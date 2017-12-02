import os
import re
from pygtail import Pygtail
import time
from socket import timeout

import click_spinner

import click
from gs_manager.servers.java import Java
from mcstatus import MinecraftServer


class Minecraft(Java):
    _mc_config = None
    _server = None

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

    @property
    def mc_config(self):
        if self._mc_config is None:
            self._mc_config = {}

            config_path = os.path.join(
                self.options['path'], 'server.properties')
            if not os.path.isfile(config_path):
                raise click.clickException(
                    'could not find server.properties for Minecraft server')

            with open(config_path) as config_file:
                for line in config_file:
                    line = line.strip()
                    if not line.startswith('#'):
                        option = line.split('=')
                        self._mc_config[option[0]] = option[1]
            self.debug('server.properties:')
            self.debug(self._mc_config)

        return self._mc_config

    @property
    def server(self):
        if self._server is None:
            ip = self.mc_config.get('server-ip')
            port = self.mc_config.get('server-port')

            if ip == '' or ip is None:
                ip = '127.0.0.1'
            if port == '' or port is None:
                port = '25565'

            self.debug('minecraft server: {}:{}'.format(ip, port))
            self._server = MinecraftServer(ip, int(port))
        return self._server

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
    def start(self, no_verify, history, delay_start, start_memory,
              max_memory, thread_count, server_jar, java_path):
        """ starts Minecraft server """

        self.debug_command('start', locals())
        history = history or self.options.get('history')
        delay_start = delay_start or self.options.get('delay_start')
        start_memory = start_memory or self.options.get('start_memory')
        max_memory = max_memory or self.options.get('max_memory')
        thread_count = thread_count or self.options.get('thread_count')
        server_jar = server_jar or self.options.get('server_jar')
        java_path = java_path or self.options.get('java_path')

        java_args = self.options['java_args'].format(
            max_memory,
            start_memory,
            thread_count,
        )

        self.invoke(
            super(Minecraft, self).start, no_verify=True,
            delay_start=delay_start, java_args=java_args,
            server_jar=server_jar, java_path=java_path
        )

        if not no_verify:
            self.debug('wait 2 seconds for logs to start...')
            time.sleep(2)
            log_file = os.path.join(self.options['path'], 'logs', 'latest.log')
            if os.path.isfile(log_file):
                offset_file = '.log_offset'
                if os.path.isfile(offset_file):
                    os.remove(offset_file)
                tail = Pygtail(log_file, offset_file=offset_file)
                loops_since_check = 0
                processing = True
                with click_spinner.spinner():
                    while processing:
                        for line in tail.readlines():
                            self.debug('log: {}'.format(line))
                            match = re.search('Done \((\d+\.\d+)s\)! For help,', line)
                            if match:
                                click.secho('{} is running'
                                            .format(self.options['name']),
                                            fg='green')
                                click.echo('server initalization took {} seconds'.format(match.group(1)))
                                processing = False
                                break

                        if loops_since_check < 5:
                            loops_since_check += 1
                        elif self.running:
                            loops_since_check = 0
                        else:
                            click.secho('{} failed to start'
                                        .format(self.options['name']),
                                        fg='red')
                            processing = False
                        time.sleep(1)
                if os.path.isfile(offset_file):
                    os.remove(offset_file)
            else:
                raise click.ClickException('could not find log file: {}'.format(log_file))

    @click.command()
    @click.pass_obj
    def status(self):
        """ checks if gameserver is runing or not """

        self.debug_command('status')

        is_running = self.running
        if is_running:
            try:
                status = self.server.status()
            except ConnectionRefusedError as ex:
                click.secho(
                    '{} is running but not responding (starting up still?)'
                    .format(self.options['name']),
                    fg='red')
            else:
                click.secho('{} is running'
                            .format(self.options['name']),
                            fg='green')
                click.echo(
                    'version: v{} (protocol {})'.format(
                        status.version.name,
                        status.version.protocol))
                click.echo(
                    'description: "{}"'.format(status.description))
                if status.players.sample is not None:
                    players = [
                        '{} ({})'.format(player.name, player.id)
                        for player in status.players.sample
                    ]
                else:
                    players = 'No players online'

                click.echo(
                    'players: {}/{} {}'.format(
                        status.players.online,
                        status.players.max,
                        players
                    )
                )
        else:
            click.secho('{} is not running'
                        .format(self.options['name']),
                        fg='red')

    @click.command()
    @click.pass_obj
    def query(self):
        """ retrieves extended information about server if it is running """

        self.debug_command('query')

        if not self.mc_config.get('enable-query') == 'true':
            raise click.ClickException(
                'query is not enabled in server.properties')

        if self.running:
            try:
                query = self.server.query()
            except timeout:
                raise click.ClickException(
                    'could not query server, check firewall')

            click.echo('host: {}:{}'
                       .format(query.raw['hostip'], query.raw['hostport']))
            click.echo('software: v{} {}'
                       .format(query.software.version, query.software.brand))
            click.echo('plugins: {}'.format(query.software.plugins))
            click.echo('motd: "{}"'.format(query.motd))
            click.echo(
                'players: {}/{} {}'.format(
                    query.players.online,
                    query.players.max,
                    query.players.names,
                )
            )
        else:
            click.secho('{} is not running'
                        .format(self.options['name']),
                        fg='red')

    @click.command()
    @click.argument('command_string')
    @click.pass_obj
    def command(self, command_string, do_print=True):
        """ runs console command """

        self.debug_command('command', locals())

        tail = None
        log_file = os.path.join(self.options['path'], 'logs', 'latest.log')
        if do_print and os.path.isfile(log_file):
            self.debug('reading log...')
            offset_file = '.log_offset'
            if os.path.isfile(offset_file):
                os.remove(offset_file)
            tail = Pygtail(log_file, offset_file=offset_file)
            tail.readlines()

        self.invoke(
            super(Minecraft, self).command,
            command_string=command_string,
            do_print=False
        )

        if do_print and tail is not None:
            time.sleep(1)
            self.debug('looking for command output...')
            for line in tail.readlines():
                match = re.match(
                    '(\[.*] \[.*]: *)?(?P<message>[^\n]+)?',
                    line.strip()
                )
                if match is not None:
                    message = match.group('message')
                    if not message == '':
                        click.echo(message)
            # if os.path.isfile(offset_file):
            #     os.remove(offset_file)
