import inspect
import os
from typing import List, Optional, get_type_hints

import click
import yaml

from gs_manager.command.types import Server
from gs_manager.logger import get_logger
from gs_manager.null import NullServer
from gs_manager.command.validators import DirectoryConfigType, ServerType


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

    _file_path: Optional[str]

    def __init__(self, config_file: str):
        self._file_path = self._discover_config(config_file)
        if self._file_path is not None:
            self.load_config()

    @property
    def __dict__(self) -> dict:
        config_dict = {}
        for key in self._config_options:
            if not key.startswith("_"):
                value = getattr(self, key)
                if key in self._serializers:
                    value = self._serializers[key](value)
                config_dict[key] = value

        return config_dict

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

    def load_config(self) -> None:
        if not os.path.isfile(self._file_path):
            raise ValueError("Invalid config path")

        config_dict = {}
        with open(self._file_path, "r") as f:
            config_dict = yaml.safe_load(f)

        if config_dict is not None:
            config_types = get_type_hints(Config)

            for key, value in config_dict.items():
                if key not in self._config_options:
                    raise ValueError(f"Unknown config option: {key}")

                expected_type = config_types[key]
                if key in self._validators:
                    for validator in self._validators[key]:
                        value = validator.validate(value)

                if not isinstance(value, config_types[key]):
                    raise ValueError(
                        f"Invalid type for config option {key}. "
                        f"Was expecting {expected_type.__name__}, "
                        f"but got {type(value).__name__}"
                    )

                setattr(self, key, value)

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
            if hasattr(self, key):
                setattr(self, key, context.params[key])

    @property
    def _config_options(self) -> List[str]:
        attributes = inspect.getmembers(
            Config, lambda a: not (inspect.isroutine(a))
        )

        return [a[0] for a in attributes if not a[0].startswith("_")]
