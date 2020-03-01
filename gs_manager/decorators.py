from functools import update_wrapper
import click
from gs_manager.utils import get_param_obj


def require(param):
    """
    decorator for a Click command to enforce a param from CLI or config
    """

    def _wrapper(command):
        original_command = command.callback

        def _callback(*args, **kwargs):
            context = click.get_current_context()
            config = context.obj.config

            if not hasattr(config, param) or getattr(config, param) is None:
                raise click.BadParameter(
                    f"must provide {param}",
                    context,
                    get_param_obj(context, param),
                )

            return original_command(*args, **kwargs)

        command.callback = update_wrapper(_callback, original_command)

        return command

    return _wrapper
