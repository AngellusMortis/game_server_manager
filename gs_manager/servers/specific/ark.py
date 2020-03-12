import os
import struct
import zlib
from typing import Any, Dict, List, Optional, Type
from steamfiles import acf
import shutil

import click

from gs_manager.command import Config, ServerCommandClass
from gs_manager.servers.generic.rcon import RconServer, RconServerConfig
from gs_manager.decorators import multi_instance, require, single_instance
from gs_manager.command.types import KeyValuePairs
from gs_manager.servers import (
    STATUS_FAILED,
    STATUS_PARTIAL_FAIL,
    STATUS_SUCCESS,
)
from gs_manager.utils import get_server_path, download_file

__all__ = ["ArkServerConfig", "ArkServer"]


STEAM_DOWNLOAD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"  # noqa


def collapse_key_value_list(context, param, values):
    value_dict = {}

    for value in values:
        value_dict.update(value)

    return value_dict


def _make_arg_string(args: dict, prefix: str) -> str:
    arg_string = ""
    for key, value in args.items():
        param = key
        if value is not None:
            param += "={}".format(str(value).replace(" ", "\\ "))
        arg_string += prefix + param
    return arg_string


def _make_command_args(ark_config: Dict[str, dict]) -> str:
    command_args = ark_config["map"]
    command_args += _make_arg_string(ark_config["params"], "?")
    command_args += _make_arg_string(ark_config["options"], " -")

    return command_args


class ArkServerConfig(RconServerConfig):
    app_id: int = 376030
    rcon_port: int = 27000
    spawn_process: bool = True
    steam_query_port: int = 27015
    workshop_id: int = 346110
    server_log: str = os.path.join(
        "ShooterGame", "Saved", "Logs", "ShooterGame.log"
    )
    backup_directory: str = os.path.join("ShooterGame", "Saved", "SavedArks")
    stop_command: str = "DoExit"
    say_command: str = "Broadcast {}"
    save_command: str = "SaveWorld"
    max_start: int = 120
    max_stop: int = 120
    rcon_multi_port: bool = True

    workshop_branch: bool = True
    ark_map: str = "TheIsland"
    ark_params: Dict[str, Any] = {}
    ark_options: Dict[str, Any] = {}

    _excluded_properties: List[str] = RconServerConfig._excluded_properties + [
        "start_command",
        "spawn_process",
        "say_command",
        "stop_command",
        "save_command",
        "rcon_multi_port",
        "ark_config",
        "start_directory",
    ]

    _instance_properties: List[str] = ["ark_config", "start_command"]
    _extra_attr: List[str] = ["_ark_config", "_start_command"]

    _ark_config: Optional[Dict[str, Any]] = None
    _start_command: Optional[str] = None

    @property
    def ark_config(self) -> Dict[str, dict]:
        if self._ark_config is None:
            config = {
                "map": self.ark_map,
                "params": self.ark_params.copy(),
                "options": self.ark_options.copy(),
            }

            if not self.steam_query_ip == "127.0.0.1":
                config["params"]["MultiHome"] = self.steam_query_ip

            if self.steam_query_port is not None:
                config["params"]["QueryPort"] = self.steam_query_port

            if (
                self.rcon_ip is not None
                and self.rcon_port is not None
                and self.rcon_password is not None
            ):
                config["params"]["RCONEnabled"] = True
                config["params"]["RCONPort"] = self.rcon_port
                config["params"][
                    "ServerAdminPassword"
                ] = self.rcon_password or config["params"].get(
                    "ServerAdminPassword"
                )

            if len(self.workshop_items) > 0:
                config["params"]["GameModIds"] = ",".join(
                    [str(i) for i in self.workshop_items]
                )

            self._ark_config = config

        return self._ark_config

    @property
    def start_command(self) -> str:
        if self._start_command is None:
            config_args = _make_command_args(self.ark_config)

            server_command = get_server_path(
                ["ShooterGame", "Binaries", "Linux", "ShooterGameServer"]
            )

            command = (
                "{} {} -server -servergamelog -log "
                "-servergamelogincludetribelogs"
            ).format(server_command, config_args,)

            if "automanagedmods" in command:
                raise click.BadParameter(
                    "-automanagedmods option is not supported"
                )
            self._start_command = command

        return self._start_command


