import getpass
import subprocess

import pytest
from gs_manager.utils import (SUDO_FORMAT, run_as_user, to_pascal_case,
                              to_snake_case)
from mock import Mock, patch

MOCK_SUDO = 'echo {} "{}"'


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
    expected = SUDO_FORMAT.format(user, command)

    run_as_user(user, command)

    assert mock_subprocess.Popen.called_with(
        expected, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


@patch('gs_manager.utils.subprocess')
@patch('gs_manager.utils.SUDO_FORMAT', MOCK_SUDO)
def test_run_as_user_diffent_sudo(mock_subprocess):
    mock_popen = Mock()
    mock_popen.communicate.return_value = (None, None)
    mock_popen.returncode = 0
    mock_subprocess.Popen.return_value = mock_popen

    user = 'root'
    command = 'ls'
    expected = MOCK_SUDO.format(user, command)

    run_as_user(user, command)

    assert mock_subprocess.Popen.called_with(
        expected, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


@patch('gs_manager.utils.SUDO_FORMAT', MOCK_SUDO)
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

    for test in tests:
        output = run_as_user(user, test)
        assert output == '{} {}'.format(user, test)


def test_run_as_user_bad_return():
    user = getpass.getuser()

    with pytest.raises(subprocess.CalledProcessError):
        run_as_user(user, 'false')


def test_run_as_user_return_process():
    user = getpass.getuser()

    process = run_as_user(user, 'false', return_process=True)

    assert process.returncode != 0


@patch('gs_manager.utils.subprocess')
def test_run_as_user_no_redirect(mock_subprocess):
    mock_popen = Mock()
    mock_popen.communicate.return_value = (None, None)
    mock_popen.returncode = 0
    mock_subprocess.Popen.return_value = mock_popen

    user = getpass.getuser()

    run_as_user(user, 'ls -la', redirect_output=False)

    assert mock_subprocess.Popen('ls -la')


def test_run_as_user_pipeline_2():
    expected = 'test'
    user = getpass.getuser()

    output = run_as_user(user, 'echo {} | cat'.format(expected))

    assert output == expected


def test_run_as_user_pipeline_3():
    user = getpass.getuser()

    output = run_as_user(user, 'echo test | cat | xargs echo 2')

    assert output == '2 test'


def test_run_as_user_pipeline_5():
    user = getpass.getuser()

    output = run_as_user(
        user,
        'echo test | cat | xargs echo 2 | cat | xargs echo 3'
    )

    assert output == '3 2 test'
