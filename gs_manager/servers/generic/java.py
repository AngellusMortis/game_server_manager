from typing import Dict, List, Optional, Type

import click

from gs_manager.command import Config, ServerCommandClass
from gs_manager.command.validators import GenericConfigType, ServerFileType
from gs_manager.decorators import multi_instance, require
from gs_manager.servers.generic.screen import ScreenServer, ScreenServerConfig

__all__ = ["JavaServerConfig", "JavaServer"]


class JavaServerConfig(ScreenServerConfig):
    command_format: str = "{} {} -jar {} {}"
    extra_args: str = ""
    java_path: str = "java"
    java_args: str = ""
    server_jar: str = None

    @property
    def start_command(self) -> str:
        return self.command_format.format(
            self.java_path, self.java_args, self.server_jar, self.extra_args,
        )

    _validators: Dict[str, List[GenericConfigType]] = {
        **ScreenServerConfig._validators,
        **{"server_jar": [ServerFileType]},
    }
    _excluded_properties: List[
        str
    ] = ScreenServerConfig._excluded_properties + ["start_command"]


class JavaServer(ScreenServer):
    name: str = "java"

    config_class: Optional[Type[Config]] = JavaServerConfig
    _config: JavaServerConfig

    @property
    def config(self) -> JavaServerConfig:
        return super().config

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
    @click.option("--java-args", type=str, help="Extra args to pass to Java")
    @click.option(
        "--server-jar", type=click.Path(), help="Path to Minecraft server jar",
    )
    @click.option(
        "--java-path", type=click.Path(), help="Path to Java executable"
    )
    @click.option("--extra-args", type=str, help="To add to jar command")
    @click.pass_obj
    def start(self, no_verify: bool, foreground: bool, *args, **kwargs) -> int:
        """ starts java gameserver """

        return self.invoke(
            super().start,
            start_command=self.config.start_command,
            no_verify=no_verify,
            forground=foreground,
        )
