from dataclasses import dataclass

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

    def convert(self, value, param, ctx) -> Server:
        from gs_manager.servers import get_server_class

        klass = get_server_class(value)

        if klass is None:
            self.fail(
                f"{value} is not a valid game server.\n"
                + self.get_missing_message(param)
            )

        return Server(value, klass)