class ArkServer(RconServer):
    name: str = "ark"
    supports_multi_instance: bool = True

    config_class: Optional[Type[Config]] = ArkServerConfig
    _config: ArkServerConfig

    @property
    def config(self) -> ArkServerConfig:
        return super().config

    def _z_unpack(self, from_path, to_path):
        """
        unpacks .z files downloaded from Steam workshop

        adapted from https://github.com/TheCherry/ark-server-manager/blob/master/src/z_unpack.py
        """  # noqa
        with open(from_path, "rb") as f_from:
            with open(to_path, "wb") as f_to:
                f_from.read(8)
                size1 = struct.unpack("q", f_from.read(8))[0]
                f_from.read(8)
                size2 = struct.unpack("q", f_from.read(8))[0]
                if size1 == -1641380927:
                    size1 = 131072
                runs = (size2 + size1 - 1) / size1
                array = []
                for i in range(int(runs)):
                    array.append(f_from.read(8))
                    f_from.read(8)
                for i in range(int(runs)):
                    to_read = array[i]
                    compressed = f_from.read(struct.unpack("q", to_read)[0])
                    decompressed = zlib.decompress(compressed)
                    f_to.write(decompressed)

    def _read_ue4_string(self, file_obj):
        """
        reads a UE4 string from a file object

        adapted from https://github.com/barrycarey/Ark_Mod_Downloader/blob/master/Ark_Mod_Downloader.py
        """  # noqa
        count = struct.unpack("i", file_obj.read(4))[0]
        flag = False
        if count < 0:
            flag = True
            count -= 1

        if flag or count <= 0:
            return ""

        return file_obj.read(count)[:-1].decode()

    def _write_ue4_string(self, string_to_write, file_obj):
        """
        writes a UE4 string to a file object

        adapted from https://github.com/barrycarey/Ark_Mod_Downloader/blob/master/Ark_Mod_Downloader.py
        """  # noqa
        string_length = len(string_to_write) + 1
        file_obj.write(struct.pack("i", string_length))
        barray = bytearray(string_to_write, "utf-8")
        file_obj.write(barray)
        file_obj.write(struct.pack("p", b"0"))

    def _parse_base_info(self, mod_info_file):
        """
        parses an ARK mod.info file

        adapted from https://github.com/barrycarey/Ark_Mod_Downloader/blob/master/Ark_Mod_Downloader.py
        """  # noqa
        map_names = []
        with open(mod_info_file, "rb") as f:
            self._read_ue4_string(f)
            map_count = struct.unpack("i", f.read(4))[0]

            for x in range(map_count):
                cur_map = self._read_ue4_string(f)
                if cur_map:
                    map_names.append(cur_map)
        return map_names

    def _read_byte_string(self, f):
        decoded = None
        size = struct.unpack("i", f.read(4))[0]
        flag = False
        if size < 0:
            flag = True
            size -= 1

        if not flag and size > 0:
            raw = f.read(size)
            decoded = raw[:-1].decode()
        return decoded

    def _parse_meta_data(self, mod_meta_file):
        """
        parses an ARK modmeta.info file

        adapted from https://github.com/barrycarey/Ark_Mod_Downloader/blob/master/Ark_Mod_Downloader.py
        """  # noqa
        meta_data = {}
        with open(mod_meta_file, "rb") as f:
            total_pairs = struct.unpack("i", f.read(4))[0]

            for x in range(total_pairs):
                key = self._read_byte_string(f)
                value = self._read_byte_string(f)

                if key and value:
                    meta_data[key] = value
        return meta_data

    def _create_mod_file(self, mod_dir, mod_file, mod_id):
        self.logger.debug("createing .mod file for {}...".format(mod_id))
        mod_info_file = os.path.join(mod_dir, "mod.info")
        mod_meta_file = os.path.join(mod_dir, "modmeta.info")
        mod_id = int(mod_id)

        if os.path.isfile(mod_info_file) and os.path.isfile(mod_meta_file):
            map_names = self._parse_base_info(mod_info_file)
            meta_data = self._parse_meta_data(mod_meta_file)

            if len(map_names) > 0 and len(meta_data) > 0:
                with open(mod_file, "w+b") as f:
                    f.write(struct.pack("ixxxx", mod_id))
                    self._write_ue4_string("ModName", f)
                    self._write_ue4_string("", f)

                    map_count = len(map_names)
                    f.write(struct.pack("i", map_count))
                    for m in map_names:
                        self._write_ue4_string(m, f)

                    f.write(struct.pack("I", 4280483635))
                    f.write(struct.pack("i", 2))

                    if "ModType" in meta_data:
                        mod_type = b"1"
                    else:
                        mod_type = b"0"

                    f.write(struct.pack("p", mod_type))
                    meta_length = len(meta_data)
                    f.write(struct.pack("i", meta_length))

                    for key, value in meta_data.items():
                        self._write_ue4_string(key, f)
                        self._write_ue4_string(value, f)
                    return True

        return False

    def _extract_files(self, mod_dir):
        for root, dirs, files in os.walk(mod_dir):
            for filename in files:
                if not filename.endswith(".z"):
                    continue

                file_path = os.path.join(root, filename)
                to_extract_path = file_path[:-2]
                size_file = "{}.uncompressed_size".format(file_path)
                size = None

                if os.path.isfile(size_file):
                    with open(size_file, "r") as f:
                        size = int(f.read().strip())
                else:
                    self.logger.debug("{} does not exist".format(size_file))
                    return False

                self.logger.debug(to_extract_path)
                self.logger.debug("extracting {}...".format(filename))
                self._z_unpack(file_path, to_extract_path)
                u_size = os.stat(to_extract_path).st_size
                self.logger.debug("{}: {} {}".format(filename, u_size, size))
                if u_size == size:
                    os.remove(file_path)
                    os.remove(size_file)
                else:
                    self.logger.error(
                        "could not validate {}".format(to_extract_path)
                    )
                    return False
        return True

    @require("ark_map")
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
        "--ark-map", type=str, help="Map to initalize ARK server with"
    )
    @click.option(
        "--ark-params",
        type=KeyValuePairs(),
        multiple=True,
        callback=collapse_key_value_list,
        help="? parameters to pass to ARK server. MultiHome, "
        "QueryPort, RCONEnabled, RCONPort, and GameModIds "
        "not supported, see other options for those. "
        "ServerAdminPassword also not support if "
        "--rcon-password is passed in",
    )
    @click.option(
        "--ark-options",
        type=KeyValuePairs(),
        multiple=True,
        callback=collapse_key_value_list,
        help="- options to pass to ARK server. -log, -server, "
        "-servergamelog, -servergamelogincludetribelogs "
        "passed in automatically. -automanagedmods is "
        "not supported (yet).",
    )
    @click.option(
        "--workshop-items",
        type=int,
        help="Comma list of mod IDs to pass to ARK server",
    )
    @click.pass_obj
    def start(
        self, no_verify: bool, foreground: bool, *args, **kwargs,
    ) -> int:
        """ starts ARK server """

        self.logger.debug(self.config.start_command)

        return self.invoke(
            super().start,
            no_verify=no_verify,
            foreground=foreground,
            start_command=self.config.start_command,
        )

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
        """ installs/validates/updates the ARK server """

        status = self.invoke(
            super().install,
            app_id=app_id,
            force=force,
            stop=stop,
            restart=restart,
        )

        self.logger.debug("super status: {}".format(status))

        if status == STATUS_SUCCESS:
            steamcmd_dir = get_server_path(
                ["Engine", "Binaries", "ThirdParty", "SteamCMD", "Linux"]
            )
            steamcmd_path = os.path.join(steamcmd_dir, "steamcmd.sh")

            if not os.path.isdir(steamcmd_dir):
                os.makedirs(steamcmd_dir, exist_ok=True)

            if not os.path.isfile(steamcmd_path):
                self.logger.info("installing Steam locally for ARK...")
                old_path = os.getcwd()
                os.chdir(steamcmd_dir)
                filename = download_file(STEAM_DOWNLOAD_URL)
                self.run_command("tar -xf {}".format(filename))
                os.remove(os.path.join(steamcmd_dir, filename))
                self.run_command("{} +quit".format(steamcmd_path))
                os.chdir(old_path)
                self.logger.success("Steam installed successfully")

        return status

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
        "--workshop-branch",
        type=str,
        help="Branch to use for workshop items for the ARK mod. "
        "Defaults to Windows, Linux branch is usually highly "
        "unstable. Do not change unless you know what you "
        "are doing",
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
        """ downloads and installs ARK mods """

        status = self.invoke(
            super().workshop_download,
            allow_run=True,
            force=force,
            stop=stop,
            restart=False,
        )

        self.logger.debug("super status: {}".format(status))

        if status == STATUS_SUCCESS:
            mod_path = get_server_path(["ShooterGame", "Content", "Mods"])
            base_src_dir = get_server_path(
                [
                    "steamapps",
                    "workshop",
                    "content",
                    str(self.config.workshop_id),
                ]
            )

            mods_to_update = []
            manifest_file = get_server_path(
                [
                    "steamapps",
                    "workshop",
                    f"appworkshop_{self.config.workshop_id}.acf",
                ]
            )

            if not force and os.path.isfile(manifest_file):
                manifest = None
                with open(manifest_file, "r") as f:
                    manifest = acf.load(f)

                    for workshop_item in self.config.workshop_items:
                        workshop_item = str(workshop_item)
                        mod_dir = os.path.join(mod_path, str(workshop_item))
                        mod_file = os.path.join(
                            mod_path, "{}.mod".format(workshop_item)
                        )

                        if not os.path.isfile(mod_file) or (
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
                        last_extract_time = os.path.getctime(mod_file)

                        if last_update_time > last_extract_time:
                            mods_to_update.append(workshop_item)
            else:
                mods_to_update = self.config.workshop_items

            mods_to_update = self.str_mods(mods_to_update)
            if len(mods_to_update) == 0:
                was_running = self.is_running("@any")
                # automatically check for any servers shutdown by install
                if not was_running:
                    self._start_servers(restart, was_running)
                return STATUS_SUCCESS

            self.logger.info(
                f"{len(mods_to_update)} mod(s) need to be extracted: "
                f"{','.join(mods_to_update)}"
            )

            was_running = self.is_running("@any")
            if was_running:
                if not (restart or stop):
                    self.logger.warning(
                        (
                            f"at least once instance of {self.config.app_id}"
                            " is still running"
                        )
                    )
                    return STATUS_PARTIAL_FAIL
                self._stop_servers(
                    was_running,
                    reason=(
                        f"Updates found for {len(mods_to_update)} "
                        f"mod(s): {','.join(mods_to_update)}"
                    ),
                )

            self.logger.info("extracting mods...")
            with click.progressbar(mods_to_update) as bar:
                for workshop_item in bar:
                    src_dir = os.path.join(base_src_dir, str(workshop_item))
                    branch_dir = os.path.join(
                        src_dir,
                        "{}NoEditor".format(self.config.workshop_branch),
                    )
                    mod_dir = os.path.join(mod_path, str(workshop_item))
                    mod_file = os.path.join(
                        mod_path, "{}.mod".format(workshop_item)
                    )

                    if not os.path.isdir(src_dir):
                        self.logger.error(
                            "could not find workshop item: {}".format(
                                self.config.workshop_id
                            )
                        )
                        return STATUS_FAILED
                    elif os.path.isdir(branch_dir):
                        src_dir = branch_dir

                    if os.path.isdir(mod_dir):
                        self.logger.debug(
                            "removing old mod_dir of {}...".format(
                                workshop_item
                            )
                        )
                        shutil.rmtree(mod_dir)
                    if os.path.isfile(mod_file):
                        self.logger.debug(
                            "removing old mod_file of {}...".format(
                                workshop_item
                            )
                        )
                        os.remove(mod_file)

                    self.logger.debug("copying {}...".format(workshop_item))
                    shutil.copytree(src_dir, mod_dir)

                    if not self._create_mod_file(
                        mod_dir, mod_file, workshop_item
                    ):
                        self.logger.error(
                            "could not create .mod file for {}".format(
                                workshop_item
                            )
                        )
                        return STATUS_FAILED

                    if not self._extract_files(mod_dir):
                        return STATUS_FAILED
            self.logger.success("workshop items successfully installed")

        if status == STATUS_SUCCESS:
            self._start_servers(restart, was_running)
        return status
