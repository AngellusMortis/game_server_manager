#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Console script for game_server_manager."""
import inspect

import click

from gs_manager.command import DEFAULT_CONFIG, Config, ConfigCommandClass
from gs_manager.command.types import Server, ServerClass
from gs_manager.logger import get_logger
from gs_manager.servers import EmptyServer


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

    if isinstance(context.obj, EmptyServer):
        server: EmptyServer = context.obj
        config: Config = server.config

        logger.debug("Initial Server Config:")
        logger.debug(config.__dict__)

        all_members = inspect.getmembers(server)
        subcommands = []
        for member in all_members:
            if isinstance(member[1], click.Command):
                main.add_command(member[1], name=member[0])
                subcommands.append(member[0])
        logger.debug(f"Found subcommands:")
        logger.debug(subcommands)
    else:
        config: Config = context.obj

    if help or context.invoked_subcommand is None:
        click.echo(context.get_help())

    if save:
        config.save_config()


if __name__ == "__main__":
    main()
