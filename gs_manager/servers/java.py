import click

from gs_manager.servers.custom_screen import CustomScreen


class Java(CustomScreen):
    command_format = ('{} {} -jar {} {}')

    @staticmethod
    def defaults():
        defaults = CustomScreen.defaults()
        defaults.update({
            'extra_args': '',
            'java_args': '',
            'java_path': 'java',
        })
        return defaults

    @staticmethod
    def excluded_from_save():
        parent = CustomScreen.excluded_from_save()
        return parent + [
            'command',
        ]

    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True)
    @click.option('-h', '--history',
                  type=int,
                  help='Number of lines to show in screen for history')
    @click.option('-ds', '--delay_start',
                  type=int,
                  help=('Time (in seconds) to wait after service has started '
                        'to verify'))
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
    @click.pass_obj
    def start(self, no_verify, history, delay_start,
              java_args, server_jar, java_path, extra_args):
        """ starts Minecraft server """

        self.debug_command('start', locals())
        history = history or self.options.get('history')
        delay_start = delay_start or self.options.get('delay_start')
        java_args = java_args or self.options.get('java_args')
        server_jar = server_jar or self.options.get('server_jar')
        java_path = java_path or self.options.get('java_path')
        extra_args = extra_args or self.options.get('extra_args')

        if server_jar is None:
            raise click.BadParameter('must provide a server_jar')

        command = self.command_format.format(
            java_path,
            java_args,
            server_jar,
            extra_args,
        )
        self.invoke(
            super(Java, self).start, no_verify=no_verify,
            history=history, delay_start=delay_start,
            command=command
        )
