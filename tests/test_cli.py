import os
from subprocess import CalledProcessError

import click
import pytest
from gs_manager.cli import GSCommand, get_types
from gs_manager.servers import CustomScreen
from mock import Mock, mock_open, patch

TEST_CONFIG = '{"test": \n"test"}'


@patch('gs_manager.cli.servers')
def test_get_types(mock_servers):
    mock_servers.CustomScreen = object
    mock_servers.SomeServer = object

    types = get_types()

    assert len(types) == 2
    assert types[0] == 'custom_screen'
    assert types[1] == 'some_server'


@patch('gs_manager.cli.servers')
def test_get_types_none(mock_servers):
    types = get_types()

    assert len(types) == 0


def test_requires_context():
    gs = GSCommand()

    with pytest.raises(click.ClickException):
        gs.server

    with pytest.raises(click.ClickException):
        gs.config


def test_property_caches():
    test_config = {'test': 'test'}
    test_commands = ['command1', 'command2']
    test_server = Mock()

    gs = GSCommand()
    gs.context = click.Context(Mock(), obj=test_server)
    gs._config = test_config
    gs._commands = test_commands

    assert gs.config == test_config
    assert gs.commands == test_commands
    assert gs.server == test_server


def test_get_cli_config():
    test_params = {'test': 'test', 'test2': None}

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = test_params
    config = gs._get_cli_config()

    assert len(config.keys()) == 1
    assert config['test'] == 'test'


@patch('gs_manager.cli.os')
def test_read_config_file_no_file(mock_os):
    test_path = 'test'
    mock_os.path.isfile.return_value = False

    gs = GSCommand()
    config_string = gs._read_config_file(test_path)

    mock_os.path.isfile.assert_called_with(test_path)
    assert config_string == '{}'


@patch('gs_manager.cli.os')
@patch('gs_manager.cli.open', mock_open(read_data=TEST_CONFIG))
def test_read_config_file(mock_os):
    mock_os.path.isfile.return_value = True

    gs = GSCommand()
    config_string = gs._read_config_file('test')

    assert config_string == TEST_CONFIG.replace('\n', '')


@patch('gs_manager.cli.os')
def test_find_config_path_same_path(mock_os):
    test_dir = '/srv'
    test_file = 'test.json'
    mock_os.getcwd.return_value = test_dir
    mock_os.path.isfile.return_value = True

    gs = GSCommand()
    config_path = gs._find_config_path(test_file)

    assert config_path == test_dir


@patch('gs_manager.cli.os')
def test_find_config_path_multi_up(mock_os):
    test_dir = '/srv/one/two'
    test_file = 'test.json'
    mock_os.getcwd.return_value = test_dir
    mock_os.path.isfile.side_effect = [False, False, True]
    mock_os.pardir = os.pardir
    mock_os.path.join = os.path.join
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    config_path = gs._find_config_path(test_file)

    assert config_path == '/srv'


@patch('gs_manager.cli.os')
def test_find_config_path_not_found_root(mock_os):
    test_dir = '/srv/one'
    test_file = 'test.json'
    mock_os.getcwd.return_value = test_dir
    mock_os.path.isfile.return_value = False
    mock_os.pardir = os.pardir
    mock_os.path.join = os.path.join
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    config_path = gs._find_config_path(test_file)

    assert mock_os.path.isfile.call_count == 2
    assert config_path == test_dir


@patch('gs_manager.cli.os')
def test_find_config_path_not_found(mock_os):
    test_dir = '/srv/one/two/three/four/five'
    test_file = 'test.json'
    mock_os.getcwd.return_value = test_dir
    mock_os.path.isfile.side_effect = [False, False, False, False, False, True]
    mock_os.pardir = os.pardir
    mock_os.path.join = os.path.join
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    config_path = gs._find_config_path(test_file)

    assert mock_os.path.isfile.call_count == 5
    assert config_path == test_dir


@patch('gs_manager.cli.os')
def test_get_config_path_params(mock_os):
    test_dir = '/srv/../srv'
    mock_os.path.isdir.return_value = True
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'path': test_dir}
    path = gs._get_config_path('test.json')

    assert gs.context.params['path'] == '/srv'
    assert path == gs.context.params['path']


@patch('gs_manager.cli.os')
def test_get_config_path_default(mock_os):
    test_dir = '/srv'
    mock_os.path.isdir.return_value = True
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    gs.context = click.Context(Mock(), default_map={'path': test_dir})
    path = gs._get_config_path('test.json')

    assert gs.context.params['path'] == test_dir
    assert path == gs.context.params['path']


@patch('gs_manager.cli.os')
def test_get_config_path_bad_path(mock_os):
    test_dir = '/srv'
    mock_os.path.isdir.return_value = False

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'path': test_dir}

    with pytest.raises(click.BadParameter):
        gs._get_config_path('test.json')


