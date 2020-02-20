import time
from functools import update_wrapper
from multiprocessing import Process

import click
from gs_manager.utils import surpress_stdout
from gs_manager.config import Config


def _instance_wrapper(command, all_callback):
    """ wraps command callback and adds instance logic """

    def _wrapper(*args, **kwargs):
        context = click.get_current_context()
        server = context.obj
        instance = server.config["current_instance"]
        all_instances = server.config.get_instances()

        server.context = context
        server.config.add_cli_config(kwargs)
        server.config["current_instance"] = instance

        server.logger.debug("command start: {}".format(context.command.name))

        if instance is not None and not server.supports_multi_instance:
            raise click.BadParameter(
                "{} does not support multiple instances".format(server.config["name"]),
                context,
            )
        elif (
            instance is None
            and len(all_instances) > 0
            and server.supports_multi_instance
        ):

            server.logger.debug("no instance specified, setting...")
            server.config["current_instance"] = all_instances[0]

        if instance == "@all":
            return all_callback(context, *args, **kwargs)
        elif instance is not None:
            server.logger.debug("adding instance to name...")
            server.config["name"] = "{}_{}".format(
                server.config["name"], server.config["current_instance"]
            )

        result = command(*args, **kwargs)
        return result

    return _wrapper


def _run_sync(context, callback, *args, **kwargs):
    """ runs command for each instance in @all synchronously """
    config = context.obj.config
    logger = context.obj.logger
    results = []
    for instance_name in config.get_instances():
        logger.debug(
            "running {} for instance: {}".format(context.command.name, instance_name)
        )

        config["current_instance"] = instance_name
        config["multi"] = True
        kwargs.update(context.params)

        result = callback(*args, **kwargs)
        results.append(result)
    return results


def _run_parallel(context, callback):
    """ runs command for each instance in @all in parallel """
    config = context.obj.config
    logger = context.obj.logger
    processes = []

    logger.info(
        "running {} for {} @all completed...".format(
            context.command.name, config["name"]
        )
    )

    # create process for each instances
    for instance_name in config.get_instances():
        logger.debug(
            "spawning {} for instance: {}".format(context.command.name, instance_name)
        )
        copy_config = Config(context)
        copy_config["current_instance"] = instance_name
        copy_config["multi"] = True

        context.obj.config = copy_config

        p = Process(
            target=surpress(callback), kwargs=dict(context.params), daemon=True,
        )
        p.start()
        processes.append(p)

    bar = click.progressbar(length=len(processes), show_eta=False)
    completed = None
    previous_completed = None
    not_done = True
    while not_done:
        logger.debug("processes: {}".format(processes))
        alive_list = [p.is_alive() for p in processes]
        logger.debug("processes alive: {}".format(alive_list))
        not_done = any(alive_list)
        completed = sum([int(not c) for c in alive_list])
        if not completed == previous_completed:
            bar.update(completed)
            previous_completed = completed
        time.sleep(1)

    logger.success(
        "\n{} {} @all completed".format(context.command.name, config["name"])
    )
    return [p.exitcode for p in processes]


def single_instance(command):
    """
    decorator for a click command to enforce a single instance or zero
    instances are passed in
    """
    original_command = command.callback

    def all_callback(context, *args, **kwargs):
        raise click.ClickException("{} does not support @all".format(command.name))

    wrapper_function = _instance_wrapper(original_command, all_callback)
    command.callback = update_wrapper(wrapper_function, original_command)
    return command


def multi_instance(command):
    """
    decorator for a click command to allow multiple instances to be passed in
    """
    original_command = command.callback

    def all_callback(context, *args, **kwargs):
        config = context.obj.config
        logger = context.obj.logger

        if config["foreground"]:
            raise click.ClickException("cannot use @all with -fg option")
        elif len(config.get_instances()) > 0:
            if config["parallel"]:
                _run_parallel(context, original_command)
            else:
                _run_sync(context, original_command, *args, **kwargs)
        else:
            logger.debug("no valid instances found, removing current_instance...")
            config["current_instance"] = None

    wrapper_function = _instance_wrapper(original_command, all_callback)
    command.callback = update_wrapper(wrapper_function, original_command)
    return command


def surpress(function):
    """
    decorator to surpress all stdout for a method
    """

    def _wrapper(*args, **kwargs):
        with surpress_stdout():
            result = function(*args, **kwargs)
        return result

    return _wrapper
