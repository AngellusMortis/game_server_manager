import os
import re
import time
from typing import Dict, List, Optional, Tuple, Type

import click
import click_spinner
from mcstatus import MinecraftServer as MCServer

from gs_manager.command import Config, ServerCommandClass
from gs_manager.command.types import KeyValuePairs
from gs_manager.command.validators import KeyValuePairsType
from gs_manager.decorators import multi_instance, require, single_instance
from gs_manager.servers import (
    STATUS_FAILED,
    STATUS_PARTIAL_FAIL,
    STATUS_SUCCESS,
)
from gs_manager.servers.generic.java import JavaServer, JavaServerConfig
from gs_manager.utils import (
    download_file,
    get_json,
    get_param_obj,
    get_server_path,
)

__all__ = ["MinecraftServerConfig", "MinecraftServer"]

VERSIONS_URL = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
EULA_URL = "https://account.mojang.com/documents/minecraft_eula"


class MinecraftServerConfig(JavaServerConfig):
    stop_command: str = "stop"
    say_command: str = "say {}"
    save_command: str = "save-all"
    server_log: str = os.path.join("logs", "latest.log")

    start_memory: int = 1204
    max_memory: int = 4096
    gc_thread_count: int = 2
    server_jar: str = "minecraft_server.jar"
    java_args: str = (
        "-Xmx{}M -Xms{}M -XX:+UseConcMarkSweepGC "
        "-XX:+CMSIncrementalPacing -XX:ParallelGCThreads={} "
        "-XX:+AggressiveOpts -Dfml.queryResult=confirm"
    )
    extra_args: str = "nogui"
    wait_start: int = 3

    _excluded_properties: List[str] = JavaServerConfig._excluded_properties + [
        "mc"
    ]

    _mc_config: Optional[Dict[str, str]] = None

    @property
    def start_command(self) -> str:
        args = self.java_args.format(
            self.start_memory, self.max_memory, self.gc_thread_count
        )
        return self.command_format.format(
            self.java_path, args, self.server_jar, self.extra_args,
        )

    @property
    def mc(self) -> Dict[str, str]:
        if self._mc_config is None:
            self._mc_config = {}

            config_path = get_server_path("server.properties")
            if not os.path.isfile(config_path):
                raise click.ClickException(
                    "could not find server.properties for Minecraft server"
                )

            lines = []
            with open(config_path) as config_file:
                for line in config_file:
                    if not line.startswith("#"):
                        lines.append(line)

            self._mc_config = KeyValuePairsType.validate(lines)

        return self._mc_config

    def save_mc(self) -> None:
        property_path = get_server_path("server.properties")
        server_property_string = ""
        for key, value in self.mc.items():
            server_property_string += f"{key}={value}\n"
        with open(property_path, "w") as f:
            f.write(server_property_string)

        self._mc_config = None
        self.mc


