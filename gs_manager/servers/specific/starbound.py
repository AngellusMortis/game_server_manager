import os
import re
import time
from typing import Dict, List, Optional, Tuple, Type

import click
import click_spinner
from mcstatus import MinecraftServer as MCServer
from pygtail import Pygtail

from gs_manager.command import Config, ServerCommandClass
from gs_manager.command.types import KeyValuePairs
from gs_manager.command.validators import KeyValuePairsType
from gs_manager.decorators import multi_instance, require, single_instance
from gs_manager.servers import (
    STATUS_FAILED,
    STATUS_PARTIAL_FAIL,
    STATUS_SUCCESS,
)
from gs_manager.servers.generic.rcon import RconServer, RconServerConfig

__all__ = ["StarboundServerConfig", "StarboundServer"]


class StarboundServerConfig(RconServerConfig):
    app_id: int = 533830
    rcon_port: int = 21026
    spawn_process: bool = True
    start_command: str = "./starbound_server"
    start_directory: str = "linux"
    steam_query_port: int = 21025
    steam_requires_login: bool = True
    workshop_id: int = 211820
    server_log: str = os.path.join("storage", "starbound_server.log")


class StarboundServer(RconServer):
    name: str = "starbound"

    config_class: Optional[Type[Config]] = StarboundServerConfig
    _config: StarboundServerConfig
    _server: Optional[MCServer] = None

    @property
    def config(self) -> StarboundServerConfig:
        return super().config
