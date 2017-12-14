import logging
import pprint

import click


class ClickLogger(logging.getLoggerClass()):
    """ Wrapper around default logging class that also calls click.echo """
    click_debug = False

    def _secho(message, **kwargs):
        if isinstance(message, (list, dict)):
            message = pprint.pformat(message)
        if not isinstance(message, str):
            message = str(message)
        click.secho(message, **kwargs)

    def info(self, message, nl=True, *args, **kwargs):
        super(ClickLogger, self).info(message, *args, **kwargs)

        self._secho(message, nl=nl)

    def debug(self, message, nl=True, *args, **kwargs):
        super(ClickLogger, self).debug(message, *args, **kwargs)

        if self.click_debug:
            self._secho(message, fg='cyan', nl=nl)

    def warning(self, message, nl=True, *args, **kwargs):
        super(ClickLogger, self).warning(message, *args, **kwargs)

        self._secho(message, fg='yellow', nl=nl)

    def error(self, message, nl=True, *args, **kwargs):
        super(ClickLogger, self).error(message, *args, **kwargs)

        self._secho(message, fg='red', nl=nl)

    def success(self, message, nl=True, *args, **kwargs):
        super(ClickLogger, self).info(message, *args, **kwargs)

        self._secho(message, fg='green', nl=nl)