class MinecraftServer(JavaServer):
    name: str = "minecraft"

    config_class: Optional[Type[Config]] = MinecraftServerConfig
    _config: MinecraftServerConfig
    _server: Optional[MCServer] = None

    @property
    def config(self) -> MinecraftServerConfig:
        return super().config

    @property
    def server(self):
        if self._server is None:
            ip = self.config.mc.get("server-ip")
            port = self.config.mc.get("server-port")

            if ip == "" or ip is None:
                ip = "127.0.0.1"
            if port == "" or port is None:
                port = "25565"

            self.logger.debug(f"Minecraft server: {ip}:{port}")
            self._server = MCServer(ip, int(port))
        return self._server

    def _get_minecraft_versions(
        self, beta: bool = False, old: bool = False
    ) -> Tuple[str, Dict[str, str]]:
        data = get_json(VERSIONS_URL)

        versions = {}

        latest = data["latest"]
        versions = {}
        for version in data["versions"]:
            if not beta and version["type"] == "snapshot":
                continue
            if not old and version["type"].startswith("old_"):
                continue
            versions[version["id"]] = version

        if beta:
            latest = latest["snapshot"]
        else:
            latest = latest["release"]

        return latest, versions

    def _process_log_file(self) -> bool:
        tail = self.tail_file()

        loops_since_check = 0
        processing = True
        done_match = False
        with click_spinner.spinner():
            while processing:
                for line in tail.readlines():
                    self.logger.debug(f"log: {line}")
                    done_match = (
                        re.search(r"Done \((\d+\.\d+)s\)! For help,", line)
                        is not None
                    )
                    if done_match:
                        processing = False
                    elif "agree to the EULA" in line:
                        self.logger.info("")
                        raise click.ClickException(
                            f"You must agree to Mojang's EULA. "
                            "Please read {EULA_URL} and restart server "
                            "with --accept_eula"
                        )

                if loops_since_check < 5:
                    loops_since_check += 1
                elif self.is_running():
                    loops_since_check = 0
                else:
                    self.logger.error(f"{self.server_name} failed to start")
                    processing = False
                time.sleep(1)

        self.delete_offset()
        return done_match

    def _startup_check(self) -> int:
        self.logger.debug("wait for server to start initalizing...")

        mtime = 0
        try:
            mtime = os.stat(self.config.server_log).st_mtime
        except FileNotFoundError:
            pass

        new_mtime = mtime
        wait_left = 5
        while new_mtime == mtime and wait_left > 0:
            try:
                mtime = os.stat(self.config.server_log).st_mtime
            except FileNotFoundError:
                pass
            wait_left -= 0.1
            time.sleep(0.1)

        if os.path.isfile(self.config.server_log):
            if self._process_log_file():
                self.logger.info(
                    "\nverifying Minecraft server is up...", nl=False,
                )
                return super()._startup_check()
        raise click.ClickException(
            f"could not find log file: {self.config.server_log}"
        )

    def is_accessible(self) -> bool:
        try:
            ping = self.server.ping()
            self.logger.debug(f"ping: {ping}")
        except Exception:
            return False
        return True

    @multi_instance
    @click.command(cls=ServerCommandClass)
    @click.option(
        "-d",
        "--detailed",
        is_flag=True,
        help="returns more detatiled infomation about the server",
    )
    @click.pass_obj
    def status(self, detailed: bool, *args, **kwargs) -> int:
        """ checks if Minecraft server is running or not """

        if self.is_running():
            if detailed and not self.config.mc.get("enable-query") == "true":
                raise click.ClickException(
                    "query is not enabled in server.properties"
                )

            query = None
            try:
                if detailed:
                    query = self.server.query()
                status = self.server.status()
            except ConnectionRefusedError:
                self.logger.error(
                    f"{self.server_name} is running, but not accessible"
                )
                return STATUS_FAILED
            else:
                self.logger.success(f"{self.server_name} is running")
                if query is not None:
                    self.logger.info(
                        f"host: {query.raw['hostip']}:{query.raw['hostport']}"
                    )
                    self.logger.info(
                        f"software: v{query.software.version} "
                        f"{query.software.brand}"
                    )
                self.logger.info(
                    f"version: v{status.version.name} (protocol "
                    f"{status.version.protocol})"
                )
                self.logger.info(f'description: "{status.description}"')
                if query is not None:
                    self.logger.info(f"plugins: {query.software.plugins}")
                    self.logger.info(f'motd: "{query.motd}"')

                self.logger.info(
                    f"players: {status.players.online}/{status.players.max}"
                )

                if query is not None:
                    self.logger.info(query.players.names)
                return STATUS_SUCCESS

        self.logger.warning(f"{self.server_name} is not running")
        return STATUS_PARTIAL_FAIL

    @multi_instance
    @require("extra_args")
    @require("java_path")
    @require("java_args")
    @require("server_jar")
    @multi_instance
    @click.command(cls=ServerCommandClass)
    @click.option(
        "--no-verify",
        is_flag=True,
        help="Do not wait until gameserver is running before exiting",
    )
    @click.option(
        "-w",
        "--wait-start",
        type=int,
        help=(
            "Time (in seconds) to wait after running the command "
            "before checking the server"
        ),
    )
    @click.option(
        "-m",
        "--max-start",
        type=int,
        help=(
            "Max time (in seconds) to wait before assuming the "
            "server is deadlocked"
        ),
    )
    @click.option(
        "--spawn-process",
        is_flag=True,
        help=(
            "Spawn a new process in the background detached from the "
            "main process"
        ),
    )
    @click.option(
        "-f",
        "--foreground",
        is_flag=True,
        help=(
            "Start gameserver in foreground. Ignores "
            "spawn_process, screen, and any other "
            "options or classes that cause server to run "
            "in background."
        ),
    )
    @click.option(
        "--start-directory",
        type=str,
        help="Directory to run the start command in relative to server_path",
    )
    @click.option(
        "--start-memory", type=int, help="Starting amount of member (in MB)",
    )
    @click.option(
        "--max-memory", type=int, help="Max amount of member (in MB)"
    )
    @click.option(
        "--thread-count",
        type=int,
        help="Number of Garbage Collection Threads",
    )
    @click.option(
        "--server-jar", type=click.Path(), help="Path to Minecraft server jar",
    )
    @click.option(
        "--java-path", type=click.Path(), help="Path to Java executable"
    )
    @click.option(
        "--add-property",
        type=KeyValuePairs(),
        multiple=True,
        help="Adds (or modifies) a property in the " "server.properties file",
    )
    @click.option(
        "--remove-property",
        type=str,
        multiple=True,
        help="Removes a property from the server.properties",
    )
    @click.option(
        "--accept_eula",
        is_flag=True,
        default=False,
        help="Forcibly accepts the Mojang EULA before starting the "
        f"server. Be sure to read {EULA_URL} before accepting",
    )
    @click.pass_obj
    def start(
        self,
        no_verify: bool,
        foreground: bool,
        accept_eula: bool,
        add_property: List[Dict[str, str]],
        remove_property: List[str],
        *args,
        **kwargs,
    ) -> int:
        """ starts Minecraft server """

        if add_property or remove_property:
            for prop in add_property:
                self.config.mc.update(prop)

            for prop in remove_property:
                del self.config.mc[prop]

            self.config.save_mc()

        if accept_eula:
            eula_path = get_server_path("eula.txt")
            with open(eula_path, "w") as f:
                f.write("eula=true")

        return self.invoke(
            super().start, no_verify=no_verify, foreground=foreground,
        )

    @multi_instance
    @click.command(cls=ServerCommandClass)
    @click.argument("command_string")
    @click.pass_obj
    def command(
        self, command_string: str, do_print: bool = True, *args, **kwargs
    ) -> int:
        """ runs console command """

        tail = None
        if do_print and os.path.isfile(self.config.server_log):
            self.logger.debug("reading log...")
            tail = self.tail_file()
            tail.readlines()

        status = self.invoke(
            super().command, command_string=command_string, do_print=False,
        )

        if status == STATUS_SUCCESS and do_print and tail is not None:
            time.sleep(1)
            self.logger.debug("looking for command output...")
            for line in tail.readlines():
                match = re.match(
                    r"(\[.*] \[.*]: *)?(?P<message>[^\n]+)?", line.strip()
                )
                if match is not None:
                    message = match.group("message")
                    if not message == "":
                        self.logger.info(message)
            self.delete_offset()
        return status

    @single_instance
    @click.command(cls=ServerCommandClass)
    @click.option(
        "-f",
        "--force",
        is_flag=True,
        help="Install version even if current server jar is not a symlink",
    )
    @click.option(
        "-b",
        "--beta",
        is_flag=True,
        help="Allow installing beta snapshot versions",
    )
    @click.option(
        "-o",
        "--old",
        is_flag=True,
        help="Allow installing old beta/alpha versions",
    )
    @click.option(
        "-e", "--enable", is_flag=True, help="Enable version after installing"
    )
    @click.argument("minecraft_version", type=str, required=False)
    @click.pass_obj
    def install(
        self,
        force: bool,
        beta: bool,
        old: bool,
        enable: bool,
        minecraft_version: str,
        *args,
        **kwargs,
    ) -> int:
        """ installs a specific version of Minecraft """

        latest, versions = self._get_minecraft_versions(beta, old)

        if minecraft_version is None:
            minecraft_version = latest
        elif minecraft_version not in versions:
            raise click.BadParameter(
                "could not find minecraft version",
                self.context,
                get_param_obj(self.context, "minecraft_version"),
            )

        self.logger.debug("minecraft version:")
        self.logger.debug(versions[minecraft_version])

        jar_dir = get_server_path("jars")
        jar_file = f"minecraft_server.{minecraft_version}.jar"
        jar_path = os.path.join(jar_dir, jar_file)
        if os.path.isdir(jar_dir):
            if os.path.isfile(jar_path):
                if force:
                    os.remove(jar_path)
                else:
                    raise click.BadParameter(
                        f"minecraft v{minecraft_version} already installed",
                        self.context,
                        get_param_obj(self.context, "minecraft_version"),
                    )
        else:
            os.makedirs(jar_dir)

        self.logger.info(f"downloading v{minecraft_version}...")
        version = get_json(versions[minecraft_version]["url"])
        download_file(
            version["downloads"]["server"]["url"],
            jar_path,
            sha1=version["downloads"]["server"]["sha1"],
        )

        self.logger.success(f"minecraft v{minecraft_version} installed")

        link_path = get_server_path(self.config.server_jar)
        if not os.path.isfile(link_path) or enable:
            return self.invoke(
                self.enable, minecraft_version=minecraft_version,
            )
        return STATUS_SUCCESS

    @single_instance
    @click.command(cls=ServerCommandClass)
    @click.option(
        "-f",
        "--force",
        is_flag=True,
        help="Force enable even if server is running",
    )
    @click.argument("minecraft_version", type=str)
    @click.pass_obj
    def enable(
        self, force: bool, minecraft_version: str, *args, **kwargs
    ) -> int:
        """ enables a specific version of Minecraft """

        if self.is_running():
            self.logger.error(f"{self.server_name} is still running")
            return STATUS_FAILED

        jar_dir = get_server_path("jars")
        jar_file = f"minecraft_server.{minecraft_version}.jar"
        jar_path = os.path.join(jar_dir, jar_file)
        link_path = get_server_path(self.config.server_jar)

        if not os.path.isfile(jar_path):
            raise click.BadParameter(
                f"minecraft v{minecraft_version} is not installed",
                self.context,
                get_param_obj(self.context, "minecraft_version"),
            )

        if not (
            os.path.islink(link_path) or force or not os.path.isfile(link_path)
        ):
            raise click.ClickException(
                f"{self.config.server_jar} is not a symbolic link, "
                "use -f to override"
            )

        if os.path.isfile(link_path):
            if os.path.realpath(link_path) == jar_path:
                raise click.BadParameter(
                    f"minecraft v{minecraft_version} already enabled",
                    self.context,
                    get_param_obj(self.context, "minecraft_version"),
                )
            os.remove(link_path)

        self.run_command(f"ln -s {jar_path} {link_path}")

        self.logger.success(f"minecraft v{minecraft_version} enabled")
        return STATUS_SUCCESS

    @single_instance
    @click.command(cls=ServerCommandClass)
    @click.option(
        "-b", "--beta", is_flag=True, help="List beta snapshot versions",
    )
    @click.option(
        "-o", "--old", is_flag=True, help="List old beta/alpha versions",
    )
    @click.option(
        "--installed", is_flag=True, help="Only list installed versions"
    )
    @click.option(
        "--num",
        default=10,
        type=int,
        help="Number of versions to list, use -1 to list all",
    )
    @click.pass_obj
    def versions(
        self, beta: bool, old: bool, installed: bool, num: int, *args, **kwargs
    ) -> int:
        """ lists versions of Minecraft """

        jar_dir = get_server_path("jars")
        installed_versions = []
        for root, dirs, files in os.walk(jar_dir):
            for filename in files:
                if filename.endswith(".jar"):
                    parts = filename.split(".")
                    installed_versions.append(".".join(parts[1:-1]))

        if installed:
            if num > 0:
                installed_versions = installed_versions[:num]

            for version in installed_versions:
                self.logger.info(f"{version} (installed)")
        else:
            latest, versions = self._get_minecraft_versions(beta, old)
            display_versions = []
            if old:
                display_versions = [
                    v["id"]
                    for v in versions.values()
                    if v["type"].startswith("old_")
                ]
            elif beta:
                display_versions = [
                    v["id"]
                    for v in versions.values()
                    if v["type"].startswith("snapshot")
                ]
            else:
                display_versions = versions.keys()

            if num > 0:
                display_versions = display_versions[:num]

            for version in display_versions:
                extra = ""
                if version == latest:
                    extra = "(latest)"

                if version in installed_versions:
                    if extra == "":
                        extra = "(installed)"
                    else:
                        extra = "(latest,installed)"
                self.logger.info(f"{version} {extra}")

        return STATUS_SUCCESS
