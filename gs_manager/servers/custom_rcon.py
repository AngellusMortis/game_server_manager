import signal

import click
from gs_manager.decorators import multi_instance, single_instance
from gs_manager.servers.base import STATUS_PARTIAL_FAIL
from gs_manager.servers.custom_steam import CustomSteam
from gs_manager.utils import get_param_obj
from valve.rcon import RCON, shell


class CustomRcon(CustomSteam):
    """
    Generic Steam gameserver with `Source RCON protocol`_ support.
    Requires additional configuration to work.

    .. _Source RCON protocol: https://developer.valvesoftware.com/wiki/Source_RCON_Protocol
    """

    @staticmethod
    def defaults():
        defaults = CustomSteam.defaults()
        defaults.update({
            'rcon_port': None,
            'rcon_password': None,
            'rcon_timeout': 10,
            'rcon_multi_part': False,
            'stop_command': None,
            'say_command': None,
            'save_command': None,
        })
        return defaults

    @staticmethod
    def excluded_from_save():
        parent = CustomSteam.excluded_from_save()
        return parent + [
            'command_string',
            'do_print',
            'message',
        ]

    @staticmethod
    def global_options():
        global_options = CustomSteam.global_options()
        all_options = [
            {
                'param_decls': ('-rp', '--rcon_port'),
                'type': int,
                'help': 'Port RCON service runs on',
            },
            {
                'param_decls': ('-rpw', '--rcon_password'),
                'type': str,
                'help': 'Password for RCON service',
            },
            {
                'param_decls': ('-rm', '--rcon_multi_part'),
                'is_flag': True,
                'help': 'Flag for if server support Multiple Part Packets',
            },
            {
                'param_decls': ('-rt', '--rcon_timeout'),
                'type': int,
                'help': 'Timeout for RCON connection',
            }
        ]
        global_options['all'] += all_options
        return global_options

    def is_rcon_enabled(self, instance_name=None):
        i_config = self.config.get_instance_config(instance_name)
        return i_config['rcon_port'] is not None and \
            i_config['rcon_password'] is not None

    def _get_rcon_args(self, instance_name=None):
        i_config = self.config.get_instance_config(instance_name)
        args = {
            'address': (i_config['steam_query_ip'],
                        i_config['rcon_port']),
            'password': i_config['rcon_password'],
            'timeout': i_config['rcon_timeout'],
            'multi_part': i_config['rcon_multi_part']
        }

        self.logger.debug('rcon args: {}'.format(args))
        return args

    def is_accessible(self, instance_name=None):
        is_accessible = super(CustomRcon, self).is_accessible(instance_name)
        if is_accessible and self.is_rcon_enabled(instance_name):
            rcon = RCON(**self._get_rcon_args(instance_name))
            try:
                rcon.connect()
            except ConnectionRefusedError:
                is_accessible = False
        return is_accessible

    def _prestop(self, seconds_to_stop, is_restart):
        if self.config['say_command'] is not None and \
                self.is_rcon_enabled(self.config['current_instance']):
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
        if self.config['stop_command'] is not None and \
                self.is_rcon_enabled(self.config['current_instance']):
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

    @multi_instance
    @click.command()
    @click.argument('command_string')
    @click.pass_obj
    def command(self, command_string, do_print=True, *args, **kwargs):
        """ runs console command using RCON """

        instance = self.config['current_instance']
        i_config = self.config.get_instance_config(instance)

        if self.is_running(instance):
            if self.is_rcon_enabled(instance):
                output = None
                rcon = RCON(**self._get_rcon_args(instance))
                try:
                    rcon.connect()
                except ConnectionRefusedError:
                    self.logger.warning('could not connect to RCON')
                else:
                    rcon.authenticate()
                    output = rcon.execute(command_string).text
                    rcon.close()

                    if do_print and output is not None:
                        if self.config['multi']:
                            self.logger.success('{}:'.format(i_config['name']))
                        self.logger.info(output)
                    return output
            else:
                self.logger.warning(
                    '{} does not have RCON enabled'
                    .format(i_config['name']))
                return STATUS_PARTIAL_FAIL
        else:
            self.logger.warning('{} is not running'.format(i_config['name']))
            return STATUS_PARTIAL_FAIL

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
                self.context, get_param_obj(self.context, 'save_command'))

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
                  help='Command format to send broadcast to server')
    @click.pass_obj
    def say(self, message, do_print=True, *args, **kwargs):
        """ broadcasts a message to gameserver """

        instance = self.config['current_instance']
        i_config = self.config.get_instance_config(instance)

        if i_config['say_command'] is None:
            raise click.BadParameter(
                'must provide a say command format',
                self.context, get_param_obj(self.context, 'say_command'))

        return self.invoke(
            self.command,
            command_string=i_config['say_command'].format(message),
            do_print=do_print
        )

    @single_instance
    @click.command()
    @click.pass_obj
    def shell(self, *args, **kwargs):
        """
        creates RCON shell.
        Shell docs: https://python-valve.readthedocs.io/en/latest/rcon.html#using-the-rcon-shell
        """

        if self.is_running(self.config['current_instance']):
            args = self._get_rcon_args(self.config['current_instance'])
            shell(args['address'], args['password'], args['multi_part'])
        else:
            raise click.ClickException('{} is not running'
                                       .format(self.config['name']))
