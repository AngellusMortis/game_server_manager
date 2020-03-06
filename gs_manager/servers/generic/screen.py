from subprocess import CalledProcessError  # nosec
from typing import Optional, Type

import click
import psutil

from gs_manager.command import Config, ServerCommandClass
from gs_manager.decorators import multi_instance, require, single_instance
from gs_manager.servers.base import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    BaseServer,
    BaseServerConfig,
)

__all__ = ["ScreenServer", "ScreenServerConfig"]


class ScreenServerConfig(BaseServerConfig):
    history: int = 1024


class ScreenServer(BaseServer):
    name: str = "screen"

    config_class: Optional[Type[Config]] = ScreenServerConfig
    _config: ScreenServerConfig

    @property
    def config(self) -> ScreenServerConfig:
        return super().config

    def _clear_screens(self):
        try:
            self.run_command("screen -wipe")
        except CalledProcessError:
            pass

    def _stop(self, pid: Optional[int] = None) -> None:
        if pid is None:
            pid = self._get_child_pid()
        return super()._stop(pid=pid)

    def _get_child_pid(self, delete_pid: bool = True) -> Optional[int]:
        pid = self.get_pid()

        try:
            screen_process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            if delete_pid:
                self._delete_pid_file()
            pid = None
        else:
            children = screen_process.children()
            child_count = len(children)
            if child_count == 1:
                pid = children[0].pid
            elif child_count == 0:
                self._clear_screens()
            else:
                raise click.ClickException(
                    "Unexpected number of child proceses for screen"
                )
        return pid

    def is_running(self, delete_pid: bool = True) -> bool:
        is_running = False
        pid = self._get_child_pid(delete_pid=delete_pid)
        if pid is not None:
            is_running = True

        self.logger.debug("is_running: {}".format(is_running))
        return is_running

    @require("start_command")
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
        help=("Directory to run the start command in relative to server_path"),
    )
    @click.option("--start-command", type=str, help="Start up command")
    @click.pass_obj
    def start(self, no_verify: bool, foreground: bool, *args, **kwargs) -> int:
        """ starts gameserver with screen """

        command = self.config.start_command

        if not foreground:
            command = (
                f"screen -h {self.config.history} -dmS "
                f"{self.server_name} {command}"
            )

        self._clear_screens()
        return self.invoke(
            super().start,
            start_command=command,
            no_verify=no_verify,
            forground=foreground,
        )

    @multi_instance
    @click.command(cls=ServerCommandClass)
    @click.argument("command_string")
    @click.pass_obj
    def command(
        self, command_string: str, do_print: bool = True, *args, **kwargs
    ) -> int:
        """ runs console command against screen session """

        if self.is_running():
            if do_print:
                self.logger.info(
                    f"command @{self.server_name}: {command_string}"
                )

            command_string = (
                f"screen -p 0 -S {self.server_name} -X eval "
                f"'stuff \"{command_string}\"\015'"
            )
            output = self.run_command(command_string)

            if do_print:
                self.logger.info(output)
            return STATUS_SUCCESS

        self.logger.warning(f"{self.server_name} is not running")
        return STATUS_FAILED

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
        """ attachs to gameserver screen to give shell access """

        if self.is_running():
            self.run_command(f"screen -x {self.server_name}")
        else:
            raise click.ClickException(f"{self.server_name} is not running")

        return STATUS_SUCCESS
