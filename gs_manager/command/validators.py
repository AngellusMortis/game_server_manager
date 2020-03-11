import os
from typing import Any, Dict

import click

from gs_manager.command.types import KeyValuePairs, Server, ServerClass
from gs_manager.utils import get_server_path


class GenericConfigType:
    @staticmethod
    def validate(value) -> Any:
        return value


class DirectoryConfigType(GenericConfigType):
    @staticmethod
    def validate(value) -> str:
        if not os.path.isdir(value):
            raise ValueError("Directory does not exist")

        return value


class ServerType(GenericConfigType):
    @staticmethod
    def validate(value) -> Server:
        return ServerClass()(value)


class ServerFileType(GenericConfigType):
    @staticmethod
    def validate(value) -> str:
        # do not validate file paths inside of service dir if context is
        # not active yet
        try:
            click.get_current_context()
        except RuntimeError:
            return value

        if not os.path.isfile(get_server_path(value)):
            raise ValueError("File does not exist")

        return value


class ServerDirectoryType(GenericConfigType):
    @staticmethod
    def validate(value) -> str:
        # do not validate file paths inside of service dir if context is
        # not active yet
        try:
            click.get_current_context()
        except RuntimeError:
            return value

        if not os.path.isdir(get_server_path(value)):
            raise ValueError("File does not exist")

        return value


class KeyValuePairsType(GenericConfigType):
    @staticmethod
    def validate(values) -> Dict[str, str]:
        return KeyValuePairs()(values)
