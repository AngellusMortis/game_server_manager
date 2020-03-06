from __future__ import annotations

import inspect
import os
from typing import Callable, Dict, List, Optional, Union, get_type_hints

import click
import yaml

from gs_manager.command.types import Server
from gs_manager.command.validators import (
    DirectoryConfigType,
    GenericConfigType,
    ServerType,
)
from gs_manager.logger import get_logger
from gs_manager.null import NullServer

__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_SERVER_TYPE",
    "BaseConfig",
    "Config",
]

DEFAULT_CONFIG = ".gs_config.yml"
DEFAULT_SERVER_TYPE = Server("null", NullServer)


class BaseConfig:
    _validators: Dict[str, List[GenericConfigType]] = {}

    _serializers: Dict[str, Callable] = {}

    _excluded_properties: List[str] = ["global_options", "parent"]

    _options: Optional[List[str]] = None
    _types: Optional[List[type]] = None

    parent: Optional[BaseConfig] = None

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
                    or attribute[0] in self._excluded_properties
                ):
                    options.append(attribute[0])

            self._options = options

        return self._options

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
    def _config_types(self) -> List[type]:
        if self._types is None:
            self._types = get_type_hints(self.__class__)
        return self._types

    @property
    def global_options(self):
        return {"all": [], "instance_enabled": []}

    def get_type_for_param(self, param) -> Optional[type]:
        if param in self._config_types:
            return self._config_types[param]
        return None

    def _update_config_from_dict(
        self, config_dict: dict, ignore_unknown=False, ignore_bool=False
    ) -> None:

        for key, value in config_dict.items():
            if not (ignore_unknown or key in self._config_options):
                raise ValueError(f"Unknown config option: {key}")
            elif key not in self._config_options or value is None:
                continue

            if key in self._validators:
                for validator in self._validators[key]:
                    value = validator.validate(value)

            expected_type = self.get_type_for_param(key)
            if not ignore_bool or (expected_type != bool or value):
                setattr(self, key, value)

    def _update_config_from_context(self, context: click.Context) -> None:
        self._update_config_from_dict(
            context.params, ignore_unknown=True, ignore_bool=True
        )

    def update_config(self, data: Union[dict, click.Context]) -> None:
        if isinstance(data, click.Context):
            self._update_config_from_context(data)
        else:
            self._update_config_from_dict(data)

    def make_server_config(self, context: click.Context) -> Config:
        server = context.params["server_type"].server

        server_config = self
        if server.config_class is not None:
            server_config = server.config_class(self._file_path)
            server_config.update_config(context)
        server._config = server_config

        return server_config


class Config(BaseConfig):
    instance_name: Optional[str] = None

    server_path: str = "."
    server_type: Server = DEFAULT_SERVER_TYPE

    _validators = {
        "server_path": [DirectoryConfigType],
        "server_type": [ServerType],
    }

    _serializers = {"server_type": lambda server_type: server_type.name}

    _file_path: Optional[str]

    _instances: Dict[str, BaseConfig] = {}

    _excluded_properties: List[str] = BaseConfig._excluded_properties + [
        "instances",
        "all_instance_names",
        "instance_name",
        "current_instance",
    ]

    def __init__(
        self,
        config_file: Optional[str] = None,
        ignore_unknown: bool = False,
        load_config: bool = True,
    ):
        if load_config:
            self._file_path = self._discover_config(config_file)
            if self._file_path is not None:
                self.load_config(ignore_unknown)

    @property
    def __dict__(self) -> dict:
        config_dict = super().__dict__

        if len(self._instances.keys()) > 0:
            config_dict["instance_overrides"] = {}
            for name, instance_config in self._instances.items():
                config_dict["instance_overrides"][name] = {}
                instance_dict = instance_config.__dict__
                for key, value in instance_dict.items():
                    if config_dict.get(key) != value:
                        config_dict["instance_overrides"][name][key] = value

        return config_dict

    @property
    def all_instance_names(self) -> str:
        return self._instances.keys()

    @property
    def instances(self) -> Dict[str, BaseConfig]:
        return self._instances

    @property
    def current_instance(self) -> BaseConfig:
        if self.instance_name is None:
            return self
        return self.get_instance(self.instance_name)

    def get_instance(self, name="default") -> BaseConfig:
        config = self
        context = click.get_current_context()

        if name != "default":
            if name not in self._instances:
                raise click.ClickException(f"instance {name} does not exist")
            config = self._instances[name]
        config.update_config(context)

        return config

    def copy(self) -> Config:
        copy = self.__class__(load_config=False)

        copy._file_path = self._file_path
        copy._update_config_from_dict(self.__dict__, ignore_unknown=True)

        return copy

    def _update_config_from_dict(
        self, config_dict: dict, ignore_unknown=False, ignore_bool=False
    ) -> None:

        super()._update_config_from_dict(
            config_dict, ignore_unknown, ignore_bool
        )

        for instance in self._instances.values():
            instance._update_config_from_dict(
                config_dict, ignore_unknown, ignore_bool
            )

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

    def _make_instance_config_factory(self) -> BaseConfig:
        class InstanceConfig(BaseConfig):
            _validators: Dict[str, List[GenericConfigType]] = self._validators
            _serializers: Dict[str, Callable] = self._serializers
            _excluded_properties: List[str] = self._excluded_properties

        for option in self._config_options:
            setattr(InstanceConfig, option, None)

        return InstanceConfig()

    def _make_instance_config(self, instance_dict: dict):
        instance_config = self._make_instance_config_factory()
        instance_config.parent = self
        instance_config._validators = self._validators
        instance_config._serializers = self._serializers
        instance_config._excluded_properties = self._excluded_properties

        for option in self._config_options:
            setattr(instance_config, option, getattr(self, option))

        instance_config._update_config_from_dict(
            instance_dict, ignore_unknown=True
        )

        return instance_config

    def load_config(self, ignore_unknown: bool = False) -> None:
        if not os.path.isfile(self._file_path):
            raise ValueError("Invalid config path")

        config_dict = {}
        with open(self._file_path, "r") as f:
            config_dict = yaml.safe_load(f)

        if config_dict is not None:
            instance_configs = []
            # reset all of the instance configs
            self._instances = {}

            if "instance_overrides" in config_dict:
                instance_configs = config_dict.pop("instance_overrides")

            self._update_config_from_dict(
                config_dict, ignore_unknown=ignore_unknown
            )

            for instance_name, instance_dict in instance_configs.items():
                self._instances[instance_name] = self._make_instance_config(
                    instance_dict
                )

    def save_config(self) -> None:
        if self._file_path is None:
            self._file_path = os.path.abspath(DEFAULT_CONFIG)

        config_dict = self.__dict__

        logger = get_logger()
        logger.debug(f"Saving config to {self._file_path}:")
        logger.debug(config_dict)

        with open(self._file_path, "w") as f:
            yaml.dump(config_dict, f)
