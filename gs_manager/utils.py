import re
import subprocess
import getpass
import shlex
import sys


def to_pascal_case(name):
    return to_snake_case(name).replace('_', ' ').title().replace(' ', '')


def to_snake_case(name):
    return re.sub('([a-z])([A-Z])', r'\1_\2', name).lower()


def run_as_user(user, command, sudo_format='sudo su - {} -c "{}"'):
    current_user = getpass.getuser()

    if current_user != user:
        command = command.replace('"', '\\"')
        command = sudo_format.format(user, command)

    args = shlex.split(command)
    process = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout, stderr = process.communicate()

    if stdout is None:
        stdout = ''

    if process.returncode == 0:
        if not isinstance(stdout, str):
            stdout = stdout.decode(sys.getdefaultencoding())
        stdout = stdout.strip()
        return stdout

    raise subprocess.CalledProcessError(
        process.returncode, command, stdout)
