import os
import re
import time
from queue import Empty, Queue
from threading import Thread
from typing import List, Optional, Type, Dict
from subprocess import CalledProcessError  # nosec

import click
import click_spinner
import requests
from steamfiles import acf

from gs_manager.command import Config, ServerCommandClass
from gs_manager.decorators import multi_instance, require, single_instance
from gs_manager.servers.base import (
    STATUS_FAILED,
    STATUS_PARTIAL_FAIL,
    STATUS_SUCCESS,
    BaseServer,
    BaseServerConfig,
)
from gs_manager.utils import get_server_path
from valve.source import NoResponseError
from valve.source.a2s import ServerQuerier

__all__ = ["SteamServer", "SteamServerConfig"]

STEAM_PUBLISHED_FILES_API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1"  # noqa


def _enqueue_output(out, queue):
    for line in iter(out.readline, b""):
        queue.put(line)
    out.close()


class SteamServerConfig(BaseServerConfig):
    steamcmd_path: str = "steamcmd"
    steam_query_ip: str = "127.0.0.1"
    steam_query_port: Optional[int] = None
    workshop_id: int = None
    workshop_items: List[str] = []
    steam_username: str = None
    steam_password: str = None
    steam_requires_login: bool = False
    app_id: int = None

    @property
    def global_options(self):
        global_options = super().global_options.copy()
        all_options = [
            {
                "param_decls": ("--steamcmd-path",),
                "type": click.Path(),
                "help": "Path to steamcmd executable",
            },
            {
                "param_decls": ("--app-id",),
                "type": int,
                "help": "app ID for Steam game to update from",
            },
            {
                "param_decls": ("--steam-query-port",),
                "type": int,
                "help": "Port to query to check if server is accessible",
            },
            {
                "param_decls": ("--steam-query-ip",),
                "type": int,
                "help": "IP to query to check if server is accessible",
            },
            {
                "param_decls": ("--steam-username",),
                "type": str,
                "help": "Steam username to use instead of anonymous",
            },
            {
                "param_decls": ("--steam-password",),
                "type": str,
                "help": "Steam password to use instead of anonymous",
            },
        ]
        global_options["all"] += all_options
        return global_options


