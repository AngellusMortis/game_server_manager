import os
import signal
import time
from subprocess import PIPE, STDOUT

import click
import psutil
from gs_manager.config import DEFAULT_SERVER_TYPE
from gs_manager.decorators import multi_instance, single_instance
from gs_manager.utils import run_as_user, write_as_user
from gs_manager.validators import validate_instance_overrides

try:
    from subprocess import DEVNULL
except ImportError:
    DEVNULL = open(os.devnull, 'w')

STATUS_SUCCESS = 0
STATUS_FAILED = 1
STATUS_PARTIAL_FAIL = 2


class Base(object):
    context = None
    config = None
    supports_multi_instance = False

    @staticmethod
    def defaults():
        return {
            'config': '.gs_config.json',
            'type': DEFAULT_SERVER_TYPE,
            'user': 'root',
            'name': 'gameserver',
            'max_start': 60,
            'max_stop': 30,
            'delay_start': 1,
            'delay_prestop': 30,
            'instance_overrides': {},
            'current_instance': None,
            'command': None,
            'multi': False,
            'foreground': False,
            'spawn_process': False,
            'parallel': False,
        }

    @staticmethod
    def excluded_from_save():
        return [
            'config',
            'debug',
            'help',
            'save',
            'path',
            'force',
            'no_verify',
            'current_instance',
            'foreground',
            'parallel',
        ]

    @staticmethod
    def global_options():
        return {
            'all': [
                {
                    'param_decls': ('-n', '--name'),
                    'type': str,
                    'help':
                        'Name of gameserver screen service, must be unique '
                        'across all gameservers',
                },
            ],
            'instance_enabled': [
                {
                    'param_decls': ('-i', '--instance_overrides'),
                    'type': str,
                    'multiple': True,
                    'callback': validate_instance_overrides,
                    'help':
                        'Override for config options to override on a per '
                        'instance level. Not supported for all server types. '
                        'See options for specific server type for '
                        'overrideable options. Must be in format of '
                        '<instance_name>:<json_with_options_to_override>. '
                        'Example (for ARK server type): '
                        '    \'main:{"ark_param":["Port=20000"]}\'',
                },
                {
                    'param_decls': ('-ci', '--current_instance'),
                    'type': str,
                    'help':
                        'Current instance to run commands against. If all, '
                        'will loop through all instances and run the command '
                        'for each',
                },
                {
                    'param_decls': ('-p', '--parallel'),
                    'is_flag': True,
                    'help':
                        'Used in conjuntion with -ci @all to run all '
                        'subcommands in parallel',
                }
            ]
        }

    def __init__(self, context, config=None, supports_multi_instance=False):
        if config is None:
            config = {}

        self.context = context
        self.config = config
        self.logger = self.config.get_logger()
        self.supports_multi_instance = supports_multi_instance

    def get_pid(self, instance_name=None):
        return self._read_pid_file(instance_name)

    def _get_pid_filename(self, instance_name):
        pid_filename = '.pid_file'
        if instance_name is not None:
            pid_filename = '{}_{}'.format(pid_filename, instance_name)
        return pid_filename

    def _read_pid_file(self, instance_name=None):
        pid = None
        pid_file = os.path.join(
            self.config['path'], self._get_pid_filename(instance_name))
        if os.path.isfile(pid_file):
            with open(pid_file, 'r') as f:
                try:
                    pid = int(f.read().strip())
                    self.logger.debug('read pid: {}'.format(pid))
                except ValueError:
                    pass
        return pid

    def _write_pid_file(self, pid, instance_name=None):
        self.logger.debug('write pid: {}'.format(pid))
        if pid is not None:
            pid_file = os.path.join(
                self.config['path'], self._get_pid_filename(instance_name))
            self.write_as_user(pid_file, str(pid))

    def _delete_pid_file(self, instance_name=None):
        pid_file = os.path.join(
            self.config['path'], self._get_pid_filename(instance_name))
        if os.path.isfile(pid_file):
            self.run_as_user('rm {}'.format(pid_file))

    def _progressbar(self, seconds):
        with click.progressbar(length=seconds) as waiter:
            for item in waiter:
                time.sleep(1)

    def _get_param_obj(self, param_name):
        param = None
        for p in self.context.command.params:
            if p.name == param_name:
                param = p
                break
        return param

    def _prestop(self, seconds_to_stop, is_restart):
        if hasattr(self, 'say') and \
                isinstance(self.say, click.Command) and \
                self.config['say_command'] is not None:
            message = 'server is shutting down in {} seconds...'
            if is_restart:
                message = 'server is restarting in {} seconds...'

            self.invoke(
                self.say,
                message=message.format(seconds_to_stop),
                do_print=False
            )
            return True
        return False

    def _stop(self):
        if hasattr(self, 'command') and \
                isinstance(self.command, click.Command) and \
                self.config['stop_command'] is not None:

            if self.config['save_command'] is not None:
                self.invoke(
                    self.command,
                    command_string=self.config['save_command'],
                    do_print=False
                )

            self.invoke(
                self.command,
                command_string=self.config['stop_command'],
                do_print=False
            )
        else:
            pid = self.get_pid(self.config['current_instance'])
            if pid is not None:
                self.run_as_user(
                    'kill -{} {}'.format(
                        signal.SIGINT,
                        pid
                    )
                )

    def _startup_check(self, instance_name=None):
        self.logger.info('')
        if self.config['delay_start'] > 0:
            time.sleep(self.config['delay_start'])
        with click.progressbar(length=self.config['max_start'],
                               show_eta=False,
                               show_percent=False) as waiter:
            for item in waiter:
                if self.is_running(instance_name) and \
                        self.is_accessible(instance_name):
                    break
                time.sleep(1)

    def is_running(self, instance_name=None):
        """ checks if gameserver is running """
        if instance_name == '@any':
            for instance in self.config.get_instances():
                if not self.is_running(instance):
                    return False
            return self.is_running(None)
        else:
            pid = self.get_pid(instance_name)
            if pid is not None:
                try:
                    psutil.Process(pid)
                except psutil.NoSuchProcess:
                    self._delete_pid_file(instance_name)
                else:
                    return True
            return False

    def is_accessible(self, instance_name=None):
        return True

    def invoke(self, method, *args, **kwargs):
        return self.context.invoke(method, *args, **kwargs)

    def run_as_user(self, command, **kwargs):
        """ runs command as configurated user """

        self.logger.debug('run command @{}: \'{}\''
                          .format(self.config['user'], command))
        try:
            output = run_as_user(self.config['user'], command, **kwargs)
        except Exception as ex:
            self.logger.debug('command exception: {}:{}'.format(type(ex), ex))
            raise ex
        self.logger.debug('command output:')
        self.logger.debug(output)

        return output

    def write_as_user(self, path, file_string):
        self.logger.debug('write file @{}: \'{}\''
                          .format(self.config['user'], path))

        write_as_user(self.config['user'], path, file_string)

    def kill_server(self, instance_name=None):
        """ forcibly kills server process """

        pid = self.get_pid(instance_name)
        if pid is not None:
            self.run_as_user(
                'kill -{} {}'.format(
                    signal.SIGKILL,
                    pid
                )
            )

    @multi_instance
    @click.command()
    @click.pass_obj
    def status(self, *args, **kwargs):
        """ checks if gameserver is running or not """

        instance = self.config['current_instance']
        i_config = self.config.get_instance_config(instance)

        if self.is_running(instance):
            if self.is_accessible(instance):
                self.logger.success(
                    '{} is running'.format(i_config['name']))
                return STATUS_SUCCESS
            else:
                self.logger.error(
                    '{} is running, but is not accessible'
                    .format(i_config['name']))
                return STATUS_PARTIAL_FAIL
        else:
            self.logger.warning('{} is not running'
                                .format(i_config['name']))
            return STATUS_FAILED

    @multi_instance
    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True,
                  help='Do not wait until gameserver is running before '
                       'exiting')
    @click.option('-ds', '--delay_start',
                  type=int,
                  help='Time (in seconds) to wait after running the command '
                       'before checking the server')
    @click.option('-mt', '--max_start',
                  type=int,
                  help='Max time (in seconds) to wait before assuming the '
                       'server is deadlocked')
    @click.option('-sp', '--spawn_process',
                  is_flag=True,
                  help='Spawn a new process')
    @click.option('-fg', '--foreground',
                  is_flag=True,
                  help='Start gameserver in foreground. Ignores '
                       'spawn_progress, screen, and any other '
                       'options or classes that cause server to run '
                       'in background.')
    @click.option('-c', '--command',
                  type=str,
                  help='Start up command')
    @click.pass_obj
    def start(self, no_verify, *args, **kwargs):
        """ starts gameserver """

        if self.config['command'] is None:
            raise click.BadParameter(
                'must provide a start command',
                self.context, self._get_param_obj('command'))

        instance = self.config['current_instance']
        i_config = self.config.get_instance_config(instance)

        if self.is_running(instance):
            self.logger.warning(
                        '{} is already running'.format(i_config['name']))
            return STATUS_PARTIAL_FAIL
        else:
            self._delete_pid_file()

            if self.config['multi']:
                self.logger.success('{}:'.format(i_config['name']))

            self.logger.info(
                'starting {}...'.format(i_config['name']), nl=False)

            command = i_config['command']
            popen_kwargs = {}
            if i_config['spawn_process'] and not self.config['foreground']:
                log_file_path = os.path.join(
                    i_config['path'],
                    'logs',
                    '{}.log'.format(i_config['name']),
                )
                command = 'nohup {}'.format(command)
                popen_kwargs = {
                    'return_process': True,
                    'redirect_output': False,
                    'stdin': DEVNULL,
                    'stderr': STDOUT,
                    'stdout': PIPE
                }
            elif self.config['foreground']:
                popen_kwargs = {
                    'redirect_output': False,
                }

            response = self.run_as_user(
                command,
                cwd=i_config['path'],
                **popen_kwargs,
            )

            if not self.config['foreground']:
                if i_config['spawn_process']:
                    self.run_as_user(
                        'cat > {}'.format(log_file_path),
                        return_process=True,
                        redirect_output=False,
                        stdin=response.stdout,
                        stderr=DEVNULL,
                        stdout=DEVNULL,
                    )

                command = i_config['command'].replace('"', '\\"')
                command = command.replace('?', '\\?')
                pids = self.run_as_user(
                    'ps -ef --sort=start_time | '
                    'grep -i -P "(?<!grep -i |-c ){}$" | awk \'{{print $2}}\''
                    .format(command)
                ).split('\n')

                for pid in pids:
                    if pid is not None and not pid == '':
                        self.run_as_user('ps -ef | grep {}'.format(pid))

                if pids[0] is None and not pids[0] == '':
                    raise click.ClickException('could not determine PID')
                self._write_pid_file(pids[0], instance)

                if not no_verify:
                    self._startup_check(instance)

                    if self.is_running(instance):
                        if self.is_accessible(instance):
                            self.logger.success(
                                '{} is running'.format(i_config['name']))
                            return STATUS_SUCCESS
                        else:
                            self.logger.error(
                                '{} is running but not accesible'
                                .format(i_config['name'])
                            )
                            return STATUS_PARTIAL_FAIL
                    else:
                        self.logger.error(
                            'could not start {}'.format(i_config['name']))
                        return STATUS_FAILED

    @multi_instance
    @click.command()
    @click.option('-f', '--force',
                  is_flag=True,
                  help='Force kill the server. WARNING: server will not have '
                       'chance to save')
    @click.option('-mt', '--max_stop',
                  type=int,
                  help='Max time (in seconds) to wait for server to stop')
    @click.option('-dp', '--delay_prestop',
                  type=int,
                  help='Time (in seconds) before stopping the server to '
                       'allow notifing users.')
    @click.pass_obj
    def stop(self, force, is_restart=False, *args, **kwargs):
        """ stops gameserver """

        instance = self.config['current_instance']
        i_config = self.config.get_instance_config(instance)

        if self.is_running(instance):
            if self.config['multi']:
                self.logger.success('{}:'.format(i_config['name']))

            if i_config['delay_prestop'] > 0 and not force:
                if self._prestop(i_config['delay_prestop'], is_restart):
                    self.logger.info('notifiying users...')
                    self._progressbar(i_config['delay_prestop'])

            self.logger.info('stopping {}...'.format(i_config['name']))

            if force:
                self.kill_server(instance)
                time.sleep(1)
            else:
                self._stop()
                with click.progressbar(length=i_config['max_stop'],
                                       show_eta=False,
                                       show_percent=False) as waiter:
                    for item in waiter:
                        if not self.is_running(instance):
                            break
                        time.sleep(1)

            if self.is_running(instance):
                self.logger.error(
                        'could not stop {}'.format(i_config['name']))
                return STATUS_PARTIAL_FAIL
            else:
                self.logger.success(
                        '{} was stopped'.format(i_config['name']))
                return STATUS_SUCCESS
        else:
            self.logger.warning(
                        '{} is not running'.format(i_config['name']))
            return STATUS_FAILED

    @multi_instance
    @click.command()
    @click.option('-f', '--force',
                  is_flag=True,
                  help='Option passed to stop command. See stop help '
                       'for more.')
    @click.option('-n', '--no_verify',
                  is_flag=True,
                  help='Option passed to start command. See start help '
                       'for more.')
    @click.pass_obj
    def restart(self, force, no_verify, *args, **kwargs):
        """ restarts gameserver"""

        if self.is_running(self.config['current_instance']):
            self.invoke(self.stop, force=force, is_restart=True)
        return self.invoke(self.start, no_verify=no_verify)

    @single_instance
    @click.command()
    @click.argument('edit_path',
                    type=click.Path())
    @click.pass_obj
    def edit(self, edit_path, *args, **kwargs):
        """ edits a server file with your default editor """
        if self.is_running(self.config['current_instance']):
            self.logger.warning(
                '{} is still running'.format(self.config['name']))
            return STATUS_PARTIAL_FAIL

        file_path = os.path.join(self.config['path'], edit_path)
        editor = os.environ.get('EDITOR') or 'vim'

        self.run_as_user(
            '{} {}'.format(editor, file_path),
            redirect_output=False,
        )
