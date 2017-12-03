import click
from gs_manager.servers.base import Base
from gs_manager.utils import validate_int_list


class CustomSteam(Base):
    """
    custom_steam is for Steam game servers that can be updated via Steam
    """

    @staticmethod
    def defaults():
        defaults = Base.defaults()
        defaults.update({
            'steamcmd_path': 'steamcmd',
            'app_id': '',
            'workshop_id': '',
            'workshop_items': []
        })
        return defaults

    @click.command()
    @click.option('-sc', '--steamcmd_path',
                  type=click.Path())
    @click.option('-a', '--app_id',
                  type=int)
    @click.pass_obj
    def validate(self, steamcmd_path, app_id):
        self.debug_command('validate', locals())
        steamcmd_path = steamcmd_path or self.options['steamcmd_path']
        app_id = app_id or self.options['app_id']

        if app_id is None or app_id == '':
            raise click.BadParameter('must provide app_id of game')

        self.run_as_user(
            '{} +login anonymous +force_install_dir {} +app_update {} validate +quit'
            .format(steamcmd_path, self.options['path'], app_id),
            redirect_output=False)

    @click.command()
    @click.option('-sc', '--steamcmd_path',
                  type=click.Path())
    @click.option('-w', '--workshop_id',
                  type=int)
    @click.option('-wi', '--workshop_items',
                  callback=validate_int_list)
    @click.pass_obj
    def workshop_download(self, steamcmd_path, workshop_id, workshop_items):
        self.debug_command('workshop_download', locals())
        steamcmd_path = steamcmd_path or self.options['steamcmd_path']
        workshop_id = workshop_id or self.options['workshop_id']
        workshop_items = workshop_items or self.options['workshop_items']

        if workshop_id is None or workshop_id == '':
            raise click.BadParameter('must provide workshop_id of game')

        self.invoke(
            self.validate, steamcmd_path=steamcmd_path, app_id=workshop_id
        )

        for workshop_item in workshop_items:
            self.run_as_user(
                '{} +login anonymous +force_install_dir {} '
                '+workshop_download_item {} {} +quit'
                .format(steamcmd_path, self.options['path'],
                        workshop_id, workshop_item),
                redirect_output=False)
