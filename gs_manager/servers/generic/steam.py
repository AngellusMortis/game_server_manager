import re
import time
from subprocess import CalledProcessError
from threading import Thread

import click
import click_spinner
from gs_manager.decorators import multi_instance, single_instance
from gs_manager.validators import validate_int_list
from valve.source import NoResponseError
from valve.source.a2s import ServerQuerier

from ..base import STATUS_FAILED, STATUS_PARTIAL_FAIL, STATUS_SUCCESS, Base

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty


def _enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()


class Steam(Base):
    """
    Generic gameserver that can be installed and updated from Steam.
    Also, optionally support Steam workshop. Requires additional
    configuration to work.
    """

    _servers = {}

    @staticmethod
    def defaults():
        defaults = Base.defaults()
        defaults.update({
            'app_id': None,
            'steam_query_ip': '127.0.0.1',
            'steam_query_port': 27015,
            'steamcmd_path': 'steamcmd',
            'workshop_id': None,
            'workshop_items': [],
        })
        return defaults

    @staticmethod
    def global_options():
        global_options = Base.global_options()
        all_options = [
            {
                'param_decls': ('-sc', '--steamcmd_path'),
                'type': click.Path(),
                'help': 'Path to steamcmd executable',
            },
            {
                'param_decls': ('-a', '--app_id'),
                'type': int,
                'help': 'app ID for Steam game to update from',
            },
            {
                'param_decls': ('-sqp', '--steam_query_port'),
                'type': int,
                'help': 'Port to query to check if server is accessible',
            },
            {
                'param_decls': ('-sqi', '--steam_query_ip'),
                'type': int,
                'help': 'IP to query to check if server is accessible',
            }
        ]
        global_options['all'] += all_options
        return global_options

    def is_accessible(self, instance_name=None):
        server = self.get_server(instance_name)
        if server is not None:
            try:
                server.ping()
            except NoResponseError:
                return False
        return True

    def _parse_line(self, bar, line):
        step_name = line.group('step_name')
        current = int(line.group('current'))
        total = int(line.group('total'))
        self.logger.debug(
            'processed: {}: {} / {}'
            .format(step_name, current, total)
        )
        if bar is None and current < total:
            bar = click.progressbar(
                length=total, show_eta=False,
                show_percent=True, label=step_name
            )
        if bar is not None:
            bar.update(current)

    def _wait_until_validated(self, process, detailed_status=False):
        if detailed_status:
            # this does not work as expected because of a steamcmd bug
            # https://github.com/ValveSoftware/Source-1-Games/issues/1684
            # https://github.com/ValveSoftware/Source-1-Games/issues/1929
            buffer = Queue()
            thread = Thread(
                target=_enqueue_output,
                args=(process.stdout, buffer),
                daemon=True,
            )
            thread.start()

            bar = None
            line_re = re.compile(
                r'Update state \(0x\d+\) (?P<step_name>\w+), progress: '
                r'\d+\.\d+ \((?P<current>\d+) \/ (?P<total>\d+)\)'
            )

            self.logger.debug('start processing output...')
            while True:
                try:
                    line = buffer.get_nowait().decode('utf-8').strip()
                except Empty:
                    time.sleep(0.1)
                else:
                    self.logger.debug('line: {}'.format(line))
                    self._parse_line(bar, line_re.match(line))

                if process.poll() is not None and buffer.empty():
                    break
        else:
            self.logger.info(
                'validating {}...'.format(self.config['app_id']),
                nl=False,
            )

            with click_spinner.spinner():
                while process.poll() is None:
                    time.sleep(1)

    def get_server(self, instance_name=None):
        if self._servers.get(instance_name) is None:
            i_config = self.config.get_instance_config(instance_name)
            if i_config is not None:
                self._servers[instance_name] = ServerQuerier((
                    i_config['steam_query_ip'],
                    i_config['steam_query_port'],
                ))
        return self._servers[instance_name]

    @multi_instance
    @click.command()
    @click.pass_obj
    def status(self, *args, **kwargs):
        """ checks if Steam server is running or not """

        instance = self.config['current_instance']
        i_config = self.config.get_instance_config(instance)

        if self.is_running(instance):
            server = self.get_server(instance)
            try:
                server_info = server.info()
                self.logger.success(
                    '{} is running'.format(self.config['name'])
                )
                self.logger.info(
                    'server name: {}'.format(server_info['server_name'])
                )
                self.logger.info('map: {}'.format(server_info['map']))
                self.logger.info('game: {}'.format(server_info['game']))
                self.logger.info(
                    'players: {}/{} ({} bots)'
                    .format(
                        server_info['player_count'],
                        server_info['max_players'],
                        server_info['bot_count'],
                    )
                )
                self.logger.info(
                    'server type: {}'.format(server_info['server_type'])
                )
                self.logger.info(
                    'password protected: {}'
                    .format(server_info['password_protected'])
                )
                self.logger.info('VAC: {}'.format(server_info['vac_enabled']))
                self.logger.info('version: {}'.format(server_info['version']))
            except NoResponseError:
                self.logger.error(
                    '{} is running but not accesible'
                    .format(i_config['name'])
                )
        else:
            self.logger.warning('{} is not running'.format(i_config['name']))

    @single_instance
    @click.command()
    @click.pass_obj
    def install(self, *args, **kwargs):
        """ installs/validates/updates the gameserver """

        self._require_param(self.config, 'app_id')
        self._require_command(self.config['steamcmd_path'], 'steamcmd_path')

        if self.is_running('@any'):
            self.logger.warning(
                '{} is still running'.format(self.config['name'])
            )
            return STATUS_PARTIAL_FAIL
        else:
            process = self.run_as_user(
                '{} +login anonymous +force_install_dir {} +app_update '
                '{} validate +quit'
                .format(
                    self.config['steamcmd_path'],
                    self.config['path'],
                    self.config['app_id'],
                ),
                redirect_output=True,
                return_process=True,
            )

            self._wait_until_validated(process)

            if process.returncode == 0:
                self.logger.success(
                    '\nvalidated {}'.format(self.config['app_id']))
                return STATUS_SUCCESS
            else:
                self.logger.error(
                    '\nfailed to validate {}'.format(self.config['name']))
                return STATUS_FAILED

    @single_instance
    @click.command()
    @click.option('-w', '--workshop_id',
                  type=int,
                  help='Workshop ID to use for downloading workshop '
                       'items from')
    @click.option('-wi', '--workshop_items',
                  callback=validate_int_list,
                  help='List of comma seperated IDs for workshop items'
                       'to download')
    @click.pass_obj
    def workshop_download(self, *args, **kwargs):
        """ downloads Steam workshop items """

        self._require_param(self.config, 'workshop_id')

        if self.is_running('@any'):
            self.logger.warning(
                '{} is still running'.format(self.config['name']))
            status = STATUS_PARTIAL_FAIL
        else:
            status = self.invoke(
                self.install,
                app_id=self.config['workshop_id'],
            )

            if status == STATUS_SUCCESS:
                self.logger.info('downloading workshop items...')
                with click.progressbar(self.config['workshop_items']) as bar:
                    for workshop_item in bar:
                        try:
                            self.run_as_user(
                                '{} +login anonymous +force_install_dir {} '
                                '+workshop_download_item {} {} +quit'
                                .format(
                                    self.config['steamcmd_path'],
                                    self.config['path'],
                                    self.config['workshop_id'],
                                    workshop_item,
                                ),
                            )
                        except CalledProcessError:
                            self.logger.error(
                                '\nfailed to validate workshop items'
                            )
                            return STATUS_FAILED

                if len(self.config['workshop_id']) == 0:
                    self.logger.warning(
                        '\nno workshop items selected for install'
                    )
                    status = STATUS_PARTIAL_FAIL
                else:
                    self.logger.success('\nvalidated workshop items')
                    status = STATUS_SUCCESS
        return status
