#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Console script for game_server_manager."""

import inspect
from functools import update_wrapper

import click
from gs_manager import servers
from gs_manager.config import Config
from gs_manager.utils import to_snake_case


def get_types():
    server_classes = inspect.getmembers(servers, predicate=inspect.isclass)
    types = []
    for server in server_classes:
        types.append(to_snake_case(server[0]))
    return types


@click.group(chain=True, invoke_without_command=True, add_help_option=False)
@click.option('-p', '--path',
              type=click.Path(),
              help='Starting directory. If empty, it uses current directory. '
                   'Will automatically look in upto 5 parent directories for '
                   'config as well')
@click.option('-c', '--config',
              type=click.Path(),
              help=('Path to JSON config file. Config file options override '
                    'default ones. CLI options override config file options. '
                    'Ignored if file does not exist.'))
@click.option('-s', '--save',
              is_flag=True,
              help=('Save config to JSON file after loading'))
@click.option('-t', '--type',
              type=click.Choice(get_types()),
              help='Type of gameserver to run')
@click.option('-d', '--debug',
              is_flag=True,
              help='Show extra debug information')
@click.option('-h', '--help',
              is_flag=True,
              help='Shows this message and exit')
@click.option('-u', '--user',
              type=str,
              help='User to run gameserver as')
@click.pass_context
def main(context, *args, **kwargs):
    """ Console script for game_server_manager """

    config = Config(context)
    logger = config.get_logger()
    context.obj = config.get_server_class()(context, config)

    possible_commands = inspect.getmembers(context.obj)
    for command in possible_commands:
        if isinstance(command[1], click.Command):
            logger.debug('adding command {}...'.format(command[0]))
            main.add_command(command_wrap(context, command[1]))

    if kwargs['help'] or context.invoked_subcommand is None:
        click.echo(context.get_help())
        check_for_save(context)
        exit(0)


def check_for_save(context):
    if context.obj.config['save']:
        context.obj.logger.debug('saving config...')
        context.obj.config.save()


def command_wrap(context, command):
    orig = command.callback

    options = context.obj.global_options()['all']
    if context.obj.supports_multi_instance:
        options += context.obj.global_options()['instance_enabled']

    for option in options:
        command.params.append(
            click.Option(**option))

    def new_func(*args, **kwargs):
        # add local cli config
        if len(kwargs.keys()) > 0:
            context.obj.logger.debug('adding cli config...')
            context.obj.config.add_cli_config(kwargs)
        result = orig(*args, **kwargs)
        check_for_save(context)
        return result

    command.callback = update_wrapper(new_func, orig)
    return command


if __name__ == "__main__":
    main()
