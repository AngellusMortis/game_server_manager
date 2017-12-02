#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Console script for game_server_manager."""

import copy
import inspect
import json
import os
from subprocess import CalledProcessError

try:
    from json import JSONDecodeError as JSONError
except ImportError:
    JSONError = ValueError

import click
from gs_manager import servers
from gs_manager.utils import run_as_user, to_pascal_case, to_snake_case


class GSCommand(click.MultiCommand):
    context = None
    _config = None
    _commands = None

    @property
    def commands(self):
        if self._commands is None:
            possible_commands = inspect.getmembers(self.server)

            commands = {}
            for command in possible_commands:
                if isinstance(command[1], click.Command):
                    commands[command[0]] = command[1]
            self._commands = commands
        return self._commands

    @property
    def server(self):
        if self.context is None:
            raise click.ClickException('context not initalized yet')

        if self.context.obj is None:
            server_class = self._get_server_class()
            self.context.obj = server_class(self.context, options=self.config)
        return self.context.obj

    @property
    def config(self):
        if self.context is None:
            raise click.ClickException('context not initalized yet')

        if self._config is None:
            file_config, config_path = self._get_file_config()
            cli_config = self._get_cli_config()

            server_type = cli_config.get('type') or \
                file_config.get('type') or 'custom_screen'

            config = self._get_default_config(server_type)
            config.update(file_config)
            config.update(cli_config)
            self._save_config_file(config_path, config)
            self._config = config

        return self._config

    def _get_server_class(self, server_type=None):
        if server_type is None:
            server_type = self.config['type']

        try:
            server = getattr(servers, to_pascal_case(server_type))
        except AttributeError:
            raise click.BadParameter(
                'server of type "{}" does not exist'.format(server_type))
        else:
            return server

    def _get_cli_config(self):
        params = self.context.params
        config = {}

        for key in params:
            if params[key] is not None:
                config[key] = params[key]
        return config

    def _get_default_config(self, server_type):
        server_class = self._get_server_class(server_type)
        return server_class.defaults()

    def _get_file_config(self):
        config = {}
        config_filename = self.context.params.get('config') or \
            self.context.lookup_default('config') or '.gs_config.json'
        path = self._get_config_path(config_filename)

        config_path = os.path.join(path, config_filename)
        config_string = self._read_config_file(config_path)
        try:
            config = json.loads(config_string)
        except JSONError:
            raise click.ClickException('invalid configuration file')

        return config, config_path

    def _get_config_path(self, config_filename):
        path = self.context.params.get('path') or \
            self.context.lookup_default('path')

        # verify working path
        if path is not None:
            if os.path.isdir(path):
                path = os.path.abspath(path)
            else:
                raise click.BadParameter('path does not exist')
        else:
            path = self._find_config_path(config_filename)

        self.context.params['path'] = path
        return path

    def _find_config_path(self, config_filename):
        path = os.getcwd()

        search_path = path

        for x in range(5):
            if search_path == '/':
                break
            if os.path.isfile(os.path.join(search_path, config_filename)):
                path = search_path
                break
            search_path = os.path.abspath(os.path.join(search_path, os.pardir))

        return path

    def _read_config_file(self, config_path):
        config_string = '{}'

        if os.path.isfile(config_path):
            with open(config_path, 'r') as config_file:
                config_string = config_file.read().replace('\n', '')

        return config_string

    def _save_config_file(self, config_path, config):
        if self.context.params.get('save'):
            defaults = self._get_default_config(config['type'])
            config_copy = copy.deepcopy(config)

            # do not save exclusions
            server_class = self._get_server_class(config['type'])
            for key in server_class.excluded_from_save():
                if key in config_copy:
                    del config_copy[key]

            # do not save config options that are save as default
            for key, value in list(config_copy.items()):
                if value == defaults.get(key):
                    del config_copy[key]

            config_json = json.dumps(
                config_copy, sort_keys=True, indent=4, separators=(',', ': '))

            try:
                run_as_user(
                    config['user'],
                    'echo \'{}\' > \'{}\''
                    .format(config_json, config_path))
            except CalledProcessError as ex:
                raise click.ClickException(
                    'could not save config file (perhaps bad user?)')

    def list_commands(self, context):
        self.context = context
        commands = list(self.commands.keys())
        commands.sort()
        return commands

    def get_command(self, context, name):
        self.context = context

        if name in self.commands:
            return self.commands[name]
        return None


def get_types():
    server_classes = inspect.getmembers(servers, predicate=inspect.isclass)
    types = []
    for server in server_classes:
        types.append(to_snake_case(server[0]))
    return types


@click.group(cls=GSCommand, chain=True)
@click.option('-p', '--path',
              type=click.Path(),
              help='Starting directory. If empty, it uses current directory')
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
@click.option('-n', '--name',
              type=str,
              help='Name of gameserver screen service, must be unique')
@click.option('-u', '--user',
              type=str,
              help='User to run gameserver as')
@click.option('-d', '--debug',
              is_flag=True)
def main(*args, **kwargs):
    """Console script for game_server_manager."""
    pass


if __name__ == "__main__":
    main()
