import getpass
import subprocess

import pytest
from gs_manager.utils import run_as_user, to_pascal_case, to_snake_case
from mock import Mock, patch


def test_to_snake_case():
    tests = [
        ('Test', 'test'),
        ('test', 'test'),
        ('AnotherTest', 'another_test'),
        ('another_test', 'another_test'),
        ('OneMoreTest', 'one_more_test'),
        ('mixedTest', 'mixed_test'),
        ('Another_mixedTest', 'another_mixed_test'),
    ]

    for test in tests:
        assert to_snake_case(test[0]) == test[1]


def test_to_pascal_case():
    tests = [
        ('test', 'Test'),
        ('Test', 'Test'),
        ('another_test', 'AnotherTest'),
        ('AnotherTest', 'AnotherTest'),
        ('one_more_test', 'OneMoreTest'),
        ('mixedTest', 'MixedTest'),
        ('Another_mixedTest', 'AnotherMixedTest'),
    ]

    for test in tests:
        assert to_pascal_case(test[0]) == test[1]


@patch('gs_manager.utils.subprocess')
def test_run_as_user_same_user(mock_subprocess):
    mock_popen = Mock()
    mock_popen.communicate.return_value = (None, None)
    mock_popen.returncode = 0
    mock_subprocess.Popen.return_value = mock_popen
    user = getpass.getuser()
    run_as_user(user, 'ls')

    assert mock_subprocess.Popen.called_with(
        'ls', stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


@patch('gs_manager.utils.subprocess')
def test_run_as_user_strip_response(mock_subprocess):
    expected = 'test'

    mock_popen = Mock()
    mock_popen.communicate.return_value = ('{}  \n'.format(expected), None)
    mock_popen.returncode = 0
    mock_subprocess.Popen.return_value = mock_popen

    user = getpass.getuser()
    ouput = run_as_user(user, 'ls')

    assert ouput == expected


@patch('gs_manager.utils.subprocess')
def test_run_as_user_different_user(mock_subprocess):
    mock_popen = Mock()
    mock_popen.communicate.return_value = (None, None)
    mock_popen.returncode = 0
    mock_subprocess.Popen.return_value = mock_popen

    user = 'root'
    command = 'ls'
    expected = 'sudo su - {} -c {}'.format(user, command)

    run_as_user(user, command)

    assert mock_subprocess.Popen.called_with(
        expected, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


@patch('gs_manager.utils.subprocess')
def test_run_as_user_diffent_sudo(mock_subprocess):
    mock_popen = Mock()
    mock_popen.communicate.return_value = (None, None)
    mock_popen.returncode = 0
    mock_subprocess.Popen.return_value = mock_popen

    user = 'root'
    command = 'ls'
    sudo_format = 'echo {} "{}"'
    expected = sudo_format.format(user, command)

    run_as_user(user, command, sudo_format=sudo_format)

    assert mock_subprocess.Popen.called_with(
        expected, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def test_run_as_user_output():
    tests = [
        'test',
        'Test',
        '1test',
        'another test',
        '"this test"',
        'another\ntest',
        'last $est',
    ]
    user = 'root'
    sudo_format = 'echo {} "{}"'

    for test in tests:
        output = run_as_user(user, test, sudo_format=sudo_format)
        assert output == '{} {}'.format(user, test)


def test_run_as_user_bad_return():
    user = getpass.getuser()

    with pytest.raises(subprocess.CalledProcessError):
        run_as_user(user, 'test')
