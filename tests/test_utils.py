import getpass
from mock import patch

from gs_manager.utils import run_as_user, to_pascal_case, to_snake_case


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
    user = getpass.getuser()
    run_as_user(user, 'ls')

    assert mock_subprocess.check_output.called_with('ls')


@patch('gs_manager.utils.subprocess')
def test_run_as_user_strip_response(mock_subprocess):
    expected = 'test'
    mock_subprocess.check_output.return_value = '{}  \n'.format(expected)

    user = getpass.getuser()
    ouput = run_as_user(user, 'ls')

    assert ouput == expected


@patch('gs_manager.utils.subprocess')
def test_run_as_user_different_user(mock_subprocess):
    user = 'root'
    command = 'ls'
    expected = 'sudo su - {} -c {}'.format(user, command)

    run_as_user(user, command)

    assert mock_subprocess.check_output.called_with(expected)


@patch('gs_manager.utils.subprocess')
def test_run_as_user_diffent_sudo(mock_subprocess):
    user = 'root'
    command = 'ls'
    sudo_format = 'echo {} "{}"'
    expected = sudo_format.format(user, command)

    run_as_user(user, command, sudo_format=sudo_format)

    assert mock_subprocess.check_output.called_with(expected)


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
