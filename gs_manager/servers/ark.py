import os

import click
from gs_manager.servers.custom_rcon import CustomRcon


class Ark(CustomRcon):
    """
    custom_steam is for Steam game servers that can be updated via Steam
    """

    _ark_config = None

    def __init__(self, *args, **kwargs):
        super(Ark, self).__init__(*args, **kwargs)

        self.options['say_command'] = 'broadcast {}'

    @staticmethod
    def defaults():
        defaults = CustomRcon.defaults()
        defaults.update({
            'steamcmd_path': 'steamcmd',
            'app_id': '376030',
            'workshop_id': '346110',
            'ark_map': 'TheIsland',
            'ark_param': '',
            'ark_option': '',
        })
        return defaults

    @staticmethod
    def excluded_from_save():
        parent = Ark.excluded_from_save()
        return parent + [
            'say_command',
        ]

    @property
    def rcon_enabled(self):
        enabled_str = self.ark_config.get('RCONEnabled')
        if enabled_str is not None:
            return enabled_str.lower() == 'true' and \
                self._get_rcon_args() is not None
        return False

    @property
    def ark_config(self):
        if self._ark_config is None:
            config = {}
            items = self.options['ark_param'] + self.options['ark_option']
            for item in items:
                parts = item.split('=')
                if len(parts) == 1:
                    config[parts[0]] = None
                else:
                    config[parts[0]] = parts[1]
            self._ark_config = config
        return self._ark_config

    @property
    def ip(self):
        return self.ark_config.get('MultiHome') or '127.0.0.1'

    @property
    def port(self):
        port = self.ark_config.get('QueryPort') or 27015
        return int(port)

    def _get_rcon_args(self):
        port = self.ark_config.get('RCONPort')
        password = self.ark_config.get('ServerAdminPassword')

        try:
            port = int(port)
        except ValueError:
            return None

        if password is None:
            return None

        args = {
            'address': (self.ip, port),
            'password': password,
            'timeout': 10,
            'multi_part': False
        }

        self.debug('rcon args: {}'.format(args))
        return args

    @click.command()
    @click.pass_obj
    def status(self):
        """ checks if gameserver is runing or not """

        self.debug_command('status')

        if self.running:
            click.secho('{} is running'
                        .format(self.options['name']),
                        fg='green')
        else:
            click.secho('{} is not running'
                        .format(self.options['name']),
                        fg='red')

    @click.command()
    @click.option('-n', '--no_verify',
                  is_flag=True)
    @click.option('-am', '--ark_map',
                  type=str)
    @click.option('-ap', '--ark_param',
                  type=str, multiple=True)
    @click.option('-ao', '--ark_option',
                  type=str, multiple=True)
    @click.pass_obj
    def start(self, no_verify, ark_map, ark_param, ark_option):
        """ starts gameserver """

        self.debug_command('start', locals())
        ark_map = ark_map or self.options['ark_map']
        ark_param = ark_param or self.options['ark_param']
        ark_option = ark_option or self.options['ark_option']

        server_command = os.path.join(
            self.options['path'], 'ShooterGame',
            'Binaries', 'Linux', 'ShooterGameServer')
        params = '?'.join(ark_param)
        params = params.replace(' ', '\\ ')
        if not params == '':
            params = '?' + params

        options = ' -'.join(ark_option)
        if not options == '':
            options = '-' + options + ' '

        command = ('{} {}?listen{} {}-server -servergamelog '
                   '-log -servergamelogincludetribelogs').format(
                        server_command, ark_map,
                        params, options)

        self.invoke(
            super(Ark, self).start, no_verify=no_verify,
            command=command)