class SteamServer(BaseServer):
    name: str = "steam"

    config_class: Optional[Type[Config]] = SteamServerConfig
    _config: SteamServerConfig

    _servers: Dict[str, ServerQuerier] = {}

    @property
    def config(self) -> SteamServerConfig:
        return super().config

    @property
    def server(self) -> Optional[ServerQuerier]:
        if self.is_query_enabled():
            if self._servers.get(self.server_name) is None:
                self._servers[self.server_name] = ServerQuerier(
                    (
                        self.config.steam_query_ip,
                        int(self.config.steam_query_port),
                    ),
                )
            return self._servers[self.server_name]
        return None

    def is_accessible(self) -> bool:
        if self.is_query_enabled():
            try:
                self.server.ping()
            except NoResponseError:
                return False
        return True

    def is_query_enabled(self) -> bool:
        return self.config.steam_query_port is not None

    def _parse_line(self, bar, line):
        step_name = line.group("step_name")
        current = int(line.group("current"))
        total = int(line.group("total"))
        self.logger.debug(
            "processed: {}: {} / {}".format(step_name, current, total)
        )
        if bar is None and current < total:
            bar = click.progressbar(
                length=total,
                show_eta=False,
                show_percent=True,
                label=step_name,
            )
        if bar is not None:
            bar.update(current)

    def _wait_until_validated(
        self, app_id, process, detailed_status=False, force=False
    ):
        update_verb = "updating"
        if force:
            update_verb = "valdiating"

        if detailed_status:
            # this does not work as expected because of a steamcmd bug
            # https://github.com/ValveSoftware/Source-1-Games/issues/1684
            # https://github.com/ValveSoftware/Source-1-Games/issues/1929
            buffer = Queue()
            thread = Thread(
                target=_enqueue_output,
                args=(process.stdout, buffer),
                daemon=True,
            )
            thread.start()

            bar = None
            line_re = re.compile(
                r"Update state \(0x\d+\) (?P<step_name>\w+), progress: "
                r"\d+\.\d+ \((?P<current>\d+) \/ (?P<total>\d+)\)"
            )

            self.logger.debug("start processing output...")
            while True:
                try:
                    line = buffer.get_nowait().decode("utf-8").strip()
                except Empty:
                    time.sleep(0.1)
                else:
                    self.logger.debug("line: {}".format(line))
                    self._parse_line(bar, line_re.match(line))

                if process.poll() is not None and buffer.empty():
                    break
        else:
            self.logger.info(
                f"{update_verb} {app_id}...", nl=False,
            )

            with click_spinner.spinner():
                while process.poll() is None:
                    time.sleep(1)

    def _check_steam_for_update(self, app_id: str, branch: str):
        manifest_file = get_server_path(
            ["steamapps", f"appmanifest_{app_id}.acf"]
        )

        if not os.path.isfile(manifest_file):
            self.logger.debug("No local manifet")
            return True

        manifest = None
        with open(manifest_file, "r") as f:
            manifest = acf.load(f)

        stdout = self.run_command(
            (
                f"{self.config.steamcmd_path} +app_info_update 1 "
                f"+app_info_print {app_id} +quit"
            ),
            redirect_output=True,
        )
        index = stdout.find(f'"{app_id}"')
        app_info = acf.loads(stdout[index:])

        try:
            current_buildid = app_info[app_id]["depots"]["branches"][branch][
                "buildid"
            ]
        except KeyError:
            self.logger.debug("Failed to parse remote manifest")
            return True

        self.logger.debug(f"current: {manifest['AppState']['buildid']}")
        self.logger.debug(f"latest: {current_buildid}")
        return manifest["AppState"]["buildid"] != current_buildid

    def _get_published_file(self, file_id):
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=5)
        s.mount("http://", adapter)

        r = s.post(
            STEAM_PUBLISHED_FILES_API,
            {"itemcount": 1, "publishedfileids[0]": file_id},
        )
        r.raise_for_status()

        return r.json()

    def _stop_servers(self, was_running, reason: Optional[str] = None):
        current_instance = self.config.instance_name
        multi_instance = self.config.multi_instance

        if reason is None:
            reason = "Updates found"

        if self._command_exists("say_command"):
            self.logger.info("notifying users...")
            self.set_instance(None, False)
            self.invoke(
                self.say,
                command_string=f"{reason}. Server restarting in 5 minutes",
                do_print=False,
                parallel=True,
            )
            self._wait(300 - self.config.pre_stop)

        if self._command_exists("save_command"):
            self.logger.info("saving servers...")
            self.set_instance(None, False)
            self.invoke(
                self.command,
                command_string=self.config.save_command,
                do_print=False,
                parallel=True,
            )

        self.set_instance(None, False)
        self.invoke(
            self.stop,
            force=False,
            reason="New updates found.",
            verb="restarting",
            parallel=True,
        )

        self.set_instance(current_instance, multi_instance)

        with open(get_server_path(".start_servers"), "w") as f:
            if isinstance(was_running, bool):
                f.write("default")
            else:
                f.write(",".join(was_running))

    def _start_servers(self, restart, was_running):
        if not restart:
            return

        if not was_running:
            was_running = self._was_running_from_disk()

        if not was_running:
            return

        current_instance = self.config.instance_name
        multi_instance = self.config.multi_instance

        self.set_instance(None, False)
        if len(was_running) == 1 and was_running[0] == "default":
            self.invoke(self.start, no_verify=False, foreground=False)
        else:
            self.invoke(
                self.start,
                no_verify=False,
                foreground=False,
                parallel=True,
                current_instances=f"@each:{','.join(was_running)}",
            )

        self.set_instance(current_instance, multi_instance)

    def _was_running_from_disk(self):
        was_running = False

        start_servers = get_server_path(".start_servers")
        if os.path.exists(start_servers):
            with open(start_servers, "r") as f:
                was_running = f.read().strip().split(",")
            os.remove(start_servers)

        return was_running

    def _steam_login(self) -> str:
        if self.config.steam_username and self.config.steam_password:
            return (
                f"+login {self.config.steam_username} "
                f"{self.config.steam_password}"
            )
        elif self.config.steam_requires_login:
            raise click.BadParameter(
                (
                    "this server requires a valid Steam login. Provide "
                    "a --steam-username and --steam-password"
                ),
                self.context,
            )

        return "+login anonymous"

    def str_mods(self, mods):
        mods = [str(mod) for mod in mods]
        return mods

    @multi_instance
    @click.command(cls=ServerCommandClass)
    @click.pass_obj
    def status(self, *args, **kwargs):
        """ checks if Steam server is running or not """

        if not self.is_running():
            self._find_pid(False)

        if self.is_running():
            try:
                if self.is_query_enabled():
                    server_info = self.server.info()
                    self.logger.success(f"{self.server_name} is running")
                    self.logger.info(
                        f"server name: {server_info['server_name']}"
                    )
                    self.logger.info(f"map: {server_info['map']}")
                    self.logger.info(f"game: {server_info['game']}")
                    self.logger.info(
                        f"players: {server_info['player_count']}/"
                        f"{server_info['max_players']} "
                        f"({server_info['bot_count']} bots)"
                    )
                    self.logger.info(
                        f"server type: {server_info['server_type']}"
                    )
                    self.logger.info(
                        "password protected: "
                        f"{server_info['password_protected']}"
                    )
                    self.logger.info(f"VAC: {server_info['vac_enabled']}")
                    self.logger.info(f"version: {server_info['version']}")
                else:
                    self.logger.success(f"{self.config.name} is running")
                return STATUS_SUCCESS
            except NoResponseError:
                self.logger.error(
                    f"{self.server_name} is running but not accesible"
                )
                return STATUS_PARTIAL_FAIL

        self.logger.warning(f"{self.server_name} is not running")
        return STATUS_FAILED

    @require("app_id")
    @require("steamcmd_path")
    @single_instance
    @click.option(
        "--allow-run", is_flag=True, help="Allow running instances",
    )
    @click.option(
        "-f",
        "--force",
        is_flag=True,
        help="Force a full validate of all mod files",
    )
    @click.option(
        "-s",
        "--stop",
        is_flag=True,
        help="Do a shutdown if instances are running",
    )
    @click.option(
        "-r",
        "--restart",
        is_flag=True,
        help="Do a restart if instances are running",
    )
    @click.command(cls=ServerCommandClass)
    @click.pass_obj
    def install(
        self,
        allow_run: bool,
        force: bool,
        stop: bool,
        restart: bool,
        app_id: Optional[int] = None,
        *args,
        **kwargs,
    ) -> int:
        """ installs/validates/updates the gameserver """

        app_id = app_id or self.config.app_id
        if not force:
            self.logger.info(f"checking for update for {app_id}...")
            needs_update = self._check_steam_for_update(
                str(self.config.app_id), "public"
            )
            if not needs_update:
                self.logger.success(
                    f"{self.config.app_id} is already on latest version"
                )
                return STATUS_SUCCESS

        was_running = False
        if not allow_run:
            was_running = self.is_running(check_all=True)
            if was_running:
                if not (restart or stop):
                    self.logger.warning(
                        f"at least once instance of {app_id} "
                        "is still running"
                    )
                    return STATUS_PARTIAL_FAIL
                self._stop_servers(
                    was_running, reason="Updates found for game"
                )

        process = self.run_command(
            (
                f"{self.config.steamcmd_path} {self._steam_login()} "
                f"+force_install_dir {self.config.server_path} +app_update "
                f"{app_id} validate +quit"
            ),
            redirect_output=True,
            return_process=True,
        )

        self._wait_until_validated(app_id, process, force=force)

        if process.returncode == 0:
            self.logger.success("\nvalidated {}".format(app_id))

            self._start_servers(restart, was_running)
            return STATUS_SUCCESS
        else:
            self.logger.error(
                "\nfailed to validate {}".format(self.server_name)
            )
            return STATUS_FAILED

    @require("app_id")
    @require("workshop_id")
    @single_instance
    @click.command(cls=ServerCommandClass)
    @click.option(
        "-w",
        "--workshop-id",
        type=int,
        help="Workshop ID to use for downloading workshop items from",
    )
    @click.option(
        "-i",
        "--workshop-items",
        type=int,
        multiple=True,
        help="List of comma seperated IDs for workshop items to download",
    )
    @click.option(
        "--allow-run", is_flag=True, help="Allow running instances",
    )
    @click.option(
        "-f",
        "--force",
        is_flag=True,
        help="Force a full validate of all mod files",
    )
    @click.option(
        "-s",
        "--stop",
        is_flag=True,
        help="Do a shutdown if instances are running",
    )
    @click.option(
        "-r",
        "--restart",
        is_flag=True,
        help="Do a restart if instances are running",
    )
    @click.pass_obj
    def workshop_download(
        self,
        allow_run: bool,
        force: bool,
        stop: bool,
        restart: bool,
        *args,
        **kwargs,
    ) -> int:
        """ downloads Steam workshop items """

        was_running = False
        if not force:
            needs_update = self._check_steam_for_update(
                str(self.config.workshop_id), "public"
            )
            if not needs_update:
                self.logger.success(
                    f"{self.config.workshop_id} is already on latest version"
                )
                self._start_servers(restart, was_running)
                return STATUS_SUCCESS

        if not allow_run:
            was_running = self.is_running(check_all=True)
            if was_running:
                if not (restart or stop):
                    self.logger.warning(
                        f"at least once instance of {self.config.app_id} "
                        "is still running"
                    )
                    return STATUS_PARTIAL_FAIL
                self._stop_servers(
                    was_running, reason="Updates found for workshop app"
                )

        status = self.invoke(
            self.install,
            app_id=self.config.workshop_id,
            allow_run=True,
            force=force,
        )

        if not status == STATUS_SUCCESS:
            return status

        if len(self.config.workshop_items) == 0:
            self.logger.warning("\nno workshop items selected for install")
            return STATUS_PARTIAL_FAIL

        mods_to_update = []
        manifest_file = get_server_path(
            [
                "steamapps",
                "workshop",
                f"appworkshop_{self.config.workshop_id}.acf",
            ],
        )

        if not force and os.path.isfile(manifest_file):
            manifest = None
            with open(manifest_file, "r") as f:
                manifest = acf.load(f)

            self.logger.info("checking for updates for workshop items...")
            with click.progressbar(self.config.workshop_items) as bar:
                for workshop_item in bar:
                    workshop_item = str(workshop_item)
                    if (
                        workshop_item
                        not in manifest["AppWorkshop"][
                            "WorkshopItemsInstalled"
                        ]
                    ):
                        mods_to_update.append(workshop_item)
                        continue

                    last_update_time = int(
                        manifest["AppWorkshop"]["WorkshopItemsInstalled"][
                            workshop_item
                        ]["timeupdated"]
                    )

                    try:
                        latest_metadata = self._get_published_file(
                            workshop_item
                        )
                    except requests.HTTPError:
                        self.logger.error(
                            "\ncould not query Steam for updates"
                        )
                        return STATUS_FAILED

                    newest_update_time = int(
                        latest_metadata["response"]["publishedfiledetails"][0][
                            "time_updated"
                        ]
                    )

                    if last_update_time < newest_update_time:
                        mods_to_update.append(workshop_item)
        else:
            mods_to_update = self.config.workshop_items

        if len(mods_to_update) == 0:
            self.logger.success("all workshop items already up to date")
            self._start_servers(restart, was_running)
            return STATUS_SUCCESS

        self.logger.info("downloading workshop items...")
        with click.progressbar(mods_to_update) as bar:
            for workshop_item in bar:
                try:
                    self.run_command(
                        (
                            f"{self.config.steamcmd_path} "
                            f"{self._steam_login()} +force_install_dir "
                            f"{self.config.server_path} "
                            "+workshop_download_item "
                            f"{self.config.workshop_id} {workshop_item} +quit"
                        )
                    )
                except CalledProcessError:
                    self.logger.error("\nfailed to validate workshop items")
                    return STATUS_FAILED

        self.logger.success("\nvalidated workshop items")
        self._start_servers(restart, was_running)
        return STATUS_SUCCESS
