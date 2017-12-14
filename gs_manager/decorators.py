import time
from functools import update_wrapper
from multiprocessing import Process

import click
from gs_manager.utils import surpress_stdout
from gs_manager.config import Config


def _instance_wrapper(command, all_callback):
    def _wrapper(*args, **kwargs):
        context = click.get_current_context()
        server = context.obj
        instance = server.config['current_instance']
        all_instances = server.config.get_instances()

        server.context = context
        server.config.add_cli_config(kwargs)
        server.logger.debug(
            'command start: {}'.format(context.command.name))

        if instance is not None and not server.supports_multi_instance:
            raise click.BadParameter(
                '{} does not support multiple instances'
                .format(server.config['name']), context)
        elif instance is None and len(all_instances) > 0 and \
                server.supports_multi_instance:

            server.logger.debug(
                'no instance specific, but one found, adding...')
            server.config['current_instance'] = all_instances[0]

        if instance == '@all':
            return all_callback(context, *args, **kwargs)
        elif instance is not None:
            server.logger.debug('adding instance name to name...')
            server.config['name'] = '{}_{}'.format(
                server.config['name'], server.config['current_instance'])

        result = command(*args, **kwargs)
        return result
    return _wrapper


def _run_sync(context, command):
    config = context.obj.config
    logger = context.obj.logger
    results = []
    for instance_name in config.get_instances():
        logger.debug(
            'running {} for instance: {}'
            .format(command.name, instance_name))

        config['current_instance'] = instance_name
        config['multi'] = True
        result = command(**dict(context.params))
        results.append(result)
    return results


def _run_parallel(context, command):
    config = context.obj.config
    logger = context.obj.logger
    processes = []

    logger.info(
        'running {} for {} @all completed...'
        .format(command.name, config['name'])
    )

    # create process for each instances
    for instance_name in config.get_instances():
        logger.debug(
            'spawning {} for instance: {}'
            .format(command.name, instance_name)
        )
        copy_config = Config(context)
        copy_config['current_instance'] = instance_name
        copy_config['multi'] = True

        context.obj.config = copy_config

        p = Process(
            target=surpress(command),
            kwargs=dict(context.params),
            daemon=True,
        )
        p.start()
        processes.append(p)

        bar = click.progressbar(length=len(processes))
        completed = None
        previous_completed = None
        not_done = True
        while not_done:
            alive_list = [p.is_alive() for p in processes]
            logger.debug('processes alive: {}'.format(alive_list))
            not_done = any(alive_list)
            completed = sum([int(not c) for c in alive_list])
            if not completed == previous_completed:
                bar.update(completed)
                previous_completed = completed
            time.sleep(1)

    logger.success(
        '\n{} {} @all completed'
        .format(command.name, config['name'])
    )
    return [p.exitcode for p in processes]


def single_instance(command):
    original_command = command.callback

    def all_callback(context, *args, **kwargs):
        raise click.ClickException(
            '{} does not support @all'.format(command.name))

    wrapper_function = _instance_wrapper(original_command, all_callback)
    command.callback = update_wrapper(wrapper_function, original_command)
    return command


def multi_instance(command):
    original_command = command.callback

    def all_callback(context, *args, **kwargs):
        config = context.obj.config
        logger = context.obj.logger

        if config['foreground']:
            raise click.ClickException(
                'cannot use @all with -fg option')
        elif len(config.get_instances()) > 0:
            if config['parallel']:
                _run_parallel(context, original_command)
            else:
                _run_sync(context, command)
        else:
            logger.debug(
                'no valid instances found, removing current_instance...')
            config['current_instance'] = None

    wrapper_function = _instance_wrapper(original_command, all_callback)
    command.callback = update_wrapper(wrapper_function, original_command)
    return command


def surpress(function):
    def new_func(*args, **kwargs):
        with surpress_stdout():
            result = function(*args, **kwargs)
        return result

    return new_func
