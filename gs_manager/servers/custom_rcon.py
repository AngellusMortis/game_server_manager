import os
import shlex
import subprocess
import time

import click
import click_spinner
from gs_manager.servers.custom_steam import CustomSteam
from valve.rcon import RCON
from valve.source import NoResponseError
from valve.source.a2s import ServerQuerier


class CustomRcon(CustomSteam):
    """
    custom_rcon is for Steam game servers with RCON
    """

    @property
    def rcon_enabled(self):
        raise NotImplementedError()

    @property
    def ip(self):
        raise NotImplementedError()

    @property
    def port(self):
        raise NotImplementedError()

    def _get_rcon_args(self):
        raise NotImplementedError()

    def _prestop(self, seconds_to_stop, is_restart):
        message = 'server is shutting down in {} seconds...'
        if is_restart:
            message = 'server is restarting in {} seconds...'

        self.invoke(
            self.say,
            message=message.format(seconds_to_stop),
            do_print=False
        )

    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True)
    @click.option('-c', '--command',
                  type=str,
                  help='Start up command.')
    @click.pass_obj
    def start(self, no_verify, command):
        """ starts gameserver """

        self.debug_command('start', locals())
        command = command or self.options['command']

        log_dir = os.path.join(self.options['path'], 'logs')
        if not os.path.isdir(log_dir):
            os.makedir(log_dir)
        log_filename = '{}.log'.format(self.options['name'])
        log_file_path = os.path.join(log_dir, log_filename)

        command = 'nohup {}'.format(command)
        args = shlex.split(command)

        self._delete_pid_file()

        click.echo('starting {}...'.format(self.options['name']), nl=False)
        pid = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            stdout=open(log_file_path, 'a')
        ).pid

        self._write_pid_file(pid)

        if not no_verify:
            with click_spinner.spinner():
                server = ServerQuerier((self.ip, self.port))

                connected = False
                while not connected:
                    try:
                        server.ping()
                        connected = True
                    except NoResponseError:
                        self.debug('server not up..')
                        time.sleep(1)

            if self.rcon_enabled:
                with click_spinner.spinner():
                    rcon = RCON(**self._get_rcon_args())

                    while not rcon.connected:
                        try:
                            rcon.connect()
                        except ConnectionRefusedError:
                            self.debug('RCON not up..')
                            time.sleep(1)

            if self.running:
                click.secho('{} is running'
                            .format(self.options['name']),
                            fg='green')
            else:
                raise click.ClickException('could not start {}'
                                           .format(self.options['name']))

    @click.command()
    @click.argument('command_string')
    @click.pass_obj
    def command(self, command_string, do_print=True):
        """ runs console command """

        self.debug_command('command', locals())

        if self.running:
            if self.rcon_enabled:
                output = None
                rcon = RCON(**self._get_rcon_args())
                try:
                    rcon.connect()
                except ConnectionRefusedError:
                    raise click.ClickException('could not connect to RCON')
                else:
                    rcon.authenticate()
                    output = rcon.execute(command_string).text
                    rcon.close()

                if do_print and output is not None:
                    click.echo(output)
                return output
            else:
                raise click.ClickException(
                    '{} does not have RCON enabled'
                    .format(self.options['name']))
        else:
            raise click.ClickException(
                '{} is not running'.format(self.options['name']))

    @click.command()
    @click.argument('message')
    @click.option('-yc', '--say_command',
                  type=str,
                  help='Command format to send broadcast to sever.')
    @click.pass_obj
    def say(self, message, say_command, do_print=True):
        """ broadcasts a message to gameserver """

        self.debug_command('say', locals())
        say_command = say_command or self.options.get('say_command')

        if say_command is None:
            raise click.BadParameter('must provide a say command format')

        return self.invoke(
            self.command,
            command_string=say_command.format(message),
            do_print=do_print
        )
