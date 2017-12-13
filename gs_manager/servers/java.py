import os
from subprocess import CalledProcessError

import click
from gs_manager.decorators import multi_instance
from gs_manager.servers.custom_screen import CustomScreen


class Java(CustomScreen):
    """
    Generic Java base gameserver that can be ran with Screen.
    Requires additional configuration to work.
    """
    command_format = ('{} {} -jar {} {}')

    @staticmethod
    def defaults():
        defaults = CustomScreen.defaults()
        defaults.update({
            'extra_args': '',
            'java_args': '',
            'java_path': 'java',
            'server_jar': None,
        })
        return defaults

    @staticmethod
    def excluded_from_save():
        parent = CustomScreen.excluded_from_save()
        return parent + [
            'command',
        ]

    @multi_instance
    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True)
    @click.option('-hc', '--history',
                  type=int,
                  help='Number of lines to show in screen for history')
    @click.option('-ds', '--delay_start',
                  type=int,
                  help=('Time (in seconds) to wait after service has started '
                        'to verify'))
    @click.option('-mt', '--max_start',
                  type=int,
                  help='Max time (in seconds) to wait before assuming the '
                       'server is deadlocked')
    @click.option('-ja', '--java_args',
                  type=str,
                  help=('Extra args to pass to Java'))
    @click.option('-sj', '--server_jar',
                  type=click.Path(),
                  help='Path to Minecraft server jar')
    @click.option('-jp', '--java_path',
                  type=click.Path(),
                  help='Path to Java executable')
    @click.option('-ea', '--extra_args',
                  type=str,
                  help=('To add to jar command'))
    @click.option('-fg', '--foreground',
                  is_flag=True,
                  help='Start gameserver in foreground. Ignores '
                       'spawn_progress, screen, and any other '
                       'options or classes that cause server to run '
                       'in background.')
    @click.pass_obj
    def start(self, no_verify, *args, **kwargs):
        """ starts java gameserver """

        if self.config['server_jar'] is None:
            raise click.BadParameter(
                'must provide a server_jar',
                self.context, self._get_param_obj('server_jar'))
        elif not os.path.isfile(self.config['server_jar']):
            raise click.BadParameter(
                'cannot find server_jar: {}'.format(self.config['server_jar']),
                self.context, self._get_param_obj('server_jar'))
        else:
            try:
                self.run_as_user('which {}'.format(self.config['java_path']))
            except CalledProcessError:
                raise click.BadParameter(
                    'cannot find java executable: {}'
                    .format(self.config['java_path']),
                    self.context, self._get_param_obj('java_path')
                )
            else:
                self.logger.debug('found java')

        command = self.command_format.format(
            self.config['java_path'],
            self.config['java_args'],
            self.config['server_jar'],
            self.config['extra_args'],
        )
        self.invoke(
            super(Java, self).start,
            command=command,
            no_verify=no_verify,
        )
