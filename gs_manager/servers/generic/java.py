import click
from gs_manager.decorators import multi_instance

from .screen import Screen


class Java(Screen):
    """
    Generic Java base gameserver that can be ran with Screen.
    Requires additional configuration to work.
    """

    command_format = "{} {} -jar {} {}"

    @staticmethod
    def defaults():
        defaults = Screen.defaults()
        defaults.update(
            {
                "extra_args": "",
                "java_args": "",
                "java_path": "java",
                "server_jar": None,
            }
        )
        return defaults

    @staticmethod
    def excluded_from_save():
        parent = Screen.excluded_from_save()
        return parent + [
            "command",
        ]

    @multi_instance
    @click.command()
    @click.option("-n", "--no_verify", is_flag=True)
    @click.option(
        "-hc",
        "--history",
        type=int,
        help="Number of lines to show in screen for history",
    )
    @click.option(
        "-ds",
        "--delay_start",
        type=int,
        help=("Time (in seconds) to wait after service has started " "to verify"),
    )
    @click.option(
        "-mt",
        "--max_start",
        type=int,
        help="Max time (in seconds) to wait before assuming the "
        "server is deadlocked",
    )
    @click.option("-ja", "--java_args", type=str, help=("Extra args to pass to Java"))
    @click.option(
        "-sj", "--server_jar", type=click.Path(), help="Path to Minecraft server jar"
    )
    @click.option(
        "-jp", "--java_path", type=click.Path(), help="Path to Java executable"
    )
    @click.option("-ea", "--extra_args", type=str, help=("To add to jar command"))
    @click.option(
        "-fg",
        "--foreground",
        is_flag=True,
        help="Start gameserver in foreground. Ignores "
        "spawn_progress, screen, and any other "
        "options or classes that cause server to run "
        "in background.",
    )
    @click.pass_obj
    def start(self, no_verify, *args, **kwargs):
        """ starts java gameserver """

        self._require_param(self.config, "server_jar")
        self._require_file(self.config["server_jar"], "server_jar")
        self._require_command(self.config["java_path"], "java_path")

        command = self.command_format.format(
            self.config["java_path"],
            self.config["java_args"],
            self.config["server_jar"],
            self.config["extra_args"],
        )
        return self.invoke(
            super(Java, self).start, command=command, no_verify=no_verify,
        )
