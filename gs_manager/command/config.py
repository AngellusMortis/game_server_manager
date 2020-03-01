from __future__ import annotations

import inspect
import os
from typing import List, Optional, get_type_hints

import click
import yaml

from gs_manager.command.types import Server
from gs_manager.command.validators import DirectoryConfigType, ServerType
from gs_manager.logger import get_logger
from gs_manager.null import NullServer

__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_SERVER_TYPE",
    "Config",
]

DEFAULT_CONFIG = ".gs_config.yml"
DEFAULT_SERVER_TYPE = Server("null", NullServer)


class Config:
    server_path: str = "."
    server_type: Server = DEFAULT_SERVER_TYPE

    _validators = {
        "server_path": [DirectoryConfigType],
        "server_type": [ServerType],
    }

    _serializers = {"server_type": lambda server_type: server_type.name}

    _exlcuded_properties: List[str] = ["global_options"]

    _file_path: Optional[str]
    _options: Optional[List[str]] = None
    _types: Optional[List[type]] = None

    def __init__(self, config_file: str, ignore_unknown: bool = False):
        self._file_path = self._discover_config(config_file)
        if self._file_path is not None:
            self.load_config(ignore_unknown)

    @property
    def __dict__(self) -> dict:
        config_dict = {}
        for key in self._config_options:
            value = getattr(self, key)
            if key in self._serializers:
                value = self._serializers[key](value)
            config_dict[key] = value

        return config_dict

    @property
    def _config_options(self) -> List[str]:
        if self._options is None:
            attributes = inspect.getmembers(
                self.__class__, lambda a: not (inspect.isroutine(a))
            )

            options = []
            for attribute in attributes:
                if not (
                    attribute[0].startswith("_")
                    or attribute[0] in self._exlcuded_properties
                ):
                    options.append(attribute[0])

            self._options = options

        return self._options

    @property
    def _config_types(self) -> List[type]:
        if self._types is None:
            self._types = get_type_hints(self.__class__)
        return self._types

    def _discover_config(self, file_path: Optional[str]) -> Optional[str]:
        if file_path is None:
            file_path = DEFAULT_CONFIG

        abs_file_path = os.path.abspath(file_path)
        if not (
            abs_file_path == file_path
            or file_path.startswith("./")
            or file_path.startswith("../")
        ):
            abs_file_path = None
            path = os.getcwd()
            search_path = path

            for x in range(5):
                if search_path == "/":
                    file_path = None
                    break
                check_file_path = os.path.join(search_path, file_path)
                if os.path.isfile(check_file_path):
                    abs_file_path = os.path.abspath(check_file_path)
                    break
                search_path = os.path.abspath(
                    os.path.join(search_path, os.pardir)
                )

        return abs_file_path

    @property
    def global_options(self):
        return {"all": []}

    def load_config(self, ignore_unknown: bool = False) -> None:
        if not os.path.isfile(self._file_path):
            raise ValueError("Invalid config path")

        config_dict = {}
        with open(self._file_path, "r") as f:
            config_dict = yaml.safe_load(f)

        if config_dict is not None:

            for key, value in config_dict.items():
                if not (ignore_unknown or key in self._config_options):
                    raise ValueError(f"Unknown config option: {key}")
                elif key not in self._config_options or value is None:
                    continue

                if key in self._validators:
                    for validator in self._validators[key]:
                        value = validator.validate(value)

                expected_type = self.get_type_for_param(key)
                if not isinstance(value, expected_type):
                    raise ValueError(
                        f"Invalid type for config option {key}. "
                        f"Was expecting {expected_type.__name__}, "
                        f"but got {type(value).__name__}"
                    )

                setattr(self, key, value)

    def get_type_for_param(self, param) -> Optional[type]:
        if param in self._config_types:
            return self._config_types[param]
        return None

    def save_config(self) -> None:
        if self._file_path is None:
            self._file_path = os.path.abspath(DEFAULT_CONFIG)

        config_dict = self.__dict__

        logger = get_logger()
        logger.debug(f"Saving config to {self._file_path}:")
        logger.debug(config_dict)

        with open(self._file_path, "w") as f:
            yaml.dump(config_dict, f)

    def update_config(self, context: click.Context) -> None:
        for key, value in context.params.items():
            if not hasattr(self, key):
                continue

            expected_type = self.get_type_for_param(key)
            if (
                expected_type == bool and context.params[key]
            ) and context.params[key] is not None:
                setattr(self, key, context.params[key])

    def make_server_config(self, context: click.Context) -> Config:
        server = context.params["server_type"].server

        server_config = self
        if server.config_class is not None:
            server_config = server.config_class(self._file_path)
            server_config.update_config(context)
        server.config = server_config

        return server_config
