import json
import os
from typing import List, Optional, Type

import click

from gs_manager.command import Config
from gs_manager.servers.generic.rcon import RconServer, RconServerConfig
from gs_manager.utils import get_server_path

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
    backup_directory: str = "storage"

    _excluded_properties: List[str] = RconServerConfig._excluded_properties + [
        "starbound"
    ]

    _starbound_config: Optional[dict] = None

    def _set_config(self, config_name, config_value) -> bool:
        if (
            config_value is not None
            and self._starbound_config[config_name] != config_value
        ):
            self._starbound_config[config_name] = config_value
            return True
        return False

    def _update_config(self):
        updated = False

        updated = updated or self._set_config(
            "gameServerBind", self.steam_query_ip
        )
        updated = updated or self._set_config(
            "gameServerPort", self.steam_query_port
        )
        updated = updated or self._set_config(
            "queryServerBind", self.steam_query_ip
        )
        updated = updated or self._set_config(
            "queryServerPort", self.steam_query_port
        )
        updated = updated or self._set_config("rconServerBind", self.rcon_ip)
        updated = updated or self._set_config(
            "rconServerPassword", self.rcon_password
        )
        updated = updated or self._set_config("rconServerPort", self.rcon_port)
        updated = updated or self._set_config(
            "runQueryServer",
            self.steam_query_port is not None
            and self.steam_query_port is not None,
        )
        updated = updated or self._set_config(
            "runRconServer",
            self.rcon_password is not None
            and self.rcon_port is not None
            and self.rcon_ip is not None,
        )

        if updated:
            self.save_starbound()

    @property
    def starbound(self) -> dict:
        if self._starbound_config is None:
            self._starbound_config = {}

            config_path = get_server_path(
                ["storage", "starbound_server.config"]
            )
            if not os.path.isfile(config_path):
                self.logger.warn(
                    "could not find starbound_server.config for "
                    "Starbound server"
                )
                return {}

            with open(config_path) as config_file:
                self._starbound_config = json.load(config_file)

            self._update_config()

        return self._starbound_config

    def save_starbound(self) -> None:
        config_path = get_server_path(["storage", "starbound_server.config"])

        with open(config_path, "w") as config_file:
            json.dump(self.starbound, config_file, indent=4, sort_keys=True)

        self._starbound_config = None
        self.starbound


class StarboundServer(RconServer):
    name: str = "starbound"

    config_class: Optional[Type[Config]] = StarboundServerConfig
    _config: StarboundServerConfig

    @property
    def config(self) -> StarboundServerConfig:
        return super().config

    def is_rcon_enabled(self) -> bool:
        return (
            super().is_rcon_enabled()
            and self.config.starbound["runRconServer"]
        )

    def is_query_enabled(self) -> bool:
        return (
            super().is_query_enabled()
            and self.config.starbound["runQueryServer"]
        )
