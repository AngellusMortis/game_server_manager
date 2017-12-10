import click
from functools import update_wrapper


def _instance_wrapper(original_command, all_callback):
    def _wrapper(*args, **kwargs):
        context = click.get_current_context()
        config = context.obj.config
        logger = context.obj.logger
        context.obj.context = context

        config.add_cli_config(kwargs)

        logger.debug(
            'command start: {}'.format(context.command.name))

        if config['current_instance'] is not None and \
                not context.obj.supports_multi_instance:
            raise click.ClickException(
                '{} does not support multiple instances'
                .format(config['name']))
        elif config['current_instance'] is None and \
                len(config['instance_overrides'].keys()) and \
                context.obj.supports_multi_instance:
            logger.debug('no instance specific, but one found, adding...')
            config['current_instance'] = \
                list(config['instance_overrides'].keys())[0]

        if config['current_instance'] == '@all':
            return all_callback(context, *args, **kwargs)
        elif config['current_instance'] is not None:
            logger.debug('adding instance name to name...')
            config['name'] = '{}_{}'.format(
                config['name'], config['current_instance'])

        result = original_command(*args, **kwargs)
        return result

    return _wrapper


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
        elif len(config['instance_overrides'].keys()) > 0:
            results = []
            for instance_name in config.get_instances():
                logger.debug(
                    'running status for instance: {}'
                    .format(instance_name))

                kwargs['current_instance'] = instance_name
                kwargs['multi'] = True
                config.add_cli_config(kwargs)
                result = original_command(*args, **kwargs)
                results.append(result)
            return results
        else:
            logger.debug(
                'no valid instances found, removing current_instance...')
            config['current_instance'] = None

    wrapper_function = _instance_wrapper(original_command, all_callback)
    command.callback = update_wrapper(wrapper_function, original_command)
    return command
