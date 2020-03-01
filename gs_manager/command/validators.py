import os
from typing import Any

from gs_manager.command.types import ServerClass, Server


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
