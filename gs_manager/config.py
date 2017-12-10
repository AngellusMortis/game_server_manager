import copy
import json
import logging
import os
import re
from subprocess import CalledProcessError

import click
from gs_manager import servers
from gs_manager.logger import ClickLogger
from gs_manager.utils import run_as_user, to_pascal_case, write_as_user

try:
    from json import JSONDecodeError as JSONError
except ImportError:
    JSONError = ValueError

DEFAULT_SERVER_TYPE = 'base'


class Config(object):

    _context = None
    _filename = '.gs_config.json'
    _path = None

    _default_config = {}
    _file_config = {}
    _global_cli_config = {}
    _cli_config = {}

    _instances = {}

    _final_config = None

    def __init__(self, context):
        self._context = context
        self._filename = self._context.params.get('config') or \
            self._context.lookup_default('config') or \
            self._filename
        self._path = self._get_config_path()

        # get initial configs
        self._file_config = self._get_file_config()
        self._global_cli_config = self._get_cli_config(self._context.params)

        # get server default configs
        self._default_config = self._get_default_config()
        self._final_config = None

        self._validate_config()

    def __len__(self):
        self._set_final_config()
        return self._final_config.__len__()

    def __length_hint__(self):
        self._set_final_config()
        if hasattr(self._final_config, '__length_hint__'):
            return self._final_config.__length_hint__()
        return None

    def __getitem__(self, key):
        self._set_final_config()
        return self._final_config.__getitem__(key)

    def __missing__(self, key):
        self._set_final_config()
        return self._final_config.__missing__(key)

    def __setitem__(self, key, value):
        self._set_final_config()
        return self._final_config.__setitem__(key, value)

    def __delitem__(self, key):
        self._set_final_config()
        return self._final_config.__delitem__(key)

    def __iter__(self):
        self._set_final_config()
        return self._final_config.__iter__()

    def __reversed__(self):
        self._set_final_config()
        return self._final_config.__reversed__()

    def __contains__(self, item):
        self._set_final_config()
        return self._final_config.__contains__(item)

    def items(self):
        self._set_final_config()
        return self._final_config.items()

    def keys(self):
        self._set_final_config()
        return self._final_config.keys()

    def values(self):
        self._set_final_config()
        return self._final_config.values()

    def _make_final_config(self, instance_name=None):
        config = self._default_config.copy()
        config.update(self._file_config)
        config.update(self._global_cli_config)

        if instance_name is not None:
            instance_config = self['instance_overrides'].get(instance_name)
            if instance_config is not None:
                for key, value in list(instance_config.items()):
                    if isinstance(value, dict):
                        config[key].update(value)
                        del instance_config[key]
                config.update(instance_config)

        cli_config = self._cli_config.copy()
        if 'instance_overrides' in cli_config:
            config['instance_overrides'].update(
                cli_config['instance_overrides'])
            del cli_config['instance_overrides']
        config.update(cli_config)

        if instance_name is not None:
            config['current_instance'] = instance_name
            del config['instance_overrides']

        config['type'] = config.get('type') or \
            DEFAULT_SERVER_TYPE
        config['path'] = self._path

        if 'save' not in config:
            config['save'] = False
        if 'debug' not in config:
            config['debug'] = False

        return config

    def _set_final_config(self):
        if self._final_config is None:
            self._instances = {}
            self._final_config = self._make_final_config()

            if 'user' in self._final_config:
                logger = self.get_logger()
                logger.debug('config: ')
                logger.debug(self._final_config)

    def _get_param_obj(self, param_name):
        param = None
        for p in self._context.command.params:
            if p.name == param_name:
                param = p
                break
        return param

    def _get_config_path(self):
        path = self._context.params.get('path') or \
            self._context.lookup_default('path')

        # verify working path
        if path is not None:
            if os.path.isdir(path):
                path = os.path.abspath(path)
            else:
                raise click.BadParameter(
                    'path does not exist', self._context,
                    self._get_param_obj('path'))
        else:
            path = self._find_config_path()

        return path

    def _find_config_path(self):
        # verify user has not provide a path to a exist file
        if os.path.isfile(self._filename):
            path = os.path.abspath(self._filename)
            # update filename to only contain the filename
            self._filename = os.path.basename(path)
            return os.path.dirname(path)

        path = os.getcwd()
        search_path = path

        for x in range(5):
            if search_path == '/':
                break
            if os.path.isfile(os.path.join(search_path, self._filename)):
                path = search_path
                break
            search_path = os.path.abspath(os.path.join(search_path, os.pardir))

        return path

    def _get_file_config(self):
        config = {}

        config_path = os.path.join(self._path, self._filename)
        config_json = self._read_config_file(config_path)
        try:
            config = json.loads(config_json)
        except JSONError:
            raise click.BadParameter(
                'invalid configuration file: {}'.format(config_path),
                self._context, self._get_param_obj('config'))

        return config

    def _get_cli_config(self, params):
        config = {}

        for key in params:
            if params[key] is not None and params[key] is not False and \
                    not (hasattr(params[key], '__iter__') and
                         len(params[key]) == 0):
                config[key] = params[key]
        return config

    def _get_default_config(self, server_type=None):
        return self.get_server_class().defaults()

    def _read_config_file(self, config_path):
        config_json = '{}'

        if os.path.isfile(config_path):
            with open(config_path, 'r') as config_file:
                config_json = config_file.read().replace('\n', '')

        return config_json

    def get_logger(self):
        logging.setLoggerClass(ClickLogger)
        logger = logging.getLogger('gs_manager')

        if not logger.hasHandlers():
            log_dir = os.path.join(self['path'], 'logs')
            if not os.path.isdir(log_dir):
                run_as_user(self['user'], 'mkdir {}'.format(log_dir))

            log_path = os.path.join(log_dir, 'gs_manager.log')
            log_file = None

            try:
                log_file = open(log_path, 'a')
            except PermissionError:
                log_file = open(os.devnull, 'w')

            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler = logging.StreamHandler(log_file)
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.propagate = False
            logger.click_debug = self['debug']
        return logger

    def get_server_class(self, server_type=None):
        if server_type is None:
            server_type = self['type']

        try:
            server = getattr(servers, to_pascal_case(server_type))
        except AttributeError:
            raise click.BadParameter(
                'server of type "{}" does not exist'.format(server_type),
                self._context, self._get_param_obj('type'))
        else:
            return server

    def _validate_config(self):
        for key, value in self.items():
            if isinstance(value, str):
                self._validate_string_param(key, value)

    def _validate_string_param(self, name, param):
        if len(param) > 0:
            match = re.match('^[^|]+$', param, re.I)
            if not match or not match.group() == param:
                raise click.BadParameter(
                    '{} cannot contain a | character'.format(name),
                    self._context, self._get_param_obj(name))

    def save(self):
        self._set_final_config()
        config_copy = copy.deepcopy(self._final_config)
        logger = self.get_logger()

        # add default values to config
        for key, value in self._default_config.items():
            if key not in config_copy:
                logger.debug('adding default value for key: {}'.format(key))
                config_copy[key] = value

        # do not save exclusions
        server_class = self.get_server_class()
        for key in server_class.excluded_from_save():
            if key in config_copy:
                logger.debug('removing excluded saved key: {}'.format(key))
                del config_copy[key]

        if not server_class.supports_multi_instance:
            logger.debug('removing instance_overrides')
            del config_copy['instance_overrides']

        logger.debug('saved config:')
        logger.debug(config_copy)

        config_json = json.dumps(
            config_copy, sort_keys=True, indent=4, separators=(',', ': '))

        config_path = os.path.join(self._path, self._filename)
        try:
            write_as_user(self['user'], config_path, config_json)
        except CalledProcessError as ex:
            raise click.ClickException(
                'could not save config file (perhaps bad user?)')

    def set_cli_config(self, config):
        self._final_config = None
        self._cli_config = self._get_cli_config(config)

    def add_cli_config(self, config):
        self._final_config = None
        cli_config = self._get_cli_config(config)
        self._cli_config.update(cli_config)

    def get_instance_config(self, name=None):
        if self._instances.get(name) is None:
            if name is None and len(self['instance_overrides'].keys()) > 0:
                name = list(self['instance_overrides'].keys())[0]
            config = self._make_final_config(name)
            if name is not None:
                config['name'] = '{}_{}'.format(config['name'], name)
            self._instances[name] = config
        return self._instances[name]

    def get_instances(self):
        return self['instance_overrides'].keys()
