import click

from gs_manager.command.config import Config
from gs_manager.null import NullServer

__all__ = ["EmptyServer", "BaseServer"]


class EmptyServer(NullServer):
    """ Empty game server with no commands"""

    name: str = "empty"
    config: Config

    def __init__(self, config: Config):
        self.config = config


class BaseServer(EmptyServer):
    """ Simple game server with common core commands"""

    name: str = "base"

    @click.command()
    @click.pass_obj
    def test(self):
        print("test")
