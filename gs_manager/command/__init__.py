from typing import Optional, Iterable

import click

from gs_manager.command.config import (
    Config,
    DEFAULT_CONFIG,
    DEFAULT_SERVER_TYPE,
)
from gs_manager.servers import EmptyServer

__all__ = [
    "ConfigCommandClass",
    "Config",
    "DEFAULT_CONFIG",
    "DEFAULT_SERVER_TYPE",
]


class ConfigCommandClass(click.Group):
    def make_context(
        self, info_name, args, parent=None, **extra
    ) -> click.Context:
        config = Config(self._get_config_file(args))
        extra["obj"] = config
        extra["default_map"] = config.__dict__

        context = super().make_context(info_name, args, parent, **extra)

        config = context.obj
        config.update_config(context)
        if issubclass(config.server_type.server, EmptyServer):
            context.obj = config.server_type.server(config)
        return context

    def parse_args(self, context: click.Context, args) -> Iterable:
        parser = self.make_parser(context)
        options, _, _ = parser.parse_args(args=args.copy())

        return super().parse_args(context, args)

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
