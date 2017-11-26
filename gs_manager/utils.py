import re
import subprocess


def to_pascal_case(name):
    return name.replace('_', ' ').title().replace(' ', '')


def to_snake_case(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def run_as_user(user, command):
    current_user = subprocess.getoutput('whoami').strip()

    if current_user != user:
        command = command.replace('"', '\\"')
        command = command.replace('$', '\$')
        command = 'sudo su - {} -c "{}"'.format(user, command)

    output = subprocess.getoutput(command).strip()
    return output
