import os
import re
import time

import click
import click_spinner
from gs_manager.decorators import multi_instance, single_instance
from gs_manager.utils import download_file, get_json, get_param_obj
from gs_manager.validators import validate_key_value
from mcstatus import MinecraftServer
from pygtail import Pygtail

from ..generic import Java
from ..base import STATUS_FAILED, STATUS_PARTIAL_FAIL, STATUS_SUCCESS

VERSIONS_URL = 'https://launchermeta.mojang.com/mc/game/version_manifest.json'
EULA_URL = 'https://account.mojang.com/documents/minecraft_eula'


class Minecraft(Java):
    """
    Java based gameserver ran with screen for Minecraft.
    """
    _mc_config = None
    _server = None

    @staticmethod
    def defaults():
        defaults = Java.defaults()
        defaults.update({
            'stop_command': 'stop',
            'say_command': 'say {}',
            'start_memory': 1024,
            'max_memory': 4096,
            'thread_count': 2,
            'server_jar': 'minecraft_server.jar',
            'java_args': ('-Xmx{}M -Xms{}M -XX:+UseConcMarkSweepGC '
                          '-XX:+CMSIncrementalPacing -XX:ParallelGCThreads={} '
                          '-XX:+AggressiveOpts -Dfml.queryResult=confirm'),
            'extra_args': 'nogui',
            'delay_start': 0,
            'save_command': 'save',
            'add_property': [],
            'remove_property': [],
        })
        return defaults

    @staticmethod
    def excluded_from_save():
        parent = Java.excluded_from_save()
        return parent + [
            'accept_eula',
            'add_property',
            'beta',
            'delay_start',
            'detailed',
            'enable',
            'extra_args',
            'java_args',
            'minecraft_version',
            'remove_property',
            'save_command',
            'say_command',
            'stop_command',
        ]

    @property
    def mc_config(self):
        if self._mc_config is None:
            self._mc_config = {}

            config_path = os.path.join(
                self.config['path'], 'server.properties')
            if not os.path.isfile(config_path):
                raise click.clickException(
                    'could not find server.properties for Minecraft server')

            with open(config_path) as config_file:
                self._mc_config = validate_key_value(None, None, config_file)
            self.logger.debug('server.properties:')
            self.logger.debug(self._mc_config)

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

            self.logger.debug('Minecraft server: {}:{}'.format(ip, port))
            self._server = MinecraftServer(ip, int(port))
        return self._server

    def _process_log_file(self, log_file, instance_name):
        offset_file = '.log_offset'
        if os.path.isfile(offset_file):
            os.remove(offset_file)
        tail = Pygtail(log_file, offset_file=offset_file)
        loops_since_check = 0
        processing = True
        done_match = False
        with click_spinner.spinner():
            while processing:
                for line in tail.readlines():
                    self.logger.debug('log: {}'.format(line))
                    done_match = re.search(
                        'Done \((\d+\.\d+)s\)! For help,',
                        line
                    ) is not None
                    if done_match:
                        processing = False
                    elif 'agree to the EULA' in line:
                        self.logger.info('')
                        raise click.ClickException(
                            'You must agree to Mojang\'s EULA. '
                            'Please read {} and restart server '
                            'with --accept_eula'.format(EULA_URL))

                if loops_since_check < 5:
                    loops_since_check += 1
                elif self.is_running(instance_name):
                    loops_since_check = 0
                else:
                    self.logger.error(
                        '{} failed to start'.format(self.config['name']))
                    processing = False
                time.sleep(1)
        if os.path.isfile(offset_file):
            os.remove(offset_file)
        return done_match

    def _startup_check(self, instance_name=None):
        log_file = os.path.join(self.config['path'], 'logs', 'latest.log')
        self.logger.debug('wait for server to start initalizing...')

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
            if self._process_log_file(log_file, instance_name):
                self.logger.info(
                    '\nverifying Minecraft server is up...',
                    nl=False,
                )
                return super(Minecraft, self)._startup_check(
                    instance_name)
        else:
            raise click.ClickException(
                'could not find log file: {}'
                .format(log_file))

    def is_accessible(self, instance_name=None):
        try:
            ping = self.server.ping()
            self.logger.debug('ping: {}'.format(ping))
        except Exception:
            return False
        return True

    @multi_instance
    @click.command()
    @click.option('-d', '--detailed',
                  is_flag=True,
                  help='returns more detatiled infomation about the server')
    @click.pass_obj
    def status(self, detailed, *args, **kwargs):
        """ checks if Minecraft server is running or not """

        if self.is_running(self.config['current_instance']):
            if detailed and not self.mc_config.get('enable-query') == 'true':
                raise click.ClickException(
                    'query is not enabled in server.properties')

            query = None
            try:
                if detailed:
                    query = self.server.query()
                status = self.server.status()
            except ConnectionRefusedError:
                self.logger.error(
                    '{} is running, but not accessible'
                    .format(self.config['name'])
                )
                return STATUS_FAILED
            else:
                self.logger.success(
                    '{} is running'.format(self.config['name'])
                )
                if query is not None:
                    self.logger.info(
                        'host: {}:{}'.format(
                            query.raw['hostip'],
                            query.raw['hostport'],
                        )
                    )
                    self.logger.info(
                        'software: v{} {}'.format(
                            query.software.version,
                            query.software.brand,
                        )
                    )
                self.logger.info(
                    'version: v{} (protocol {})'.format(
                        status.version.name,
                        status.version.protocol,
                    )
                )
                self.logger.info(
                    'description: "{}"'.format(
                        status.description,
                    )
                )
                if query is not None:
                    self.logger.info(
                        'plugins: {}'.format(query.software.plugins)
                    )
                    self.logger.info(
                        'motd: "{}"'.format(query.motd)
                    )

                self.logger.info(
                    'players: {}/{}'.format(
                        status.players.online,
                        status.players.max,
                    )
                )

                if query is not None:
                    self.logger.info(query.players.names)
                return STATUS_SUCCESS
        else:
            self.logger.warning(
                '{} is not running'.format(self.config['name'])
            )
            return STATUS_PARTIAL_FAIL

    @multi_instance
    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True)
    @click.option('-hc', '--history',
                  type=int,
                  help='Number of lines to show in screen for history')
    @click.option('-mt', '--max_start',
                  type=int,
                  help='Max time (in seconds) to wait before assuming the '
                       'server is deadlocked')
    @click.option('-sm', '--start_memory',
                  type=int,
                  help='Starting amount of member (in MB)')
    @click.option('-mm', '--max_memory',
                  type=int,
                  help='Max amount of member (in MB)')
    @click.option('-tc', '--thread_count',
                  type=int,
                  help='Number of Garbage Collection Threads')
    @click.option('-sj', '--server_jar',
                  type=click.Path(),
                  help='Path to Minecraft server jar')
    @click.option('-jp', '--java_path',
                  type=click.Path(),
                  help='Path to Java executable')
    @click.option('-fg', '--foreground',
                  is_flag=True,
                  help='Start gameserver in foreground. Ignores '
                       'spawn_progress, screen, and any other '
                       'options or classes that cause server to run '
                       'in background.')
    @click.option('-ap', '--add_property',
                  type=str,
                  multiple=True,
                  help='Adds (or modifies) a property in the '
                       'server.properties file')
    @click.option('-rp', '--remove_property',
                  type=str,
                  multiple=True,
                  help='Removes a property from the server.properties')
    @click.option('--accept_eula',
                  is_flag=True,
                  default=False,
                  help='Forcibly accepts the Mojang EULA before starting the '
                       'server. Be sure to read {} before accepting'
                       .format(EULA_URL))
    @click.pass_obj
    def start(self, no_verify, accept_eula, *args, **kwargs):
        """ starts Minecraft server """

        java_args = self.config['java_args'].format(
            self.config['max_memory'],
            self.config['start_memory'],
            self.config['thread_count'],
        )

        if self.config['add_property'] or self.config['remove_property']:
            properties = validate_key_value(
                None, None, self.config['add_property']
            )
            self.mc_config.update(properties)

            for server_property in self.config['remove_property']:
                del self.mc_config[server_property]

            property_path = os.path.join(
                self.config['path'], 'server.properties')
            server_property_string = ''
            for key, value in self.mc_config.items():
                server_property_string += '{}={}\n'.format(key, value)
            self.write_as_user(property_path, server_property_string)
            self._mc_config = None
            self.mc_config

        if accept_eula:
            eula_path = os.path.join(self.config['path'], 'eula.txt')
            self.write_as_user(eula_path, 'eula=true')

        return self.invoke(
            super(Minecraft, self).start,
            java_args=java_args,
            no_verify=no_verify,
        )

    @multi_instance
    @click.command()
    @click.argument('command_string')
    @click.pass_obj
    def command(self, command_string, do_print=True, *args, **kwargs):
        """ runs console command """

        tail = None
        log_file = os.path.join(self.config['path'], 'logs', 'latest.log')
        if do_print and os.path.isfile(log_file):
            self.logger.debug('reading log...')
            offset_file = '.log_offset'
            if os.path.isfile(offset_file):
                os.remove(offset_file)
            tail = Pygtail(log_file, offset_file=offset_file)
            tail.readlines()

        status = self.invoke(
            super(Minecraft, self).command,
            command_string=command_string,
            do_print=False
        )

        if status == STATUS_SUCCESS and do_print and tail is not None:
            time.sleep(1)
            self.logger.debug('looking for command output...')
            for line in tail.readlines():
                match = re.match(
                    '(\[.*] \[.*]: *)?(?P<message>[^\n]+)?',
                    line.strip()
                )
                if match is not None:
                    message = match.group('message')
                    if not message == '':
                        self.logger.info(message)
            if os.path.isfile(offset_file):
                os.remove(offset_file)
        return status

    @single_instance
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
    def install(self, force, beta, enable, minecraft_version, *args, **kwargs):
        """ installs a specific version of Minecraft """

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
            raise click.BadParameter(
                'could not find minecraft version',
                self.context,
                get_param_obj(self.context, 'minecraft_version'),
            )

        self.logger.debug('minecraft version:')
        self.logger.debug(versions[minecraft_version])

        jar_dir = os.path.join(self.config['path'], 'jars')
        jar_file = 'minecraft_server.{}.jar'.format(minecraft_version)
        jar_path = os.path.join(jar_dir, jar_file)
        if os.path.isdir(jar_dir):
            if os.path.isfile(jar_path):
                if force:
                    os.remove(jar_path)
                else:
                    raise click.BadParameter(
                        'minecraft v{} already installed'
                        .format(minecraft_version),
                        self.context,
                        get_param_obj(self.context, 'minecraft_version')
                    )
        else:
            os.makedirs(jar_dir)

        self.logger.info('downloading v{}...'.format(minecraft_version))
        version = get_json(versions[minecraft_version]['url'])
        download_file(
            version['downloads']['server']['url'],
            jar_path,
            sha1=version['downloads']['server']['sha1'])

        self.logger.success(
            'minecraft v{} installed'.format(minecraft_version))

        link_path = os.path.join(self.config['path'], 'minecraft_server.jar')
        if not os.path.isfile(link_path) or enable:
            return self.invoke(
                self.enable,
                minecraft_version=minecraft_version,
            )
        return STATUS_SUCCESS

    @single_instance
    @click.command()
    @click.option('-f', '--force',
                  is_flag=True)
    @click.argument('minecraft_version',
                    type=str)
    @click.pass_obj
    def enable(self, force, minecraft_version, *args, **kwargs):
        """ enables a specific version of Minecraft """

        if self.is_running(self.config['current_instance']):
            self.logger.error(
                '{} is still running'.format(self.config['name'])
            )
            return STATUS_FAILED

        jar_dir = os.path.join(self.config['path'], 'jars')
        jar_file = 'minecraft_server.{}.jar'.format(minecraft_version)
        jar_path = os.path.join(jar_dir, jar_file)
        link_path = os.path.join(self.config['path'], 'minecraft_server.jar')

        if not os.path.isfile(jar_path):
            raise click.BadParameter(
                'minecraft v{} is not installed'
                .format(minecraft_version),
                self.context,
                get_param_obj(self.context, 'minecraft_version')
            )

        if not (os.path.islink(link_path) or force or
                not os.path.isfile(link_path)):
            raise click.ClickException(
                'minecraft_server.jar is not a symbolic link, '
                'use -f to override')

        if os.path.isfile(link_path):
            if os.path.realpath(link_path) == jar_path:
                raise click.BadParameter(
                    'minecraft v{} already enabled'
                    .format(minecraft_version),
                    self.context,
                    get_param_obj(self.context, 'minecraft_version')
                )
            self.run_as_user('rm {}'.format(link_path))

        self.run_as_user('ln -s {} {}'.format(jar_path, link_path))

        self.logger.success('minecraft v{} enabled'.format(minecraft_version))
        return STATUS_SUCCESS

    @single_instance
    @click.command()
    @click.pass_obj
    def versions(self, *args, **kwargs):
        """ lists installed versions of Minecraft """

        jar_dir = os.path.join(self.config['path'], 'jars')

        versions = []
        for root, dirs, files in os.walk(jar_dir):
            for filename in files:
                if filename.endswith('.jar'):
                    parts = filename.split('.')
                    versions.append('.'.join(parts[1:-1]))
        self.logger.info(versions)
        return STATUS_SUCCESS
