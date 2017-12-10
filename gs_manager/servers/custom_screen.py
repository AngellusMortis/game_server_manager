import re
from subprocess import CalledProcessError

import click
import psutil
from gs_manager.decorators import multi_instance, single_instance
from gs_manager.servers.base import Base


class CustomScreen(Base):
    """
    Generic gameserver that has an interactive console and can easily be
    ran via the screen command. Requires additional configuration to work.
    """
    logger = None

    @staticmethod
    def defaults():
        defaults = Base.defaults()
        defaults.update({
            'history': 1024,
            'say_command': None,
            'stop_command': None,
            'save_command': None,
        })
        return defaults

    @staticmethod
    def excluded_from_save():
        parent = Base.excluded_from_save()
        return parent + [
            'command_string',
            'do_print',
            'message',
        ]

    def _clear_screens(self):
        try:
            self.run_as_user('screen --wipe')
        except CalledProcessError:
            pass

    def get_pid(self, instance_name=None):
        pid = self._read_pid_file(instance_name)

        if pid is None:
            screen = None
            try:
                screen = self.run_as_user(
                    'screen -ls | grep {}'
                    .format(self.config['name'])).strip()
            except CalledProcessError as ex:
                self.logger.debug(ex.output)

            if screen is not None and screen != '':
                pid = int(re.match('\d+', screen).group())

            self._write_pid_file(pid, instance_name)
        return pid

    def is_running(self, instance_name=None):
        is_running = False
        pid = self.get_pid(instance_name)

        try:
            screen_process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            self._delete_pid_file(instance_name)
        else:
            child_count = len(screen_process.children())
            if child_count == 1:
                is_running = True
            elif child_count == 0:
                self._clear_screens()
            else:
                raise click.ClickException(
                    'Unexpected number of child proceses for screen')

        self.logger.debug('is_running: {}'.format(is_running))
        return is_running

    @multi_instance
    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True,
                  help='Do not wait until gameserver is running before '
                       'exiting')
    @click.option('-hc', '--history',
                  type=int,
                  help='Number of lines to show in screen for history')
    @click.option('-ds', '--delay_start',
                  type=int,
                  help='Time (in seconds) to wait after service has started '
                       'to verify it is running')
    @click.option('-mt', '--max_start',
                  type=int,
                  help='Max time (in seconds) to wait before assuming the '
                       'server is deadlocked')
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
        """ starts gameserver with screen """

        command = self.config['command']

        if not self.config['foreground']:
            command = 'screen -h {} -dmS {} {}'.format(
                self.config['history'],
                self.config['name'],
                self.config['command'],
            )

        self._clear_screens()
        self.invoke(
            super(CustomScreen, self).start,
            command=command,
            no_verify=no_verify,
        )

    @multi_instance
    @click.command()
    @click.argument('command_string')
    @click.pass_obj
    def command(self, command_string, do_print=True, *args, **kwargs):
        """ runs console command against screen session """

        if self.is_running(self.config['current_instance']):
            if do_print:
                self.logger.info(
                    'command @{}: {}'
                    .format(self.config['name'], command_string)
                )

            command_string = "screen -p 0 -S {} -X eval 'stuff \"{}\"\015'" \
                .format(self.config['name'], command_string)
            output = self.run_as_user(command_string)

            if do_print:
                self.logger.info(output)
            return output
        else:
            self.logger.warning('{} is not running'.format(self.config['name']))

    @multi_instance
    @click.command()
    @click.option('-vc', '--save_command',
                  type=str,
                  help='Command to save the server')
    @click.pass_obj
    def save(self, do_print=True, *args, **kwargs):
        """ saves gameserver """

        instance = self.config['current_instance']
        i_config = self.config.get_instance_config(instance)

        if i_config['save_command'] is None:
            raise click.BadParameter(
                'must provide a save command',
                self.context, self._get_param_obj('save_command'))

        return self.invoke(
            self.command,
            command_string=i_config['save_command'],
            do_print=do_print
        )

    @multi_instance
    @click.command()
    @click.argument('message')
    @click.option('-yc', '--say_command',
                  type=str,
                  help='Command format to send broadcast to sever')
    @click.pass_obj
    def say(self, message, do_print=True, *args, **kwargs):
        """ broadcasts a message to gameserver """

        if self.config['say_command'] is None:
            raise click.BadParameter(
                'must provide a say command format',
                self.context, self._get_param_obj('say_command'))

        return self.invoke(
            self.command,
            command_string=self.config['say_command'].format(message),
            do_print=do_print
        )

    @single_instance
    @click.command()
    @click.pass_obj
    def shell(self, *args, **kwargs):
        """ attachs to gameserver screen to give shell access """

        if self.is_running(self.config['current_instance']):
            self.run_as_user('screen -x {}'.format(self.config['name']))
        else:
            raise click.ClickException('{} is not running'
                                       .format(self.config['name']))
