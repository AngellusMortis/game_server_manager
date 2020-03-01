import os
import re
import shlex
import subprocess  # nosec
import sys
from typing import List, Union

import click

__all__ = [
    "to_pascal_case",
    "to_snake_case",
    "get_server_path",
    "get_param_obj",
    "run_command",
]


def to_pascal_case(name: str) -> str:
    return to_snake_case(name).replace("_", " ").title().replace(" ", "")


def to_snake_case(name: str) -> str:
    return re.sub("([a-z])([A-Z])", r"\1_\2", name).lower()


def get_server_path(path: Union[str, List[str]]) -> str:
    context = click.get_current_context()

    if isinstance(path, str):
        return os.path.join(context.obj.config.server_path, path)
    return os.path.join(context.obj.config.server_path, *path)


def get_param_obj(context, name):
    param = None
    for p in context.command.params:
        if p.name == name:
            param = p
            break
    return param


def _create_pipeline(
    args, previous_process=None, redirect_output=True, **kwargs
):
    processes = []
    split_index = args.index("|")
    split_index_1 = split_index + 1
    args1 = args[:split_index]
    args2 = args[split_index_1:]

    if previous_process is not None:
        kwargs["stdin"] = previous_process.stdout
    else:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT

    processes.append(subprocess.Popen(args1, **kwargs))  # nosec

    if "|" in args2:
        processes += _create_pipeline(
            args2,
            previous_process=processes[-1],
            redirect_output=redirect_output,
            **kwargs
        )
    else:
        if redirect_output:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.STDOUT

        kwargs["stdin"] = processes[-1].stdout

        processes.append(
            subprocess.Popen(args[split_index_1:], **kwargs)  # nosec
        )

    return processes


def run_command(command, redirect_output=True, return_process=False, **kwargs):
    args = shlex.split(command)

    processes = []
    if "|" in args:
        processes = _create_pipeline(
            args, redirect_output=redirect_output, **kwargs
        )
        for x in range(len(processes) - 1):
            processes[x].stdout.close()
    else:
        if redirect_output:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.STDOUT

        processes.append(subprocess.Popen(args, **kwargs))  # nosec

    if return_process:
        return processes[-1]
    else:
        stdout, stderr = processes[-1].communicate()

        if stdout is None:
            stdout = ""

        if not isinstance(stdout, str):
            stdout = stdout.decode(sys.getdefaultencoding())
        stdout = stdout.strip()

        if processes[-1].returncode == 0:
            return stdout

        raise subprocess.CalledProcessError(
            processes[-1].returncode, command, stdout
        )
