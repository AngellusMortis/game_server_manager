import click

from gs_manager.servers.java import Java


class Minecraft(Java):
    def __init__(self, *args, **kwargs):
        super(Minecraft, self).__init__(*args, **kwargs)

        self.options['stop_command'] = 'stop'
        self.options['say_command'] = 'say {}'

    @staticmethod
    def defaults():
        defaults = Java.defaults()
        defaults.update({
            'start_memory': 1024,
            'max_memory': 4096,
            'thread_count': 2,
            'server_jar': 'minecraft_server.jar',
            'java_path': 'java',
            'java_args': ('-Xmx{}M -Xms{}M -XX:+UseConcMarkSweepGC '
                          '-XX:+CMSIncrementalPacing -XX:ParallelGCThreads={} '
                          '-XX:+AggressiveOpts -Dfml.queryResult=confirm'),
            'extra_args': 'nogui',
        })
        return defaults


    @staticmethod
    def excluded_from_save():
        parent = Java.excluded_from_save()
        return parent + [
            'extra_args',
            'java_args',
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
    @click.option('-sm', '--start_memory',
                  type=int,
                  help=('Starting amount of member (in MB)'))
    @click.option('-mm', '--max_memory',
                  type=int,
                  help=('Max amount of member (in MB)'))
    @click.option('-tc', '--thread_count',
                  type=int,
                  help=('Number of Garbage Collection Threads'))
    @click.option('-sj', '--server_jar',
                  type=click.Path(),
                  help='Path to Minecraft server jar')
    @click.option('-jp', '--java_path',
                  type=click.Path(),
                  help='Path to Java executable')
    @click.pass_obj
    def start(self, no_verify, *args, **kwargs):
        """ starts Minecraft server """

        java_args = self.options['java_args'].format(
            self.options['max_memory'],
            self.options['start_memory'],
            self.options['thread_count'],
        )

        self.options['command'] = self.command_format.format(
            self.options['java_path'],
            java_args,
            self.options['server_jar'],
            self.options['extra_args'],
        )
        self.invoke(
            super(Minecraft, self).start, no_verify=no_verify)
