import logging
import os
import pprint

import click
from gs_manager.utils import get_server_path

__all__ = ["get_logger", "ClickLogger"]


def get_logger() -> logging.getLoggerClass():
    logging.setLoggerClass(ClickLogger)
    logger = logging.getLogger("gs_manager")

    if not logger.hasHandlers():
        logger.setLevel(logging.DEBUG)
        log_dir = get_server_path("logs")
        if not os.path.isdir(log_dir):
            os.mkdir(log_dir)

        log_path = os.path.join(log_dir, "gs_manager.log")
        log_file = None

        try:
            log_file = open(log_path, "a")
        except PermissionError:
            log_file = open(os.devnull, "w")

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler = logging.StreamHandler(log_file)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
        logger.click_debug = click.get_current_context().params["debug"]
    return logger


class ClickLogger(logging.getLoggerClass()):
    """ Wrapper around default logging class that also calls click.echo """

    click_debug = False

    def _secho(self, message, **kwargs) -> None:
        if isinstance(message, (list, dict)):
            message = pprint.pformat(message)
        if not isinstance(message, str):
            message = str(message)
        click.secho(message, **kwargs)

    def info(self, message, nl=True, *args, **kwargs) -> None:
        super(ClickLogger, self).info(message, *args, **kwargs)

        self._secho(message, nl=nl)

    def debug(self, message, nl=True, *args, **kwargs) -> None:
        super(ClickLogger, self).debug(message, *args, **kwargs)

        if self.click_debug:
            self._secho(message, fg="cyan", nl=nl)

    def warning(self, message, nl=True, *args, **kwargs) -> None:
        super(ClickLogger, self).warning(message, *args, **kwargs)

        self._secho(message, fg="yellow", nl=nl)

    def error(self, message, nl=True, *args, **kwargs) -> None:
        super(ClickLogger, self).error(message, *args, **kwargs)

        self._secho(message, fg="red", nl=nl)

    def success(self, message, nl=True, *args, **kwargs) -> None:
        super(ClickLogger, self).info(message, *args, **kwargs)

        self._secho(message, fg="green", nl=nl)
