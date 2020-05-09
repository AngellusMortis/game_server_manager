import time
from functools import update_wrapper
from multiprocessing import Process
from typing import Callable, List

import click

from gs_manager.utils import get_param_obj, surpress_stdout


def require(param: str):
    """
    decorator for a Click command to enforce a param from CLI or config
    """

    def _wrapper(command: click.Command):
        original_command = command.callback

        def _callback(*args, **kwargs):
            context = click.get_current_context()
            config = context.obj.config

            value = kwargs.get(param)

            if value is None:
                if (
                    not hasattr(config, param)
                    or getattr(config, param) is None
                ):
                    raise click.BadParameter(
                        f"must provide {param}",
                        context,
                        get_param_obj(context, param),
                    )
                value = getattr(config, param)

            config.validate(param, value)

            return original_command(*args, **kwargs)

        command.callback = update_wrapper(_callback, original_command)

        return command

    return _wrapper


def _get_instance_names(instance_str: str) -> List[str]:
    from gs_manager.servers import BaseServer

    context = click.get_current_context()
    server: BaseServer = context.obj

    instance_names = []

    if instance_str == "@all":
        instance_names = server.config.all_instance_names
    elif instance_str.startswith("@each:"):
        instance_names = instance_str[6:].split(",")
        for name in instance_names:
            if name not in server.config.all_instance_names:
                raise click.BadParameter(
                    f"instance of {name} does not exist", context,
                )

    return instance_names


def _instance_wrapper(command: click.Command, multi_callback: Callable):
    """ wraps command callback and adds instance logic """

    def _wrapper(*args, **kwargs):
        from gs_manager.servers import BaseServer

        context = click.get_current_context()
        instance_name = context.params.get("current_instance")
        server: BaseServer = context.obj
        if "current_instance" in kwargs:
            instance_name = kwargs.pop("current_instance")

        if instance_name is not None:
            server.logger.debug(
                f"command start: {context.command.name} ({instance_name})"
            )
        else:
            server.logger.debug(f"command start: {context.command.name}")

        if instance_name is not None:
            if not server.supports_multi_instance:
                raise click.BadParameter(
                    f"{server.name} does not support multiple instances",
                    context,
                )
            elif instance_name.startswith("@"):
                instance_names = _get_instance_names(instance_name)
                return multi_callback(instance_names, *args, **kwargs)
            elif instance_name not in server.config.all_instance_names:
                raise click.BadParameter(
                    f"instance of {instance_name} does not exist", context,
                )

        server.set_instance(instance_name)
        result = command(*args, **kwargs)
        server.set_instance(None)
        return result

    return _wrapper


def _run_sync(
    callback: Callable, instance_names: List[str], *args, **kwargs
) -> List[int]:
    """ runs command for each instance synchronously """
    from gs_manager.servers import BaseServer

    context = click.get_current_context()
    server: BaseServer = context.obj
    results = []

    for instance_name in instance_names:
        server.logger.debug(
            f"running {context.command.name} for instance: {instance_name}"
        )

        server.set_instance(instance_name, multi_instance=True)
        server.logger.success(f"{server.server_name}:")
        result = callback(*args, **kwargs)
        results.append(result)

    server.set_instance(None, multi_instance=False)

    return results


def _run_parallel(
    callback: Callable, instance_names: List[str], *args, **kwargs
) -> List[int]:
    """ runs command for each instance in @all in parallel """
    from gs_manager.servers import BaseServer

    context = click.get_current_context()
    server: BaseServer = context.obj
    processes = []

    if len(instance_names) == len(server.config.all_instance_names):
        instance_str = "@all"
    else:
        instance_str = ",".join(instance_names)

    server.logger.info(
        f"running {context.command.name} for "
        f"{server.config.name} {instance_str}..."
    )

    # create process for each instances
    for instance_name in instance_names:
        server.logger.debug(
            f"spawning {context.command.name} for instance: {instance_name}"
        )

        def callback_wrapper(*args, **kwargs):
            server.set_instance(instance_name)
            return callback(*args, **kwargs)

        p = Process(
            target=surpress(callback_wrapper), args=args, kwargs=kwargs, daemon=True,
        )
        p.start()
        processes.append(p)

    bar = click.progressbar(
        length=len(processes), show_eta=False, show_pos=True
    )

    completed = None
    previous_completed = 0
    not_done = True
    while not_done:
        server.logger.debug("processes: {}".format(processes))
        alive_list = [p.is_alive() for p in processes]
        server.logger.debug("processes alive: {}".format(alive_list))
        not_done = any(alive_list)
        completed = sum([int(not c) for c in alive_list])

        bar.update(completed - previous_completed)
        previous_completed = completed
        time.sleep(1)

    server.logger.success(
        f"\n{context.command.name} {server.config.name} "
        f"{instance_str} completed"
    )
    return [p.exitcode for p in processes]


def single_instance(command: click.Command):
    """
    decorator for a click command to enforce a single instance or zero
    instances are passed in
    """

    original_command = command.callback

    def multi_callback(*args, **kwargs):
        raise click.ClickException(
            "{} does not support @all".format(command.name)
        )

    wrapper_function = _instance_wrapper(original_command, multi_callback)
    command.callback = update_wrapper(wrapper_function, original_command)
    return command


def multi_instance(command: click.Command):
    """
    decorator for a click command to allow multiple instances to be passed in
    """

    original_command = command.callback

    def multi_callback(instance_names: List[str], *args, **kwargs):
        from gs_manager.servers import (
            BaseServer,
            STATUS_SUCCESS,
            STATUS_FAILED,
            STATUS_PARTIAL_FAIL,
        )

        context = click.get_current_context()
        server: BaseServer = context.obj

        if context.params.get("foreground"):
            raise click.ClickException(
                "cannot use @ options with the --foreground option"
            )

        if context.params.get("parallel"):
            results = _run_parallel(
                original_command, instance_names, *args, **kwargs
            )
        else:
            results = _run_sync(
                original_command, instance_names, *args, **kwargs
            )

        server.logger.debug(f"results: {results}")
        partial_failed = results.count(STATUS_PARTIAL_FAIL)
        failed = results.count(STATUS_FAILED)
        return_code = STATUS_SUCCESS
        total = len(results)

        if failed > 0:
            server.logger.warning(f"{failed}/{total} return a failure code")
            return_code = STATUS_PARTIAL_FAIL
        if partial_failed > 0:
            server.logger.warning(
                f"{partial_failed}/{total} return a partial failure code"
            )
            return_code = STATUS_PARTIAL_FAIL

        if failed == total:
            return_code = STATUS_FAILED
        return return_code

    wrapper_function = _instance_wrapper(original_command, multi_callback)
    command.callback = update_wrapper(wrapper_function, original_command)
    return command


def surpress(function):
    """
    decorator to surpress all stdout for a method
    """

    def _wrapper(*args, **kwargs):
        with surpress_stdout():
            result = function(*args, **kwargs)
        exit(result)

    return _wrapper
