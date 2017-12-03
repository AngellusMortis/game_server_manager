import os
import re
import time
from socket import timeout

import click
import click_spinner
from gs_manager.servers.java import Java
from gs_manager.utils import download_file, get_json
from mcstatus import MinecraftServer
from pygtail import Pygtail

VERSIONS_URL = 'https://launchermeta.mojang.com/mc/game/version_manifest.json'


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
            'say_command',
            'stop_command',
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
    @click.option('-ap', '--add_property',
                  type=str,
                  multiple=True)
    @click.option('-rp', '--remove_property',
                  type=str,
                  multiple=True)
    @click.option('--accept_eula',
                  is_flag=True,
                  default=False)
    @click.pass_obj
    def start(self, no_verify, history, start_memory,
              max_memory, thread_count, server_jar, java_path,
              add_property, remove_property, accept_eula):
        """ starts Minecraft server """

        self.debug_command('start', locals())
        history = history or self.options.get('history')
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

        if add_property or remove_property:
            for p in add_property:
                server_property = p.split('=')
                self.mc_config[server_property[0]] = server_property[1]

            for server_property in remove_property:
                del self.mc_config[server_property]

            property_path = os.path.join(
                self.options['path'], 'server.properties')
            server_property_string = ''
            for key, value in self.mc_config.items():
                server_property_string += '{}={}\n'.format(key, value)
            self.write_as_user(property_path, server_property_string)
            self._mc_config = None
            self.mc_config

        if accept_eula:
            eula_path = os.path.join(self.options['path'], 'eula.txt')
            self.write_as_user(eula_path, 'eula=true')

        self.invoke(
            super(Minecraft, self).start, no_verify=True,
            delay_start=0, java_args=java_args,
            server_jar=server_jar, java_path=java_path
        )

        if not no_verify:
            log_file = os.path.join(self.options['path'], 'logs', 'latest.log')
            self.debug('wait for server to start initalizing...')

            mtime = 0
            try:
                mtime = os.stat(log_file).st_mtime
            except FileNotFoundError:
                pass

            new_mtime = mtime
            wait_left = 5
            while new_mtime == mtime and wait_left > 0:
                try:
                    mtime = os.stat(log_file).st_mtime
                except FileNotFoundError:
                    pass
                wait_left -= 0.1
                time.sleep(0.1)

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
                            done_match = re.search(
                                'Done \((\d+\.\d+)s\)! For help,',
                                line
                            )
                            if done_match:
                                click.secho('{} is running'
                                            .format(self.options['name']),
                                            fg='green')
                                click.echo(
                                    'server initalization took {} seconds'
                                    .format(done_match.group(1)))
                                processing = False
                                break
                            elif 'agree to the EULA' in line:
                                raise click.ClickException(
                                    'You much agree to Mojang\'s EULA. '
                                    'Please read https://account.mojang.com/documents/minecraft_eula '
                                    'and restart server with --accept_eula')

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
            if os.path.isfile(offset_file):
                os.remove(offset_file)

    @click.command()
    @click.option('-f', '--force',
                  is_flag=True)
    @click.option('-b', '--beta',
                  is_flag=True)
    @click.option('-e', '--enable',
                  is_flag=True)
    @click.argument('minecraft_version',
                    type=str, required=False)
    @click.pass_obj
    def install(self, force, beta, enable, minecraft_version):
        """ installs a specific version of Minecraft """

        self.debug_command('install', locals())

        data = get_json(VERSIONS_URL)
        latest = data['latest']
        versions = {}
        for version in data['versions']:
            versions[version['id']] = version

        if minecraft_version is None:
            if beta:
                minecraft_version = latest['snapshot']
            else:
                minecraft_version = latest['release']
        elif minecraft_version not in versions:
            raise click.BadParameterException(
                'could not find minecraft version')

        self.debug('minecraft version:')
        self.debug(versions[minecraft_version])

        jar_dir = os.path.join(self.options['path'], 'jars')
        jar_file = 'minecraft_server.{}.jar'.format(minecraft_version)
        jar_path = os.path.join(jar_dir, jar_file)
        if os.path.isdir(jar_dir):
            if os.path.isfile(jar_path):
                if force:
                    os.remove(jar_path)
                else:
                    raise click.ClickException(
                        'minecraft v{} already installed'
                        .format(minecraft_version))
        else:
            os.makedirs(jar_dir)

        click.echo('downloading v{}...'.format(minecraft_version))
        version = get_json(versions[minecraft_version]['url'])
        download_file(
            version['downloads']['server']['url'],
            jar_path,
            sha1=version['downloads']['server']['sha1'])

        click.secho(
            'minecraft v{} installed'
            .format(minecraft_version),
            fg='green'
        )

        if enable:
            self.invoke(self.enable, minecraft_version=minecraft_version)

    @click.command()
    @click.option('-f', '--force',
                  is_flag=True)
    @click.argument('minecraft_version',
                    type=str)
    @click.pass_obj
    def enable(self, force, minecraft_version):
        """ enables a specific version of Minecraft """

        jar_dir = os.path.join(self.options['path'], 'jars')
        jar_file = 'minecraft_server.{}.jar'.format(minecraft_version)
        jar_path = os.path.join(jar_dir, jar_file)
        link_path = os.path.join(self.options['path'], 'minecraft_server.jar')

        if not os.path.isfile(jar_path):
            raise click.ClickException(
                'minecraft v{} is not installed'.format(minecraft_version))

        if not (os.path.islink(link_path) or force):
            raise click.ClickException(
                'minecraft_server.jar is not a symbolic link, '
                'use -f to override')

        if os.path.isfile(link_path):
            if os.path.realpath(link_path) == jar_path:
                raise click.ClickException(
                    'minecraft v{} already enabled'.format(minecraft_version))
            self.run_as_user('rm {}'.format(link_path))

        self.run_as_user('ln -s {} {}'.format(jar_path, link_path))

        click.secho(
            'minecraft v{} enabled'
            .format(minecraft_version),
            fg='green'
        )
