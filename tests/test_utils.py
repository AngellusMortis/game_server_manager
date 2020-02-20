import subprocess

import pytest
from gs_manager.utils import run_command, to_pascal_case, to_snake_case
from mock import Mock, patch


def test_to_snake_case():
    tests = [
        ("Test", "test"),
        ("test", "test"),
        ("AnotherTest", "another_test"),
        ("another_test", "another_test"),
        ("OneMoreTest", "one_more_test"),
        ("mixedTest", "mixed_test"),
        ("Another_mixedTest", "another_mixed_test"),
    ]

    for test in tests:
        assert to_snake_case(test[0]) == test[1]


def test_to_pascal_case():
    tests = [
        ("test", "Test"),
        ("Test", "Test"),
        ("another_test", "AnotherTest"),
        ("AnotherTest", "AnotherTest"),
        ("one_more_test", "OneMoreTest"),
        ("mixedTest", "MixedTest"),
        ("Another_mixedTest", "AnotherMixedTest"),
    ]

    for test in tests:
        assert to_pascal_case(test[0]) == test[1]


@patch("gs_manager.utils.subprocess")
def test_run_command(mock_subprocess):
    mock_popen = Mock()
    mock_popen.communicate.return_value = (None, None)
    mock_popen.returncode = 0
    mock_subprocess.Popen.return_value = mock_popen
    run_command("ls")

    assert mock_subprocess.Popen.called_with(
        "ls", stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )


@patch("gs_manager.utils.subprocess")
def test_run_command_strip_response(mock_subprocess):
    expected = "test"

    mock_popen = Mock()
    mock_popen.communicate.return_value = ("{}  \n".format(expected), None)
    mock_popen.returncode = 0
    mock_subprocess.Popen.return_value = mock_popen

    output = run_command("ls")

    assert output == expected


def test_run_command_output():
    tests = [
        "test",
        "Test",
        "1test",
        "another test",
        "another\ntest",
        "last $est",
    ]

    for test in tests:
        output = run_command('echo "{}"'.format(test))
        assert output == test


def test_run_command_bad_return():
    with pytest.raises(subprocess.CalledProcessError):
        run_command("false")


def test_run_command_return_process():
    process = run_command("false", return_process=True)

    assert process.returncode != 0


@patch("gs_manager.utils.subprocess")
def test_run_command_no_redirect(mock_subprocess):
    mock_popen = Mock()
    mock_popen.communicate.return_value = (None, None)
    mock_popen.returncode = 0
    mock_subprocess.Popen.return_value = mock_popen

    run_command("ls -la", redirect_output=False)

    assert mock_subprocess.Popen("ls -la")


def test_run_command_pipeline_2():
    expected = "test"

    output = run_command("echo {} | cat".format(expected))

    assert output == expected


def test_run_command_pipeline_3():
    output = run_command("echo test | cat | xargs echo 2")

    assert output == "2 test"


def test_run_command_pipeline_5():
    output = run_command("echo test | cat | xargs echo 2 | cat | xargs echo 3")

    assert output == "3 2 test"
