import getpass
import logging
import os
import signal
import time
from subprocess import DEVNULL, PIPE, STDOUT, CalledProcessError  # nosec
from typing import Callable, List, Optional, Type

import click
import psutil

from gs_manager.command import Config, ServerCommandClass
from gs_manager.decorators import multi_instance, require, single_instance
from gs_manager.logger import get_logger
from gs_manager.null import NullServer
from gs_manager.utils import get_server_path, run_command

__all__ = [
    "EmptyServer",
    "BaseServer",
    "BaseServerConfig",
    "STATUS_SUCCESS",
    "STATUS_FAILED",
    "STATUS_PARTIAL_FAIL",
]

STATUS_SUCCESS = 0
STATUS_FAILED = 1
STATUS_PARTIAL_FAIL = 2


class BaseServerConfig(Config):
    multi_instance: bool = False

    _excluded_properties: List[str] = Config._excluded_properties + [
        "multi_instance",
    ]

    name: str = "game_server"
    user: str = getpass.getuser()

    # start command config
    wait_start: int = 3
    max_start: int = 60
    spawn_process: bool = False
    start_command: str = None
    start_directory: str = ""

    # stop command config
    max_stop: int = 30
    pre_stop: int = 30
    stop_command: str = None

    # save command config
    save_command: str = None

    # say command config
    say_command: str = None

    @property
    def global_options(self):
        return {
            "all": [
                {
                    "param_decls": ("-n", "--name"),
                    "type": str,
                    "help": (
                        "Name of gameserver service, should be unique "
                        "across all gameservers to prevent ID conflicts. "
                        "Instance names will be appended to global name"
                    ),
                },
                {
                    "param_decls": ("-u", "--user"),
                    "type": str,
                    "help": ("User to run the game server as"),
                },
            ],
            "instance_enabled": [
                {
                    "param_decls": ("-i", "--current_instance"),
                    "type": str,
                    "help": "Current instance to run commands against.",
                },
                {
                    "param_decls": ("-p", "--parallel"),
                    "is_flag": True,
                    "help": "Used in conjuntion with -ci @all to run all "
                    "subcommands in parallel",
                },
            ],
        }


class EmptyServer(NullServer):
    """ Empty game server with no commands"""

    name: str = "empty"

    _config: Config

    config_class: Optional[Type[Config]] = None
    _logger: Optional[logging.getLoggerClass()] = None

    def __init__(self, config: Config):
        self._config = config

    @property
    def config(self) -> Config:
        self._config.update_config(self.context)
        return self._config

    @property
    def context(self) -> click.Context:
        return click.get_current_context()

    @property
    def logger(self) -> logging.getLoggerClass():
        if self._logger is None:
            self._logger = get_logger()
        return self._logger


