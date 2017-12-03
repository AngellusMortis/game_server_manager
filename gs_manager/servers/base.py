import logging
import os
import pprint
import signal
import time

import click
import psutil
from gs_manager.utils import run_as_user, write_as_user


class Base(object):

    @staticmethod
    def defaults():
        return {
            'config': '.gs_config.json',
            'type': 'custom_screen',
            'name': 'gameserver',
            'user': 'root',
            'delay_start': 3,
            'max_stop': 60,
            'delay_prestop': 30,
            'debug': False
        }

    @staticmethod
    def excluded_from_save():
        return [
            'config',
            'path',
            'save',
            'debug',
            'force',
            'no_verify',
        ]

    logger = None

    def __init__(self, context, options=None):
        if options is None:
            options = {}

        self.context = context
        self.logger = logging.getLogger(__name__)

        self.options = options

    @property
    def pid(self):
        return self._read_pid_file()

    def _read_pid_file(self):
        pid = None
        pid_file = os.path.join(self.options['path'], '.pid_file')
        if os.path.isfile(pid_file):
            with open(pid_file, 'r') as f:
                try:
                    pid = int(f.read().strip())
                except ValueError:
                    pass
        self.debug('read pid: {}'.format(pid))
        return pid

    def _write_pid_file(self, pid):
        self.debug('write pid: {}'.format(pid))
        if pid is not None:
            pid_file = os.path.join(self.options['path'], '.pid_file')
            with open(pid_file, 'w') as f:
                f.write(str(pid))

    def _delete_pid_file(self):
        pid_file = os.path.join(self.options['path'], '.pid_file')
        if os.path.isfile(pid_file):
            os.remove(pid_file)

    @property
    def running(self):
        """ checks if gameserver is running """
        try:
            psutil.Process(self.pid)
        except psutil.NoSuchProcess:
            return False
        return True

    def _progressbar(self, seconds):
        with click.progressbar(length=seconds) as waiter:
            for item in waiter:
                time.sleep(1)

    def invoke(self, method, *args, **kwargs):
        self.context.invoke(method, *args, **kwargs)

    def debug(self, message):
        """ prints message out to console if debug is on """

        if isinstance(message, (list, dict)):
            message = pprint.pformat(message)
        if not isinstance(message, str):
            message = str(message)

        self.logger.debug(message)
        if self.options['debug']:
            click.secho(message, fg='cyan')

    def debug_command(self, name, args=None):
        self.debug('command: {}'.format(name))
        self.debug('options:')
        self.debug(self.options)
        if args is not None:
            self.debug('locals:')
            self.debug(args)
        self.debug('')

    def run_as_user(self, command, **kwargs):
        """ runs command as configurated user """

        self.debug('run command @{}: \'{}\''
                   .format(self.options['user'], command))
        try:
            output = run_as_user(self.options['user'], command, **kwargs)
        except Exception as ex:
            self.debug('command exception: {}:{}'.format(type(ex), ex))
            raise ex
        self.debug('command output:')
        self.debug(output)

        return output

    def write_as_user(self, path, file_string):
        self.debug('write file @{}: \'{}\''
                   .format(self.options['user'], path))

        write_as_user(self.options['user'], path, file_string)

    def kill_server(self):
        """ forcibly kills server process """

        pid = self.pid
        if pid is not None:
            os.kill(pid, signal.SIGKILL)

    def _prestop(self, seconds_to_stop, is_restart):
        raise NotImplementedError()

    def _stop(self):
        pid = self.pid
        if pid is not None:
            os.kill(pid, signal.SIGINT)

    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True)
    @click.option('-c', '--command',
                  type=str,
                  help='Start up command.')
    @click.option('-ds', '--delay_start',
                  type=int,
                  help=('Time (in seconds) to wait after service has started '
                        'to verify'))
    @click.pass_obj
    def start(self, no_verify, command, delay_start):
        """ starts gameserver """

        self.debug_command('start', locals())
        command = command or self.options['command']
        delay_start = delay_start or self.options['delay_start']

        if command is None or command == '':
            raise click.BadParameter('must provide a start command')

        if self.running:
            raise click.ClickException('{} is already running'
                                       .format(self.options['name']))
        else:
            self._delete_pid_file()

            click.echo('starting {}...'.format(self.options['name']), nl=False)
            self.run_as_user(command,
                             cwd=self.options['path'])

            command = command.replace('+', '\\+')
            pids = self.run_as_user(
                'ps -ef --sort=start_time | grep -i -P "(?<!grep -i ){}" | awk \'{{print $2}}\''
                .format(command)
            ).split('\n')
            self._write_pid_file(pids[-1])

            if not no_verify:
                click.echo('')
                self._progressbar(delay_start)

                if self.running:
                    click.secho('{} is running'
                                .format(self.options['name']),
                                fg='green')
                else:
                    raise click.ClickException('could not start {}'
                                               .format(self.options['name']))

    @click.command()
    @click.option('-f', '--force',
                  is_flag=True)
    @click.option('-mt', '--max_stop',
                  type=int,
                  help=('Max time (in seconds) to wait for server to stop'))
    @click.option('-dp', '--delay_prestop',
                  type=int,
                  help=('Time (in seconds) before stopping the server to '
                        'allow notifing users.'))
    @click.pass_obj
    def stop(self, force, max_stop, delay_prestop, is_restart=False):
        """ stops gameserver """

        self.debug_command('stop', locals())
        max_stop = max_stop or self.options['max_stop']
        if not delay_prestop == 0:
            delay_prestop = delay_prestop or self.options['delay_prestop']

        if self.running:
            if delay_prestop > 0 and not force:
                click.echo('notifiying users...'
                           .format(self.options['name'],
                                   delay_prestop))
                self._prestop(delay_prestop, is_restart)
                self._progressbar(delay_prestop)

            click.echo('stopping {}...'.format(self.options['name']))

            if force:
                self.kill_server()
            else:
                self._stop()
                with click.progressbar(length=max_stop,
                                       show_eta=False,
                                       show_percent=False) as waiter:
                    for item in waiter:
                        if not self.running:
                            break
                        time.sleep(1)

            if self.running:
                raise click.ClickException('could not stop {}'
                                           .format(self.options['name']))
            else:
                click.secho('{} was stopped'
                            .format(self.options['name']),
                            fg='green')
        else:
            raise click.ClickException('{} is not running'
                                       .format(self.options['name']))

    @click.command()
    @click.option('-f', '--force',
                  is_flag=True)
    @click.option('-n', '--no_verify',
                  is_flag=True)
    @click.pass_obj
    def restart(self, force, no_verify):
        """ restarts gameserver"""

        self.debug_command('restart', locals())
        if self.running:
            self.invoke(self.stop, force=force, is_restart=True)
        self.invoke(self.start, no_verify=no_verify)

    @click.command()
    @click.pass_obj
    def status(self):
        """ checks if gameserver is runing or not """

        self.debug_command('status')
        if self.running:
            click.secho('{} is running'
                        .format(self.options['name']),
                        fg='green')
        else:
            click.secho('{} is not running'
                        .format(self.options['name']),
                        fg='red')
