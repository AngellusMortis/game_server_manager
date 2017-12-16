import copy
import json
import os
from subprocess import CalledProcessError

import click
from gs_manager.logger import get_logger
from gs_manager.utils import get_param_obj, get_server_class, write_as_user
from gs_manager.validators import validate_string_value

from .dict_config import DictConfig

try:
    from json import JSONDecodeError as JSONError
except ImportError:
    JSONError = ValueError

DEFAULT_SERVER_TYPE = 'screen'


class Config(DictConfig):

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
        self._global_cli_config = \
            self._get_cli_config(self._context.params)

        # get server default configs
        self._default_config = self._get_default_config()
        self._final_config = None

        self._validate_config()

    def _add_instance(self, config, instance_name):
        if instance_name is not None:
            instance = self['instance_overrides'].get(instance_name)
            if instance is not None:
                for key, value in list(instance.items()):
                    if isinstance(value, dict):
                        config[key].update(value)
                        del instance[key]
                config.update(instance)

    def _add_cli_config(self, config):
        cli_config = self._cli_config.copy()
        if 'instance_overrides' in cli_config:
            config['instance_overrides'].update(
                cli_config['instance_overrides'])
            del cli_config['instance_overrides']
        config.update(cli_config)

    def _make_final_config(self, instance_name=None):
        config = self._default_config.copy()
        config.update(self._file_config)
        config.update(self._global_cli_config)

        self._add_instance(config, instance_name)
        self._add_cli_config(config)

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
                logger = get_logger(self)
                logger.debug('config: ')
                logger.debug(self._final_config)

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
                    get_param_obj(self._context, 'path'))
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
                self._context, get_param_obj(self._context, 'config'))

        return config

    def _is_empty_option(self, param):
        return param is None or \
            param is False or \
            (hasattr(param, '__iter__') and len(param) == 0)

    def _get_cli_config(self, params):
        config = {}

        for key in params:
            if not self._is_empty_option(params[key]):
                config[key] = params[key]
        return config

    def _get_default_config(self, server_type=None):
        return get_server_class(self, self._context).defaults()

    def _read_config_file(self, config_path):
        config_json = '{}'

        if os.path.isfile(config_path):
            with open(config_path, 'r') as config_file:
                config_json = config_file.read().replace('\n', '')

        return config_json

    def _validate_config(self):
        for key, value in self.items():
            if isinstance(value, str):
                validate_string_value(
                    self._context,
                    get_param_obj(self._context, key),
                    value,
                )

    def _add_default_keys(self, config):
        logger = get_logger(self)
        for key, value in self._default_config.items():
            if key not in config:
                logger.debug('adding default value for key: {}'.format(key))
                config[key] = value

    def _delete_excluded_keys(self, config):
        logger = get_logger(self)
        server_class = get_server_class(self, self._context)
        for key in server_class.excluded_from_save():
            if key in config:
                logger.debug('removing excluded saved key: {}'.format(key))
                del config[key]

        if not server_class.supports_multi_instance:
            logger.debug('removing instance_overrides')
            del config['instance_overrides']

    def save(self):
        self._set_final_config()
        config = copy.deepcopy(self._final_config)
        logger = get_logger(self)

        self._add_default_keys(config)
        self._delete_excluded_keys(config)

        logger.debug('saved config:')
        logger.debug(config)

        config_json = json.dumps(
            config, sort_keys=True,
            indent=4, separators=(',', ': '),
        )

        config_path = os.path.join(self._path, self._filename)
        try:
            write_as_user(self['user'], config_path, config_json)
        except CalledProcessError:
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
        return list(self['instance_overrides'].keys())