class BaseServer(EmptyServer):
    """ Simple game server with common core commands"""

    name: str = "base"
    supports_multi_instance: bool = False

    config_class: Optional[Type[Config]] = BaseServerConfig
    _config: BaseServerConfig

    @property
    def config(self) -> BaseServerConfig:
        return super().config.current_instance

    def set_instance(
        self, instance_name: str, multi_instance: bool = False
    ) -> None:
        self._config.instance_name = instance_name
        self._config.multi_instance = multi_instance

    @property
    def server_name(self) -> str:
        if self.config.parent is None:
            return self.config.name
        return f"{self.config.parent.name}_{self.config.name}"

    def _get_pid_filename(self) -> str:
        if self.config.parent is None:
            return ".pid_file"
        return f".pid_file_{self.config.name}"

    def _get_pid_file_path(self) -> str:
        return get_server_path(self._get_pid_filename())

    def _read_pid_file(self) -> Optional[int]:
        pid = None
        pid_file = self._get_pid_file_path()
        if os.path.isfile(pid_file):
            with open(pid_file, "r") as f:
                try:
                    pid = int(f.read().strip())
                    self.logger.debug("read pid: {}".format(pid))
                except ValueError:
                    pass
        return pid

    def _write_pid_file(self, pid: int) -> None:
        self.logger.debug("write pid: {}".format(pid))
        if pid is not None:
            pid_file = self._get_pid_file_path()
            with open(pid_file, "w") as f:
                f.write(str(pid))

    def _delete_pid_file(self) -> None:
        pid_file = self._get_pid_file_path()
        if os.path.isfile(pid_file):
            os.remove(pid_file)

    def _startup_check(self) -> int:
        self.logger.info("")

        def _wait_callback():
            if self.is_running() and self.is_accessible():
                return True

        self._wait(
            self.config.max_start,
            callback=_wait_callback,
            label="timeout",
            show_percent=False,
        )
        if self.is_running():
            if self.is_accessible():
                self.logger.success(f"\n{self.config.name} is running")
                return STATUS_SUCCESS
            else:
                self.logger.error(
                    f"{self.config.name} is running but not accesible"
                )
                return STATUS_PARTIAL_FAIL
        else:
            self.logger.error(f"could not start {self.config.name}")
            return STATUS_FAILED

    def _find_pid(self, require: bool = True) -> None:
        command = (
            self.config.start_command.replace('"', '\\"')
            .replace("?", "\\?")
            .replace("+", "\\+")
            .strip()
        )
        pids = self.run_command(
            "ps -ef --sort=start_time | "
            f'grep -i -P "(?<!grep -i |-c ){command}$" | '
            "awk '{{print $2}}'"
        ).split("\n")

        self.logger.debug(f"pids: {pids}")

        for pid in pids:
            if pid is not None and not pid == "":
                self.run_command(f"ps -ef | grep {pid}")

        if pids[0] is None and not pids[0] == "":
            if require:
                raise click.ClickException("could not determine PID")
        else:
            self._write_pid_file(pids[0])

    def _wait(
        self,
        seconds: int,
        callback: Optional[Callable] = None,
        label: Optional[str] = None,
        show_eta: bool = True,
        show_percent: bool = True,
    ) -> None:
        with click.progressbar(
            length=seconds,
            label=label,
            show_eta=show_eta,
            show_percent=show_percent,
        ) as waiter:
            for item in waiter:
                if callback is not None:
                    if callback():
                        break
                time.sleep(1)

    def _prestop(
        self, seconds: int, verb: str = "shutting down", reason: str = ""
    ) -> bool:
        if self._command_exists("say_command"):
            if reason != "":
                reason = f" {reason}"

            if seconds < 60:
                time = f"{seconds} seconds"
            else:
                minutes = seconds / 60
                seconds = seconds % 60
                time = f"{minutes} minutes and {seconds} seconds"

            message = f"Server is {verb} in {time}...{reason}"

            self.invoke(
                self.command,
                command_string=self.config.say_command.format(message),
                do_print=False,
            )
            return True
        return False

    def _stop(self, pid: Optional[int] = None) -> None:
        stopped = False
        if self._command_exists("stop_command"):
            if self._command_exists("save_command"):
                self.invoke(
                    self.command,
                    command_string=self.config.save_command,
                    do_print=False,
                )

            response = self.invoke(
                self.command,
                command_string=self.config.stop_command,
                do_print=False,
            )
            if response == STATUS_SUCCESS:
                stopped = True
            else:
                self.logger.debug("stop command failed, sending kill signal")

        if not stopped:
            if pid is None:
                pid = self.get_pid()
            if pid is not None:
                os.kill(pid, signal.SIGINT)

    def _command_exists(self, command: str) -> bool:
        return (
            hasattr(self, "command")
            and isinstance(self.command, click.Command)
            and hasattr(self.config, command)
            and getattr(self.config, command) is not None
        )

    def get_pid(self) -> int:
        return self._read_pid_file()

    def is_running(self, delete_pid: bool = True) -> bool:
        """ checks if gameserver is running """

        pid = self.get_pid()
        if pid is not None:
            try:
                psutil.Process(pid)
            except psutil.NoSuchProcess:
                if delete_pid:
                    self._delete_pid_file()
            else:
                return True
        return False

    def is_accessible(self) -> bool:
        return self.is_running(delete_pid=False)

    def run_command(self, command: str, **kwargs) -> str:
        """ runs command with debug logging """

        self.logger.debug(f"run command ({self.config.user}: '{command}'")
        try:
            output = run_command(command, **kwargs)
        except Exception as ex:
            self.logger.debug("command exception: {}:{}".format(type(ex), ex))
            raise ex
        self.logger.debug("command output:")
        self.logger.debug(output)

        return output

    def invoke(self, method: Callable, *args, **kwargs) -> int:
        return self.context.invoke(method, *args, **kwargs)

    def kill_server(self) -> None:
        """ forcibly kills server process """

        pid = self.get_pid()
        if pid is not None:
            os.kill(pid, signal.SIGKILL)

    @multi_instance
    @click.command(cls=ServerCommandClass)
    @click.pass_obj
    def print_config(self, *args, **kwargs) -> int:
        """ Debug tool to just print out your server config """

        config_dict = self.config.__dict__
        if "instance_overrides" in config_dict:
            config_dict.pop("instance_overrides")

        self.logger.info(f"Config for {self.server_name}")
        self.logger.info(config_dict)

        return STATUS_SUCCESS

    @require("start_command")
    @multi_instance
    @click.command(cls=ServerCommandClass)
    @click.pass_obj
    def status(self, *args, **kwargs) -> int:
        """ checks if gameserver is running or not """

        if not self.is_running():
            self._find_pid(False)

        if self.is_running():
            if self.is_accessible():
                self.logger.success(f"{self.config.name} is running")
                return STATUS_SUCCESS
            else:
                self.logger.error(
                    f"{self.config.name} is running, but is not accessible"
                )
                return STATUS_PARTIAL_FAIL
        else:
            self.logger.warning(f"{self.config.name} is not running")
            return STATUS_FAILED

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
    def start(
        self,
        no_verify: bool,
        foreground: bool,
        start_command: Optional[str] = None,
        *args,
        **kwargs,
    ) -> int:
        """ starts gameserver """

        if self.is_running():
            self.logger.warning(f"{self.config.name} is already running")
            return STATUS_PARTIAL_FAIL

        self._delete_pid_file()
        self.logger.info(f"starting {self.config.name}...", nl=False)

        command = start_command or self.config.start_command
        popen_kwargs = {}
        if self.config.spawn_process and not foreground:
            log_file_path = get_server_path(
                ["logs", f"{self.config.name}.log"]
            )

            command = f"nohup {command}"
            popen_kwargs = {
                "return_process": True,
                "redirect_output": False,
                "stdin": DEVNULL,
                "stderr": STDOUT,
                "stdout": PIPE,
            }
        elif foreground:
            popen_kwargs = {
                "redirect_output": False,
            }

        try:
            response = self.run_command(
                command,
                cwd=get_server_path(self.config.start_directory),
                **popen_kwargs,
            )
        except CalledProcessError:
            self.logger.error("unexpected error from server")

        if foreground:
            return

        if self.config.spawn_process:
            self.run_command(
                f"cat > {log_file_path}",
                return_process=True,
                redirect_output=False,
                stdin=response.stdout,
                stderr=DEVNULL,
                stdout=DEVNULL,
            )

        if self.config.wait_start > 0:
            time.sleep(self.config.wait_start)

        self._find_pid()
        if no_verify:
            return STATUS_SUCCESS
        return self._startup_check()

    @multi_instance
    @click.command()
    @click.option(
        "-f",
        "--force",
        is_flag=True,
        help=(
            "Force kill the server. WARNING: server will not have "
            "chance to save"
        ),
    )
    @click.option(
        "--max-stop",
        type=int,
        help="Max time (in seconds) to wait for server to stop",
    )
    @click.option(
        "--pre-stop",
        type=int,
        help=(
            "Time (in seconds) before stopping the server to "
            "allow notifing users."
        ),
    )
    @click.option(
        "-r",
        "--reason",
        type=str,
        help="Reason the server is stopping",
        default="",
    )
    @click.option("-v", "--verb", type=str, help="Shutdown verb", default="")
    @click.pass_obj
    def stop(
        self, force: bool, reason: str, verb: str, *args, **kwargs
    ) -> int:
        """ stops gameserver """

        if verb == "":
            if force:
                verb = "killing"
            else:
                verb = "shutting down"

        if self.is_running():
            if self.config.pre_stop > 0 and not force:
                if self._prestop(self.config.pre_stop, verb, reason):
                    self.logger.info("notifiying users...")
                    self._wait(self.config.pre_stop)

            self.logger.info(f"{verb} {self.config.name}...")

            if force:
                self.kill_server()
                time.sleep(1)
            else:
                self._stop()

                def _wait_callback():
                    if not self.is_running():
                        return True

                self._wait(
                    self.config.max_stop,
                    callback=_wait_callback,
                    label="timeout",
                    show_percent=False,
                )

            if self.is_running():
                self.logger.error(f"could not stop {self.config.name}")
                return STATUS_PARTIAL_FAIL
            else:
                self.logger.success(f"{self.config.name} was stopped")
                return STATUS_SUCCESS
        else:
            self.logger.warning(f"{self.config.name} is not running")
            return STATUS_FAILED

    @multi_instance
    @click.command()
    @click.option(
        "-f",
        "--force",
        is_flag=True,
        help=(
            "Force kill the server. WARNING: server will not have "
            "chance to save"
        ),
    )
    @click.option(
        "--no-verify",
        is_flag=True,
        help="Do not wait until gameserver is running before exiting",
    )
    @click.option(
        "-r",
        "--reason",
        type=str,
        help="Reason the server is restarting",
        default="",
    )
    @click.pass_obj
    def restart(
        self, force: bool, no_verify: bool, reason: str, *args, **kwargs
    ):
        """ restarts gameserver"""

        if self.is_running():
            self.invoke(
                self.stop, force=force, verb="restarting", reason=reason
            )
        return self.invoke(self.start, no_verify=no_verify, foreground=False)

    @single_instance
    @click.command(cls=ServerCommandClass)
    @click.option(
        "-f",
        "--force",
        is_flag=True,
        help="Edit file even though server is running",
    )
    @click.argument("edit_path", type=click.Path())
    @click.pass_obj
    def edit(self, force: bool, edit_path: str, *args, **kwargs) -> int:
        """ edits a server file with your default editor """

        if not force and self.is_running():
            self.logger.warning(f"{self.config.name} is still running")
            return STATUS_PARTIAL_FAIL

        file_path = get_server_path(edit_path)
        editor = os.environ.get("EDITOR") or "vim"

        self.run_command(
            f"{editor} {file_path}", redirect_output=False,
        )
        return STATUS_SUCCESS


class TestServer(BaseServer):
    name: str = "test"
    supports_multi_instance: bool = True
