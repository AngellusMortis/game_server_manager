from dataclasses import dataclass
from typing import Dict, List, Union

import click

from gs_manager.null import NullServer

__all__ = ["ServerClass"]


@dataclass
class Server:
    name: str
    server: NullServer


class ServerClass(click.ParamType):
    name = "server_type"

    def __init__(self):
        from gs_manager.servers import get_servers

        self._choices = get_servers()

    def get_metavar(self, param) -> str:
        return f"[{'|'.join(self._choices)}]"

    def get_missing_message(self, param) -> str:
        choices = ",\n\t".join(self._choices)
        return (
            f"Choose from:\n\t{choices}.\n"
            "Or provide class path to a valid Python class path that \n"
            "inherits from gs_manager.servers.EmptyServer"
        )

    def convert(
        self, value: Union[str, Server], param: str, ctx: click.Context
    ) -> Server:
        if isinstance(value, Server):
            return value

        if value == "null":
            from gs_manager.servers.base import NullServer

            return Server("null", NullServer)

        from gs_manager.servers import get_server_class

        klass = get_server_class(value)

        if klass is None:
            self.fail(
                f"{value} is not a valid game server.\n"
                + self.get_missing_message(param)
            )

        return Server(value, klass)


class KeyValuePairs(click.ParamType):
    name = "key_value_pairs"

    def convert(
        self, values: Union[str, List[str]], param: str, ctx: click.Context
    ) -> Dict[str, str]:

        if isinstance(values, str):
            values = [values]

        return_dict = {}

        for value in values:
            valid = True

            if value.startswith("#") or value.startswith("="):
                valid = False
                continue

            parts = value.split("=")
            if len(parts) > 2:
                valid = False
                continue

            if len(parts) == 1:
                value = None
            elif len(parts) == 2:
                value = parts[1].strip()

            return_dict[parts[0]] = value

            if not valid:
                self.fail(f"{value} is not a valid key-value pair\n")

        return return_dict
