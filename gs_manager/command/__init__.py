from typing import Optional

import click

from gs_manager.command.config import (
    DEFAULT_CONFIG,
    DEFAULT_SERVER_TYPE,
    Config,
)

__all__ = [
    "ConfigCommandClass",
    "ServerCommandClass",
    "Config",
    "DEFAULT_CONFIG",
    "DEFAULT_SERVER_TYPE",
]


class ConfigCommandClass(click.Group):
    def make_context(
        self, info_name, args, parent=None, **extra
    ) -> click.Context:
        from gs_manager.servers import EmptyServer

        config = Config(self._get_config_file(args), ignore_unknown=True)
        extra["obj"] = config
        extra["default_map"] = config.__dict__

        context = super().make_context(info_name, args, parent, **extra)

        config = context.obj
        config = config.make_server_config(context)
        if issubclass(config.server_type.server, EmptyServer):
            context.obj = config.server_type.server(config)
        return context

    def _get_config_file(self, args: list) -> Optional[str]:
        config_file = None
        index = -1

        try:
            index = args.index("-c")
        except ValueError:
            try:
                index = args.index("--config-file")
            except ValueError:
                pass

        index += 1
        if index != 0 and len(args) > index:
            config_file = args[index]

        return config_file


class ServerCommandClass(click.Command):
    def make_context(
        self, info_name, args, parent=None, **extra
    ) -> click.Context:
        context = super().make_context(info_name, args, parent, **extra)

        config: Config = context.parent.obj.config
        config.update_config(context)

        return context
