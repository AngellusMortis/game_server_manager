import getpass
import hashlib
import io
import os
import re
import shlex
import struct
import subprocess
import sys
import zlib

import requests

import click


def to_pascal_case(name):
    return to_snake_case(name).replace('_', ' ').title().replace(' ', '')


def to_snake_case(name):
    return re.sub('([a-z])([A-Z])', r'\1_\2', name).lower()


def create_pipeline(args, previous_process=None,
                    redirect_output=True, **kwargs):
    processes = []
    split_index = args.index('|')
    args1 = args[:split_index]
    args2 = args[split_index+1:]

    if previous_process is not None:
        kwargs['stdin'] = previous_process.stdout
    else:
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.STDOUT

    processes.append(subprocess.Popen(
        args1,
        **kwargs
    ))

    if '|' in args2:
        processes += create_pipeline(
            args2, previous_process=processes[-1],
            redirect_output=redirect_output, **kwargs)
    else:
        if redirect_output:
            kwargs['stdout'] = subprocess.PIPE
            kwargs['stderr'] = subprocess.STDOUT

        kwargs['stdin'] = processes[-1].stdout

        processes.append(subprocess.Popen(
            args[split_index+1:],
            **kwargs
        ))

    return processes


def run_as_user(user, command, sudo_format='sudo su - {} -c "{}"',
                redirect_output=True, return_process=False, **kwargs):
    current_user = getpass.getuser()

    if current_user != user:
        command = command.replace('"', '\\"')
        command = command.replace('+', '\\+')
        command = sudo_format.format(user, command)

    args = shlex.split(command)

    processes = []
    if '|' in args:
        processes = create_pipeline(
            args, redirect_output=redirect_output, **kwargs)
        for x in range(len(processes)-1):
            processes[x].stdout.close()
    else:
        if redirect_output:
            kwargs['stdout'] = subprocess.PIPE
            kwargs['stderr'] = subprocess.STDOUT

        processes.append(subprocess.Popen(
            args,
            **kwargs
        ))

    if current_user != user and \
            isinstance(processes[0].stdin, io.BufferedWriter):
        # try:
        #     input = raw_input
        # except NameError:
        #     pass
        processes[0].stdin.write(input().encode('utf-8'))
        print()

    if return_process:
        return processes[-1]
    else:
        stdout, stderr = processes[-1].communicate()

        if stdout is None:
            stdout = ''

        if not isinstance(stdout, str):
            stdout = stdout.decode(sys.getdefaultencoding())
        stdout = stdout.strip()

        if processes[-1].returncode == 0:
            return stdout

        raise subprocess.CalledProcessError(
            processes[-1].returncode, command, stdout)


def write_as_user(user, path, file_string):
    parent_dir = os.path.join(path, os.pardir)
    current_user = getpass.getuser()

    if user != current_user:
        run_as_user(user, 'chown {} {}'.format(current_user, parent_dir))
    with open(path, 'w') as f:
        f.write(file_string)
    if user != current_user:
        run_as_user(user, 'chown {} {}'.format(user, parent_dir))


def get_json(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def validate_checksum(path, checksum, checksum_type):
    data = None
    file_checksum = None
    with open(path, 'rb') as f:
        data = f.read()
    file_checksum = getattr(hashlib, checksum_type)(data).hexdigest()

    if not checksum == file_checksum:
        raise click.ClickException(
            'could not validate {} checksum'.format(checksum_type))


def download_file(url, path, md5=None, sha1=None):
    response = requests.get(url, stream=True)
    response.raise_for_status()

    tmp_file = path + '.tmp'
    if os.path.isfile(tmp_file):
        os.remove(tmp_file)
    with open(tmp_file, 'wb') as f:
        with click.progressbar(
            response.iter_content(chunk_size=1024),
            length=int(response.headers.get('content-length'))
        ) as bar:
            for chunk in bar:
                if chunk:
                    f.write(chunk)
                    f.flush()

    if md5 is not None:
        validate_checksum(tmp_file, md5, 'md5')
    if sha1 is not None:
        validate_checksum(tmp_file, sha1, 'sha1')

    os.rename(tmp_file, path)


def str_to_l(st):
    return struct.unpack('q', st)[0]


def z_unpack(src, dst):
    with open(src, 'rb') as f_src:
        with open(dst, 'wb') as f_dst:
            f_src.read(8)
            size1 = str_to_l(f_src.read(8))
            f_src.read(8)
            size2 = str_to_l(f_src.read(8))
            if(size1 == -1641380927):
                size1 = 131072
            runs = (size2 + size1 - 1) / size1
            array = []
            for i in range(int(runs)):
                array.append(f_src.read(8))
                f_src.read(8)
            for i in range(int(runs)):
                to_read = array[i]
                compressed = f_src.read(str_to_l(to_read))
                decompressed = zlib.decompress(compressed)
                f_dst.write(decompressed)
