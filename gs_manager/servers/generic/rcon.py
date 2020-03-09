from typing import Dict, Optional, Type

import click

from gs_manager.command import Config, ServerCommandClass
from gs_manager.decorators import multi_instance, require, single_instance
from gs_manager.servers.base import (
    STATUS_FAILED,
    STATUS_PARTIAL_FAIL,
    STATUS_SUCCESS,
)
from gs_manager.servers.generic.steam import SteamServer, SteamServerConfig
from valve.rcon import RCON, shell
from valve.source.a2s import ServerQuerier

__all__ = ["RconServer", "RconServerConfig"]

STEAM_PUBLISHED_FILES_API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1"  # noqa


class RconServerConfig(SteamServerConfig):
    rcon_multi_part: bool = False
    rcon_password: Optional[str] = None
    rcon_ip: str = "127.0.0.1"
    rcon_port: Optional[int] = None
    rcon_timeout: int = 10

    @property
    def global_options(self):
        global_options = super().global_options.copy()
        all_options = [
            {
                "param_decls": ("--rcon-ip",),
                "type": int,
                "help": "IP RCON service runs on",
            },
            {
                "param_decls": ("--rcon-port",),
                "type": int,
                "help": "Port RCON service runs on",
            },
            {
                "param_decls": ("--rcon-password",),
                "type": str,
                "help": "Password for RCON service",
            },
            {
                "param_decls": ("--rcon-multi-part",),
                "is_flag": True,
                "help": "Flag for if server support Multiple Part Packets",
            },
            {
                "param_decls": ("--rcon-timeout",),
                "type": int,
                "help": "Timeout for RCON connection",
            },
        ]
        global_options["all"] += all_options
        return global_options


class RconServer(SteamServer):
    name: str = "rcon"

    config_class: Optional[Type[Config]] = RconServerConfig
    _config: RconServerConfig

    _servers: Dict[str, ServerQuerier] = {}

    @property
    def config(self) -> RconServerConfig:
        return super().config

    def is_rcon_enabled(self):
        return (
            self.config.rcon_ip is not None
            and self.config.rcon_port is not None
            and self.config.rcon_password is not None
        )

    def _get_rcon_args(self):
        args = {
            "address": (self.config.rcon_ip, int(self.config.rcon_port),),
            "password": self.config.rcon_password,
            "timeout": self.config.rcon_timeout,
            "multi_part": self.config.rcon_multi_part,
        }

        self.logger.debug(f"rcon args: {args}")
        return args

    def is_accessible(self):
        is_accessible = super().is_accessible()
        if is_accessible and self.is_rcon_enabled():
            rcon = RCON(**self._get_rcon_args())
            try:
                rcon.connect()
            except ConnectionRefusedError:
                is_accessible = False
        return is_accessible

    def _command_exists(self, command: str) -> bool:
        return super()._command_exists(command) and self.is_rcon_enabled()

    @multi_instance
    @click.command(cls=ServerCommandClass)
    @click.argument("command_string")
    @click.pass_obj
    def command(
        self, command_string: str, do_print: bool = True, *args, **kwargs
    ):
        """ runs console command using RCON """

        if self.is_running():
            if self.is_rcon_enabled():
                output = None
                rcon = RCON(**self._get_rcon_args())
                try:
                    rcon.connect()
                except ConnectionRefusedError:
                    if do_print:
                        self.logger.warning("could not connect to RCON")
                    return STATUS_FAILED
                else:
                    rcon.authenticate()
                    output = rcon.execute(command_string).text
                    rcon.close()

                    if do_print and output is not None:
                        self.logger.info(output)
                    return STATUS_SUCCESS

            if do_print:
                self.logger.warning(
                    f"{self.server_name} does not have RCON enabled"
                )
            return STATUS_PARTIAL_FAIL

        self.logger.warning(f"{self.server_name} is not running")
        return STATUS_PARTIAL_FAIL

    @require("save_command")
    @multi_instance
    @click.command(cls=ServerCommandClass)
    @click.option(
        "--save-command", type=str, help="Command to save the server"
    )
    @click.pass_obj
    def save(self, do_print: bool = True, *args, **kwargs) -> int:
        """ saves gameserver """

        return self.invoke(
            self.command,
            command_string=self.config.save_command,
            do_print=do_print,
        )

    @require("say_command")
    @multi_instance
    @click.command(cls=ServerCommandClass)
    @click.argument("message")
    @click.option(
        "--say-command",
        type=str,
        help="Command format to send broadcast to sever",
    )
    @click.pass_obj
    def say(self, message, do_print=True, *args, **kwargs) -> int:
        """ broadcasts a message to gameserver """

        return self.invoke(
            self.command,
            command_string=self.config.say_command.format(message),
            do_print=do_print,
        )

    @single_instance
    @click.command(cls=ServerCommandClass)
    @click.pass_obj
    def shell(self, *args, **kwargs):
        """
        creates RCON shell.
        Shell docs: https://python-valve.readthedocs.io/en/latest/rcon.html#using-the-rcon-shell
        """  # noqa

        if self.is_running():
            if self.is_rcon_enabled():
                args = self._get_rcon_args()
                shell(args["address"], args["password"], args["multi_part"])
            else:
                self.logger.warning(
                    f"{self.server_name} does not have RCON enabled"
                )
        else:
            raise click.ClickException(f"{self.server_name} is not running")