@patch('gs_manager.cli.os')
def test_get_config_path_no_path(mock_os):
    test_dir = '/srv'
    mock_os.getcwd.return_value = test_dir
    mock_os.path.isfile.return_value = True

    gs = GSCommand()
    gs.context = click.Context(Mock())
    path = gs._get_config_path('test.json')

    assert gs.context.params['path'] == test_dir
    assert path == test_dir


@patch('gs_manager.cli.os')
@patch('gs_manager.cli.open', mock_open(read_data=TEST_CONFIG))
def test_get_file_config_params(mock_os):
    test_dir = '/srv'
    test_file = 'test.json'
    mock_os.getcwd.return_value = test_dir
    mock_os.isdir.return_value = True
    mock_os.path.isfile.return_value = True
    mock_os.path.join = os.path.join
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'config': test_file, 'path': test_dir}
    config, config_path = gs._get_file_config()

    assert config_path == os.path.join(test_dir, test_file)
    assert config == {'test': 'test'}


@patch('gs_manager.cli.os')
@patch('gs_manager.cli.open', mock_open(read_data=TEST_CONFIG))
def test_get_file_config_default(mock_os):
    test_dir = '/srv'
    test_file = 'test.json'
    mock_os.getcwd.return_value = test_dir
    mock_os.isdir.return_value = True
    mock_os.path.isfile.return_value = True
    mock_os.path.join = os.path.join
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    gs.context = click.Context(Mock(), default_map={'config': test_file})
    gs.context.params = {'path': test_dir}

    config, config_path = gs._get_file_config()

    assert config_path == os.path.join(test_dir, test_file)
    assert config == {'test': 'test'}


@patch('gs_manager.cli.os')
@patch('gs_manager.cli.open', mock_open(read_data=TEST_CONFIG))
def test_get_file_config_code(mock_os):
    test_dir = '/srv'
    mock_os.getcwd.return_value = test_dir
    mock_os.isdir.return_value = True
    mock_os.path.isfile.return_value = True
    mock_os.path.join = os.path.join
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'path': test_dir}

    config, config_path = gs._get_file_config()

    assert config_path == os.path.join(test_dir, '.gs_config.json')
    assert config == {'test': 'test'}


@patch('gs_manager.cli.os')
@patch('gs_manager.cli.open', mock_open(read_data='garba}e'))
def test_get_file_config_bad_data(mock_os):
    test_dir = '/srv'
    mock_os.getcwd.return_value = test_dir
    mock_os.isdir.return_value = True
    mock_os.path.isfile.return_value = True
    mock_os.path.join = os.path.join
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'path': test_dir}

    with pytest.raises(click.ClickException):
        gs._get_file_config()


@patch('gs_manager.cli.servers')
def test_get_server_class_exists(mock_servers):
    test_server = Mock()
    mock_servers.Test = test_server

    gs = GSCommand()
    server = gs._get_server_class('test')

    assert server == test_server


@patch('gs_manager.cli.servers', new_callable=object)
def test_get_server_class_none(mock_servers):
    gs = GSCommand()

    with pytest.raises(click.BadParameter):
        gs._get_server_class('test')


@patch('gs_manager.cli.servers')
def test_get_server_class_from_config(mock_servers):
    test_server = Mock()
    mock_servers.Test = test_server

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs._config = {'type': 'test'}
    server = gs._get_server_class('test')

    assert server == test_server


@patch('gs_manager.cli.servers')
def test_get_default_config(mock_servers):
    default_config = {'test': 'test'}
    test_server = Mock()
    test_server.defaults.return_value = default_config
    mock_servers.Test = test_server

    gs = GSCommand()
    config = gs._get_default_config('test')

    assert default_config == config


def test_save_config_file_no_save():
    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs._get_default_config = Mock()
    gs._save_config_file('', {})

    assert not gs._get_default_config.called


@patch('gs_manager.cli.run_as_user')
def test_save_config_no_config(mock_run):
    test_path = '/srv'
    test_config = {'user': 'root', 'type': 'custom_screen'}

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'save': True}
    gs._save_config_file(test_path, test_config)

    mock_run.assert_called_with('root', 'echo \'{}\' > \'/srv\'')


@patch('gs_manager.cli.servers')
@patch('gs_manager.cli.run_as_user')
def test_save_config_no_excluded(mock_run, mock_servers):
    test_server = Mock()
    test_server.excluded_from_save.return_value = ['user', 'type', 'save']
    test_server.defaults.return_value = []
    test_path = '/srv'
    test_config = {'user': 'root', 'type': 'test'}
    mock_servers.Test = test_server

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'save': True}
    gs._save_config_file(test_path, test_config)

    mock_run.assert_called_with('root', 'echo \'{}\' > \'/srv\'')


@patch('gs_manager.cli.servers')
@patch('gs_manager.cli.run_as_user')
def test_save_config_no_defaults(mock_run, mock_servers):
    test_server = Mock()
    test_server.excluded_from_save.return_value = ['save']
    test_server.defaults.return_value = {'user': 'root', 'type': 'test'}
    test_path = '/srv'
    test_config = {'user': 'root', 'type': 'test'}
    mock_servers.Test = test_server

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'save': True}
    gs._save_config_file(test_path, test_config)

    mock_run.assert_called_with('root', 'echo \'{}\' > \'/srv\'')


