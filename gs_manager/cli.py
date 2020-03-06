#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Console script for game_server_manager."""
import inspect

import click

from gs_manager.command import DEFAULT_CONFIG, Config, ConfigCommandClass
from gs_manager.command.types import Server, ServerClass
from gs_manager.logger import get_logger
from gs_manager.servers import EmptyServer
import logging


@click.group(
    cls=ConfigCommandClass,
    chain=True,
    invoke_without_command=True,
    add_help_option=False,
)
# Generic Parameters
@click.option(
    "-c",
    "--config-file",
    type=click.Path(),
    default=DEFAULT_CONFIG,
    help="Config file to read vars from",
)
@click.option(
    "-p",
    "--server-path",
    type=click.Path(),
    default=Config.server_path,
    help="The root path for the game server",
)
@click.option(
    "-s",
    "--save",
    is_flag=True,
    help=("Save config to YML file after loading"),
)
@click.option(
    "-d", "--debug", is_flag=True, help="Show extra debug information"
)
@click.option(
    "-t",
    "--server-type",
    type=ServerClass(),
    help="Type of gameserver to run",
    default=Config.server_type,
)
@click.option("-h", "--help", is_flag=True, help="Shows this message and exit")
@click.pass_context
def main(
    context: click.Context,
    config_file: str,
    server_path: str,
    save: bool,
    debug: bool,
    server_type: Server,
    help: bool,
    **kwargs,
):
    """ Console script for gs_manager """

    logger = get_logger()

    logger.debug("Initial Context:")
    logger.debug(context.params)
    logger.debug(context.args)

    if isinstance(context.obj, EmptyServer):
        server: EmptyServer = context.obj
        config: Config = server.config

        logger.debug("Main Server Config:")
        logger.debug(config.__dict__)

        for name, instance_config in config.instances.items():
            logger.debug(f"Instance Server Config ({name}):")
            logger.debug(instance_config.__dict__)

        add_subcommands(server, logger)
    else:
        config: Config = context.obj

    if help or context.invoked_subcommand is None:
        click.echo(context.get_help())

    if save:
        config.save_config()


def add_global_options(
    server: EmptyServer,
    command: click.Command,
    logger: logging.getLoggerClass(),
):
    options = server.config.global_options["all"]
    if server.supports_multi_instance:
        options += server.config.global_options["instance_enabled"]

    for option in options:
        command.params.append(click.Option(**option))

    logger.debug("Found global options:")
    logger.debug(options)


def add_subcommands(server: EmptyServer, logger: logging.getLoggerClass()):
    all_members = inspect.getmembers(server)
    subcommands = []
    for member in all_members:
        if isinstance(member[1], click.Command):
            add_global_options(server, member[1], logger)

            main.add_command(member[1], name=member[0])
            subcommands.append(member[0])
    logger.debug("Found subcommands:")
    logger.debug(subcommands)


if __name__ == "__main__":
    main()
