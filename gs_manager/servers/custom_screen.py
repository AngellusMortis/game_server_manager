import re
from subprocess import CalledProcessError

import click
from gs_manager.servers.base import Base


class CustomScreen(Base):
    """
    custom_screen is for game servers that have some type of interactive
    terminal and will get ran on its own screen so the terminal can be
    accessed at any time
    """
    logger = None

    @staticmethod
    def defaults():
        defaults = Base.defaults()
        defaults.update({
            'history': 1024,
            'delay_start': 3,
            'max_stop': 60,
            'delay_prestop': 30,
        })
        return defaults

    @staticmethod
    def excluded_from_save():
        parent = Base.excluded_from_save()
        return parent + [
            'force',
            'no_verify',
        ]

    @property
    def pid(self):
        pid = None
        screen = None

        try:
            screen = self.run_as_user('screen -ls | grep {}'
                                      .format(self.options['name'])).strip()
        except CalledProcessError as ex:
            if not ex.output == '':
                raise click.ClickException(
                    'something went wrong checking server status')

        if screen is not None and screen != '':
            pid = int(re.match('\d+', screen).group())

        self.debug('pid: {}'.format(pid))
        return pid

    @property
    def running(self):
        """ checks if gameserver is running """

        is_running = False
        pid = self.pid
        if pid is not None:
            processes = self.run_as_user(
                'ps -el | grep {} | awk \'{{print $4}}\''.format(pid))
            processes = processes.split('\n')
            is_running = len(processes) == 2 and processes[0] == str(pid)

        self.debug('is_running: {}'.format(is_running))
        return is_running

    def _prestop(self, delay_prestop, is_restart):
        message = 'server is shutting down in {} seconds...'
        if is_restart:
            message = 'server is restarting in {} seconds...'

        self.invoke(
            self.say,
            message=message.format(delay_prestop))

    def _stop(self):
        self.invoke(
            self.command,
            command_string=self.options['stop_command'],
            do_print=False
        )

    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True)
    @click.option('-hc', '--history',
                  type=int,
                  help='Number of lines to show in screen for history')
    @click.option('-c', '--command',
                  type=str,
                  help='Start up command.')
    @click.option('-ds', '--delay_start',
                  type=int,
                  help=('Time (in seconds) to wait after service has started '
                        'to verify'))
    @click.pass_obj
    def start(self, no_verify, history, command, delay_start):
        """ starts gameserver """

        self.debug_command('start', locals())
        history = history or self.options['history']
        command = command or self.options['command']
        delay_start = delay_start or self.options['delay_start']

        command = 'screen -h {} -dmS {} {}'.format(
            history, self.options['name'], command)
        self.invoke(
            super(CustomScreen, self).start, no_verify=no_verify,
            command=command, delay_start=delay_start)

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
    @click.option('-sc', '--stop_command',
                  type=str,
                  help='Command to stop server.')
    @click.pass_obj
    def stop(self, force, max_stop, delay_prestop,
             stop_command, is_restart=False):
        """ stops gameserver """

        self.debug_command('stop', locals())
        max_stop = max_stop or self.options['max_stop']
        if not delay_prestop == 0:
            delay_prestop = delay_prestop or self.options['delay_prestop']
        stop_command = stop_command or self.options['stop_command']

        if stop_command is None or stop_command == '':
            raise click.BadParameter('must provide a stop command')

        self.options['stop_command'] = stop_command

        self.invoke(
            super(CustomScreen, self).stop,
            force=force, is_restart=is_restart,
            max_stop=max_stop, delay_prestop=delay_prestop
        )

    @click.command()
    @click.argument('command_string')
    @click.pass_obj
    def command(self, command_string, do_print=True):
        """ runs console command """

        self.debug_command('command', locals())

        if self.running:
            command_string = "screen -p 0 -S {} -X eval 'stuff \"{}\"\015'" \
                .format(self.options['name'], command_string)
            output = self.run_as_user(command_string)

            if do_print:
                click.echo(output)
            return output
        else:
            raise click.ClickException('{} is not running'
                                       .format(self.options['name']))

    @click.command()
    @click.argument('message')
    @click.option('-yc', '--say_command',
                  type=str,
                  help='Command format to send broadcast to sever.')
    @click.pass_obj
    def say(self, message, say_command):
        """ broadcasts a message to gameserver """

        self.debug_command('say', locals())
        say_command = say_command or self.options.get('say_command')

        if say_command is None:
            raise click.BadParameter('must provide a say command format')

        return self.invoke(
            self.command, command_string=say_command.format(message))

    @click.command()
    @click.pass_obj
    def attach(self):
        """ attachs to gameserver screen """

        self.debug_command('attach')
        if self.running:
            self.run_as_user('screen -x {}'.format(self.options['name']))
        else:
            raise click.ClickException('{} is not running'
                                       .format(self.options['name']))
