import click

from gs_manager.servers.base import Base


class Custom(Base):
    logger = None

    @staticmethod
    def defaults():
        defaults = Base.defaults()
        defaults.update({
            'history': 1024,
            'delay_start': 3,
            'delay_stop': 10,
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

    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True)
    @click.option('-h', '--history',
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
    def start(self, no_verify, *args, **kwargs):
        """ starts gameserver """

        self.debug('command: start')

        if self.options.get('command') is None:
            raise click.BadParameter('must provide a start command')

        if self.is_running():
            click.secho('{} is already running'
                        .format(self.options['name']),
                        fg='red')
            exit(1)
        else:
            click.echo('starting {}...'.format(self.options['name']))
            self.run_as_user('cd {} && screen -h {} -dmS {} {}'
                             .format(self.options['path'],
                                     self.options['history'],
                                     self.options['name'],
                                     self.options['command']))
            if not no_verify:
                self._progressbar(self.options['delay_start'])

                if self.is_running():
                    click.secho('{} is running'
                                .format(self.options['name']),
                                fg='green')
                else:
                    click.secho('could not start {}'
                                .format(self.options['name']),
                                fg='red')
                    exit(1)

    @click.command()
    @click.option('-f', '--force',
                  is_flag=True)
    @click.option('-dt', '--delay_stop',
                  type=int,
                  help=('Time (in seconds) to wait after service has stopped '
                        'to verify'))
    @click.option('-dp', '--delay_prestop',
                  type=int,
                  help=('Time (in seconds) before stopping the server to '
                        'allow notifing users.'))
    @click.option('-sc', '--stop_command',
                  type=str,
                  help='Command to stop server.')
    @click.pass_obj
    def stop(self, force, is_restart=False, *args, **kwargs):
        """ stops gameserver """

        self.debug('command: stop')

        if self.options.get('stop_command') is None:
            raise click.BadParameter('must provide a stop command')

        if self.is_running():
            if self.options['delay_prestop'] > 0 and not force:
                click.echo('notifiying users...'
                           .format(self.options['name'],
                                   self.options['delay_prestop']))

                message = 'server is shutting down in {} seconds...'
                if is_restart:
                    message = 'server is restarting in {} seconds...'
                self.invoke(
                    self.say,
                    message=message.format(self.options['delay_prestop']))
                self._progressbar(self.options['delay_prestop'])

            click.echo('stopping {}...'.format(self.options['name']))

            if force:
                self.kill_server()
            else:
                self.invoke(
                    self.command,
                    command_string=self.options['stop_command'],
                    do_print=False)
                self._progressbar(self.options['delay_stop'])

            if self.is_running():
                click.secho('{} could not be stopped'
                            .format(self.options['name']),
                            fg='red')
                exit(1)
            else:
                click.secho('{} was stopped'
                            .format(self.options['name']),
                            fg='green')
        else:
            click.secho('{} is not running'
                        .format(self.options['name']),
                        fg='red')
            exit(1)

    @click.command()
    @click.option('-f', '--force',
                  is_flag=True)
    @click.option('-n', '--no_verify',
                  is_flag=True)
    @click.pass_obj
    def restart(self, force, no_verify, *args, **kwargs):
        """ restarts gameserver"""

        self.debug('command: restart')

        if self.is_running():
            self.invoke(self.stop, force=force, is_restart=True)
        self.invoke(self.start, no_verify=no_verify)

    @click.command()
    @click.pass_obj
    def status(self, *args, **kwargs):
        """ checks if gameserver is runing or not """

        self.debug('command: status')

        if self.is_running():
            click.secho('{} is running'
                        .format(self.options['name']),
                        fg='green')
        else:
            click.secho('{} is not running'
                        .format(self.options['name']),
                        fg='red')

    @click.command()
    @click.argument('command_string')
    @click.pass_obj
    def command(self, command_string, do_print=True, *args, **kwargs):
        """ runs console command """

        self.debug('command: command')

        command_string = "screen -p 0 -S {} -X eval 'stuff \"{}\"\015'" \
            .format(self.options['name'], command_string)
        output = self.run_as_user(command_string)

        if do_print:
            click.echo(output)
        return output

    @click.command()
    @click.argument('message')
    @click.option('-yc', '--say_command',
                  type=str,
                  help='Command format to send broadcast to sever.')
    @click.pass_obj
    def say(self, message, *args, **kwargs):
        """ broadcasts a message to gameserver """

        self.debug('command: say')

        command_format = self.options.get('say_command')

        if command_format is None:
            raise click.BadParameter('must provide a say command format')

        return self.invoke(
            self.command, command_string=command_format.format(message))

    @click.command()
    @click.pass_obj
    def attach(self):
        """ attachs to gameserver screen """

        self.debug('command: attach')

        if self.is_running():
            self.run_as_user('screen -x {}'.format(self.options['name']))
        else:
            click.secho('{} is not running'
                        .format(self.options['name']),
                        fg='red')
            exit(1)
