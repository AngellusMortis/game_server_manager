import logging
import pprint
import re
import time
from subprocess import CalledProcessError

import click
from gs_manager.utils import run_as_user


class Base(object):

    @staticmethod
    def defaults():
        return {
            'config': '.gs_config.json',
            'type': 'custom',
            'name': 'gameserver',
            'user': 'root',
        }

    @staticmethod
    def excluded_from_save():
        return [
            'config',
            'path',
            'save',
            'debug'
        ]

    logger = None

    def __init__(self, context, options=None):
        if options is None:
            options = {}

        self.context = context
        self.logger = logging.getLogger(__name__)

        self.options = options

    def invoke(self, method, *args, **kwargs):
        self.context.invoke(method, *args, **kwargs)

    def run_as_user(self, command):
        """ runs command as configurated user """

        self.debug('running command \'{}\''.format(command))
        output = run_as_user(self.options['user'], command)
        self.debug(output)

        return output

    def is_running(self):
        """ checks if gameserver is running """

        # grab screen name from gameserver name
        try:
            screen = self.run_as_user('screen -ls | grep {}'
                                      .format(self.options['name'])).strip()
        except CalledProcessError as ex:
            if ex.output == '':
                is_running = False
            else:
                raise click.ClickException(
                    'something went wrong checking server status')
        else:
            # check the screen exists
            is_running = (screen != '' and screen is not None)

        self.debug('is_running: {}'.format(is_running))

        # check the original command is actually running in screen
        if is_running:
            pid = re.match('\d+', screen).group()
            processes = self.run_as_user(
                'ps -el | grep {} | awk \'{{print $4}}\''.format(pid))
            processes = processes.split('\n')
            return len(processes) == 2 and processes[0] == pid
        return False

    def debug(self, message):
        """ prints message out to console if debug is on """

        if isinstance(message, (list, dict)):
            message = pprint.pformat(message)
        message = str(message)

        self.logger.debug(message)
        if self.options['debug']:
            click.secho(message, fg='cyan')

    def kill_server(self):
        """ forcibly kills server process """
        # grab screen name from gameserver name
        screen = self.run_as_user('screen -ls | grep {}'
                                  .format(self.options['name'])).strip()

        if screen != '':
            pid = re.match('\d+', screen).group()
            self.run_as_user('kill -9 {}'.format(pid))

    def _wait(self, seconds):
        return [x for x in range(seconds)]

    def _progressbar(self, seconds):
        wait_items = self._wait(seconds)
        with click.progressbar(wait_items) as waiter:
            for item in waiter:
                time.sleep(1)
