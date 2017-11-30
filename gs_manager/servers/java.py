import click

from gs_manager.servers.custom import Custom


class Java(Custom):
    command_format = ('{} {} -jar {} {}')

    def __init__(self, *args, **kwargs):
        super(Java, self).__init__(*args, **kwargs)

    @staticmethod
    def defaults():
        defaults = Custom.defaults()
        defaults.update({
            'extra_args': '',
            'java_args': '',
            'java_path': 'java',
        })
        return defaults

    @staticmethod
    def excluded_from_save():
        parent = Custom.excluded_from_save()
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
    @click.pass_obj
    def start(self, no_verify, *args, **kwargs):
        """ starts Minecraft server """

        server_jar = self.options.get('server_jar')

        if server_jar is None:
            raise click.BadParameter('must provide a server_jar')

        self.options['command'] = self.command_format.format(
            self.options['java_path'],
            self.options['java_args'],
            self.options['server_jar'],
            self.options['extra_args'],
        )
        self.invoke(
            super(Java, self).start, no_verify=no_verify)