@patch('gs_manager.cli.run_as_user')
def test_save_config_with_config(mock_run):
    test_path = '/srv'
    test_config = {'user': 'root', 'type': 'custom_screen', 'test': 'test'}

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'save': True}
    gs._save_config_file(test_path, test_config)

    mock_run.assert_called_with(
        'root', 'echo \'{\n    "test": "test"\n}\' > \'/srv\'')


@patch('gs_manager.cli.run_as_user')
def test_save_config_failed_to_save(mock_run):
    test_path = '/srv'
    test_config = {'user': 'root', 'type': 'custom_screen'}
    mock_run.side_effect = CalledProcessError(1, 'test', None)

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'save': True}

    with pytest.raises(click.ClickException):
        gs._save_config_file(test_path, test_config)


@patch('gs_manager.cli.servers')
def test_config_cli_type(mock_servers):
    test_server = Mock()
    test_server.defaults.return_value = {'test': 'test'}
    mock_servers.Test = test_server

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'type': 'test'}
    config = gs.config

    assert config['test'] == 'test'


@patch('gs_manager.cli.os')
@patch('gs_manager.cli.open', mock_open(read_data='{"test": "test"}'))
def test_config_file_type(mock_os):
    mock_os.getcwd.return_value = '/srv'
    mock_os.path.isfile.return_value = True
    mock_os.path.join = os.path.join
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    gs.context = click.Context(Mock())
    config = gs.config

    assert config['test'] == 'test'


@patch('gs_manager.cli.servers')
def test_config_no_type(mock_servers):
    test_server = Mock()
    test_server.defaults.return_value = {'test': 'test'}
    mock_servers.CustomScreen = test_server

    gs = GSCommand()
    gs.context = click.Context(Mock())
    config = gs.config

    assert config['test'] == 'test'


@patch('gs_manager.cli.os')
@patch('gs_manager.cli.servers')
@patch('gs_manager.cli.open', mock_open(read_data='{"test": "test2"}'))
def test_config_file_overrides_default(mock_servers, mock_os):
    test_server = Mock()
    test_server.defaults.return_value = {'test': 'test'}
    mock_servers.CustomScreen = test_server
    mock_os.getcwd.return_value = '/srv'
    mock_os.path.isfile.return_value = True
    mock_os.path.join = os.path.join
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    gs.context = click.Context(Mock())
    config = gs.config

    assert config['test'] == 'test2'


@patch('gs_manager.cli.os')
@patch('gs_manager.cli.servers')
@patch('gs_manager.cli.open', mock_open(read_data='{"test": "test2"}'))
def test_config_cli_overrides_file(mock_servers, mock_os):
    test_server = Mock()
    test_server.defaults.return_value = {'test': 'test'}
    mock_servers.CustomScreen = test_server
    mock_os.getcwd.return_value = '/srv'
    mock_os.path.isfile.return_value = True
    mock_os.path.join = os.path.join
    mock_os.path.abspath = os.path.abspath

    gs = GSCommand()
    gs.context = click.Context(Mock())
    gs.context.params = {'test': 'test3'}
    config = gs.config

    assert config['test'] == 'test3'


def test_server():

    gs = GSCommand()
    gs._config = {'type': 'custom_screen'}
    gs.context = click.Context(Mock())

    assert isinstance(gs.server, CustomScreen)


def test_commands():
    mock_server = Mock()
    mock_server.command1 = click.Command('command1')
    mock_server.command2 = click.Command('command2')

    gs = GSCommand()
    gs.context = click.Context(Mock(), obj=mock_server)

    commands = gs.commands

    assert len(commands.keys()) == 2
    assert commands['command1'] == mock_server.command1
    assert commands['command2'] == mock_server.command2


def test_list_commands():
    mock_server = Mock()
    mock_server.command1 = click.Command('command1')
    mock_server.command2 = click.Command('command2')
    test_context = click.Context(Mock(), obj=mock_server)

    gs = GSCommand()
    commands = gs.list_commands(test_context)

    assert len(commands) == 2
    assert commands[0] == 'command1'
    assert commands[1] == 'command2'


def test_list_commands_none():
    mock_server = Mock()
    test_context = click.Context(Mock(), obj=mock_server)

    gs = GSCommand()
    commands = gs.list_commands(test_context)

    assert len(commands) == 0


def test_get_command_missing():
    mock_server = Mock()
    test_context = click.Context(Mock(), obj=mock_server)

    gs = GSCommand()
    command = gs.get_command(test_context, 'test')

    assert command is None


def test_get_command():
    mock_server = Mock()
    mock_server.command1 = click.Command('command1')
    mock_server.command2 = click.Command('command2')
    test_context = click.Context(Mock(), obj=mock_server)

    gs = GSCommand()
    command = gs.get_command(test_context, 'command1')

    assert command == mock_server.command1
