import os
import shutil
import struct
import zlib

import click
from gs_manager.decorators import multi_instance, single_instance
from gs_manager.servers.base import STATUS_FAILED, STATUS_SUCCESS
from gs_manager.validators import validate_int_list, validate_key_value

from ..generic import Rcon

STEAM_DOWNLOAD_URL = 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz'


class Ark(Rcon):
    """
    Steam based gameserver with RCON support for ARK: Surivial Evolved.
    """

    def __init__(self, *args, **kwargs):
        super(Ark, self).__init__(
            supports_multi_instance=True, *args, **kwargs)

    @staticmethod
    def defaults():
        defaults = Rcon.defaults()
        defaults.update({
            'app_id': '376030',
            'workshop_id': '346110',
            'ark_map': 'TheIsland',
            'ark_params': {},
            'ark_options': {},
            'spawn_process': True,
            'stop_command': 'DoExit',
            'say_command': 'Broadcast {}',
            'save_command': 'SaveWorld',
            'max_start': 120,
            'workshop_branch': 'Windows',
            'rcon_multi_part': False,
        })
        return defaults

    @staticmethod
    def excluded_from_save():
        parent = Rcon.excluded_from_save()
        return parent + [
            'say_command',
            'spawn_process',
            'command',
            'stop_command',
            'save_command',
            'rcon_multi_part',
        ]

    def get_ark_config(self, instance_name=None):
        i_config = self.config.get_instance_config(instance_name)
        ark_config = {
            'map': i_config['ark_map'],
            'params': i_config['ark_params'],
            'options': i_config['ark_options'],
        }

        if not i_config['steam_query_ip'] == '127.0.0.1':
            ark_config['params']['MultiHome'] = i_config['steam_query_ip']

        if i_config['steam_query_port'] is not None:
            ark_config['params']['QueryPort'] = i_config['steam_query_port']

        if self.is_rcon_enabled(instance_name):
            ark_config['params']['RCONEnabled'] = True
            ark_config['params']['RCONPort'] = i_config['rcon_port']
        ark_config['params']['ServerAdminPassword'] = \
            i_config['rcon_password'] or \
            ark_config['params'].get('ServerAdminPassword')

        if len(i_config['workshop_items']) > 0:
            ark_config['params']['GameModIds'] = \
                ','.join([str(i) for i in i_config['workshop_items']])

        self.logger.debug('ark config:')
        self.logger.debug(ark_config)
        return ark_config

    def _make_command_args(self, ark_config):
        command_args = ark_config['map']

        for key, value in ark_config['params'].items():
            param = key
            if value is not None:
                param += '={}'.format(str(value).replace(' ', '\\ '))
            command_args += '?{}'.format(param)

        for key, value in ark_config['options'].items():
            param = key
            if value is not None:
                param += '={}'.format(str(value).replace(' ', '\\ '))
            command_args += ' -{}'.format(param)

        self.logger.debug('command args: {}'.format(command_args))
        return command_args

    def _z_unpack(self, from_path, to_path):
        """
        unpacks .z files downloaded from Steam workshop

        adapted from https://github.com/TheCherry/ark-server-manager/blob/master/src/z_unpack.py
        """
        with open(from_path, 'rb') as f_from:
            with open(to_path, 'wb') as f_to:
                f_from.read(8)
                size1 = struct.unpack('q', f_from.read(8))[0]
                f_from.read(8)
                size2 = struct.unpack('q', f_from.read(8))[0]
                if size1 == -1641380927:
                    size1 = 131072
                runs = (size2 + size1 - 1) / size1
                array = []
                for i in range(int(runs)):
                    array.append(f_from.read(8))
                    f_from.read(8)
                for i in range(int(runs)):
                    to_read = array[i]
                    compressed = f_from.read(struct.unpack('q', to_read)[0])
                    decompressed = zlib.decompress(compressed)
                    f_to.write(decompressed)

    def _read_ue4_string(self, file_obj):
        """
        reads a UE4 string from a file object

        adapted from https://github.com/barrycarey/Ark_Mod_Downloader/blob/master/Ark_Mod_Downloader.py
        """
        count = struct.unpack('i', file_obj.read(4))[0]
        flag = False
        if count < 0:
            flag = True
            count -= 1

        if flag or count <= 0:
            return ""

        return file_obj.read(count)[:-1].decode()

    def _write_ue4_string(self, string_to_write, file_obj):
        """
        writes a UE4 string to a file object

        adapted from https://github.com/barrycarey/Ark_Mod_Downloader/blob/master/Ark_Mod_Downloader.py
        """
        string_length = len(string_to_write) + 1
        file_obj.write(struct.pack('i', string_length))
        barray = bytearray(string_to_write, "utf-8")
        file_obj.write(barray)
        file_obj.write(struct.pack('p', b'0'))

    def _parse_base_info(self, mod_info_file):
        """
        parses an ARK mod.info file

        adapted from https://github.com/barrycarey/Ark_Mod_Downloader/blob/master/Ark_Mod_Downloader.py
        """
        map_names = []
        with open(mod_info_file, 'rb') as f:
            self._read_ue4_string(f)
            map_count = struct.unpack('i', f.read(4))[0]

            for x in range(map_count):
                cur_map = self._read_ue4_string(f)
                if cur_map:
                    map_names.append(cur_map)
        return map_names

    def _parse_meta_data(self, mod_meta_file):
        """
        parses an ARK modmeta.info file

        adapted from https://github.com/barrycarey/Ark_Mod_Downloader/blob/master/Ark_Mod_Downloader.py
        """
        meta_data = {}
        with open(mod_meta_file, 'rb') as f:
            total_pairs = struct.unpack('i', f.read(4))[0]

            for x in range(total_pairs):
                key, value = None, None

                key_bytes = struct.unpack('i', f.read(4))[0]
                key_flag = False
                if key_bytes < 0:
                    key_flag = True
                    key_bytes -= 1

                if not key_flag and key_bytes > 0:
                    raw = f.read(key_bytes)
                    key = raw[:-1].decode()

                value_bytes = struct.unpack('i', f.read(4))[0]
                value_flag = False
                if value_bytes < 0:
                    value_flag = True
                    value_bytes -= 1

                if not value_flag and value_bytes > 0:
                    raw = f.read(value_bytes)
                    value = raw[:-1].decode()

                if key and value:
                    meta_data[key] = value
        return meta_data

    def _create_mod_file(self, mod_dir, mod_file, mod_id):
        self.logger.debug('createing .mod file for {}...'.format(mod_id))
        mod_info_file = os.path.join(mod_dir, 'mod.info')
        mod_meta_file = os.path.join(mod_dir, 'modmeta.info')

        if os.path.isfile(mod_info_file) and os.path.isfile(mod_meta_file):
            map_names = self._parse_base_info(mod_info_file)
            meta_data = self._parse_meta_data(mod_meta_file)

            if len(map_names) > 0 and len(meta_data) > 0:
                with open(mod_file, 'w+b') as f:
                    f.write(struct.pack('ixxxx', mod_id))
                    self._write_ue4_string('ModName', f)
                    self._write_ue4_string('', f)

                    map_count = len(map_names)
                    f.write(struct.pack('i', map_count))
                    for m in map_names:
                        self._write_ue4_string(m, f)

                    f.write(struct.pack('I', 4280483635))
                    f.write(struct.pack('i', 2))

                    if 'ModType' in meta_data:
                        mod_type = b'1'
                    else:
                        mod_type = b'0'

                    f.write(struct.pack('p', mod_type))
                    meta_length = len(meta_data)
                    f.write(struct.pack('i', meta_length))

                    for key, value in meta_data.items():
                        self._write_ue4_string(key, f)
                        self._write_ue4_string(value, f)
                    return True

        return False

    @multi_instance
    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True,
                  help='Do not wait until gameserver is running before '
                       'exiting')
    @click.option('-ds', '--delay_start',
                  type=int,
                  help='Time (in seconds) to wait after running the command '
                       'before checking the server')
    @click.option('-mt', '--max_start',
                  type=int,
                  help='Max time (in seconds) to wait before assuming the '
                       'server is deadlocked')
    @click.option('-fg', '--foreground',
                  is_flag=True,
                  help='Start gameserver in foreground. Ignores '
                       'spawn_progress, screen, and any other '
                       'options or classes that cause server to run '
                       'in background.')
    @click.option('-am', '--ark_map',
                  type=str,
                  help='Map to initalize ARK server with')
    @click.option('-ap', '--ark_params',
                  type=str,
                  multiple=True,
                  callback=validate_key_value,
                  help='? parameters to pass to ARK server. MultiHome, '
                       'QueryPort, RCONEnabled, RCONPort, and GameModIds '
                       'not supported, see other options for those. '
                       'ServerAdminPassword also not support if '
                       '--rcon_password is passed in')
    @click.option('-ao', '--ark_options',
                  type=str,
                  multiple=True,
                  callback=validate_key_value,
                  help='- options to pass to ARK server. -log, -server, '
                       '-servergamelog, -servergamelogincludetribelogs '
                       'passed in automatically. -automanagedmods is '
                       'not supported (yet).')
    @click.option('-wi', '--workshop_items',
                  callback=validate_int_list,
                  help='Comma list of mod IDs to pass to ARK server')
    @click.pass_obj
    def start(self, no_verify, *args, **kwargs):
        """ starts ARK server """

        ark_config = self.get_ark_config(self.config['current_instance'])
        config_args = self._make_command_args(ark_config)

        server_command = os.path.join(
            self.config['path'], 'ShooterGame',
            'Binaries', 'Linux', 'ShooterGameServer')

        command = ('{} {} -server -servergamelog -log '
                   '-servergamelogincludetribelogs').format(
                        server_command,
                        config_args,
                    )

        if 'automanagedmods' in command:
            self.logger.error('-automanagedmods option is not supported')
            return STATUS_FAILED

        return self.invoke(
            super(Ark, self).start,
            no_verify=no_verify,
            command=command,
        )

    @single_instance
    @click.command()
    @click.pass_obj
    def install(self, *args, **kwargs):
        """ installs/validates/updates the ARK server """

        status = self.invoke(
            super(Ark, self).install
        )

        self.logger.debug('super status: {}'.format(status))

        if status == STATUS_SUCCESS:
            steamcmd_dir = os.path.join(
                self.config['path'], 'Engine', 'Binaries',
                'ThirdParty', 'SteamCMD', 'Linux'
            )
            steamcmd_path = os.path.join(steamcmd_dir, 'steamcmd.sh')

            if not os.path.isdir(steamcmd_dir):
                self.run_as_user('mkdir -p {}'.format(steamcmd_dir))

            if not os.path.isfile(steamcmd_path):
                self.logger.info('installing Steam locally for ARK...')
                self.run_as_user(
                    'wget {}'.format(STEAM_DOWNLOAD_URL), cwd=steamcmd_dir)
                self.run_as_user(
                    'tar -xf steamcmd_linux.tar.gz', cwd=steamcmd_dir)
                self.run_as_user('rm steamcmd_linux.tar.gz', cwd=steamcmd_dir)
                self.run_as_user('{} +quit'.format(steamcmd_path))
                self.logger.success('Steam installed successfully')

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
    @click.option('-wb', '--workshop_branch',
                  type=str,
                  help='Branch to use for workshop items for the ARK mod. '
                       'Defaults to Windows, Linux branch is usually highly '
                       'unstable. Do not change unless you know what you '
                       'are doing')
    @click.pass_obj
    def workshop_download(self, *args, **kwargs):
        """ downloads and installs ARK mods """
        status = self.invoke(
            super(Ark, self).workshop_download
        )

        self.logger.debug('super status: {}'.format(status))

        if status == STATUS_SUCCESS:
            self.logger.info('extracting mods...')
            mod_path = os.path.join(
               self.config['path'], 'ShooterGame', 'Content', 'Mods')
            base_src_dir = os.path.join(
                self.config['path'], 'steamapps', 'workshop',
                'content', str(self.config['workshop_id'])
            )

            self.logger.debug('mod_path: {}'.format(mod_path))
            self.logger.debug('base_src_dir: {}'.format(base_src_dir))

            with click.progressbar(self.config['workshop_items']) as bar:
                for workshop_item in bar:
                    src_dir = os.path.join(base_src_dir, str(workshop_item))
                    branch_dir = os.path.join(
                        src_dir,
                        '{}NoEditor'.format(self.config['workshop_branch'])
                    )
                    mod_dir = os.path.join(mod_path, str(workshop_item))
                    mod_file = os.path.join(
                        mod_path, '{}.mod'.format(workshop_item))

                    if not os.path.isdir(src_dir):
                        self.logger.error(
                            'could not find workshop item: {}'
                            .format(self.config['workshop_id']))
                        return STATUS_FAILED
                    elif os.path.isdir(branch_dir):
                        src_dir = branch_dir

                    if os.path.isdir(mod_dir):
                        self.logger.debug(
                            'removing old mod_dir of {}...'
                            .format(workshop_item))
                        self.run_as_user('rm -r {}'.format(mod_dir))
                    if os.path.isfile(mod_file):
                        self.logger.debug(
                            'removing old mod_file of {}...'
                            .format(workshop_item))
                        self.run_as_user('rm {}'.format(mod_file))

                    self.logger.debug('copying {}...'.format(workshop_item))
                    shutil.copytree(src_dir, mod_dir)

                    if not self._create_mod_file(
                            mod_dir, mod_file, workshop_item):
                        self.logger.error(
                            'could not create .mod file for {}'
                            .format(workshop_item)
                        )
                        return STATUS_FAILED

                    for root, dirs, files in os.walk(mod_dir):
                        for filename in files:
                            if filename.endswith('.z'):
                                file_path = os.path.join(root, filename)
                                to_extract_path = file_path[:-2]
                                size_file = '{}.uncompressed_size'.format(
                                    file_path)
                                size = None

                                if os.path.isfile(size_file):
                                    with open(size_file, 'r') as f:
                                        size = int(f.read().strip())
                                else:
                                    self.logger.debug(
                                        '{} does not exist'.format(size_file))

                                self.logger.debug(to_extract_path)
                                self.logger.debug(
                                    'extracting {}...'.format(filename))
                                self._z_unpack(file_path, to_extract_path)
                                u_size = os.stat(to_extract_path).st_size
                                self.logger.debug(
                                    '{}: {} {}'.format(filename, u_size, size))
                                if u_size == size:
                                    self.run_as_user(
                                        'rm {} {}'.format(
                                            file_path, size_file))
                                else:
                                    self.logger.error(
                                        'could not validate {}'
                                        .format(to_extract_path)
                                    )
                                    return STATUS_FAILED
            self.logger.success('workshop items successfully installed')
