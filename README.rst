===================
Game Server Manager
===================


.. image:: https://img.shields.io/pypi/v/game_server_manager.svg
    :target: https://pypi.python.org/pypi/game_server_manager
    :alt: PyPi

.. image:: https://img.shields.io/pypi/pyversions/game_server_manager.svg
    :target: https://pypi.python.org/pypi/game_server_manager
    :alt: Python Versions

.. image:: https://img.shields.io/travis/AngellusMortis/game_server_manager.svg
    :target: https://travis-ci.org/AngellusMortis/game_server_manager
    :alt: Travis CI

.. image:: https://readthedocs.org/projects/game-server-manager/badge/?version=latest
    :target: https://game-server-manager.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation

.. image:: https://pyup.io/repos/github/AngellusMortis/game_server_manager/shield.svg
    :target: https://pyup.io/repos/github/AngellusMortis/game_server_manager/
    :alt: Updates

.. image:: https://coveralls.io/repos/github/AngellusMortis/game_server_manager/badge.svg?branch=master
    :target: https://coveralls.io/github/AngellusMortis/game_server_manager?branch=master
    :alt: Coverage

.. image:: https://api.codeclimate.com/v1/badges/982bb673e87f58dac7d1/maintainability
   :target: https://codeclimate.com/github/AngellusMortis/game_server_manager/maintainability
   :alt: Maintainability

.. image:: https://api.codeclimate.com/v1/badges/982bb673e87f58dac7d1/test_coverage
   :target: https://codeclimate.com/github/AngellusMortis/game_server_manager/test_coverage
   :alt: Test Coverage


Command to manage and control various types of game servers.


* Free software: MIT license
* (Coming soon!) Documentation: https://game-server-manager.readthedocs.io.


Requirements
------------

* POSIX Complient System - built and tested on Arch Linux, but should work on any Linux, MAC OSX or Windows Subsystem for Linux version
        * Uses and requires the following commands::

                grep
                java # optional for Java based servers
                ln
                nohup
                ps
                screen # optional for screen based servers
                steamcmd # optional for Steam based servers
                vim # or whatever your default $EDITOR command is
                which

* Python - built and tested with 3.6, but for full 1.0 release, unit tests will suppport 2.7 and 3.4+ unless there is a compelling reason not to

Features
--------

Allows full management of different types of servers with full configuration supported for each. Existing types (so far):

Generic configurable gameserver types
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Custom Screen (custom_screen)**: Generic gameserver that has an interactive console and can easily be ran via the screen command. Requires additional configuration to work.
* **Custom Steam (custom_steam)**: Generic gameserver that can be installed and updated from Steam. Also, optionally support Steam workshop. Requires additional configuration to work.
* **Custom RCON (custom_rcon)**: Generic Steam gameserver with `Source RCON protocol`_ support. Requires additional configuration to work.
* **Java (java)**: Generic Java base gameserver that can be ran with screen. Requires additional configuration to work.

Gameservers for specific games
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Minecraft (minecraft)**: Java based gameserver ran with screen for Minecraft.
* **ARK (ark)**: Steam based gameserver with RCON support for ARK: Surivial Evolved.

Quickstart
----------

Install from pip::

        sudo pip install game_server_manager
        gs --help

`gs` will attempt to use `.gs_config.json` as the main configuration file. If this does not exist, you must provide all configuration options via command line. `-t` will speciify type of gameserver and `-s` will save a `.gs_config.json` file based on your commandline parameters.

Generic
~~~~~~~

1. Generate default config (assuming generic type of `custom_screen`)::

        gs -t custom_screen -s status

2. Edit `.gs_config.json` with anything that is relevant to your server
3. Start server::

        gs start

4. *Optional*: Once you get everything working, make an issue and/or pull request to make a new server type so you do not have to configure in the future!

Minecraft
~~~~~~~~~

Existing Install
****************

If you already have an existing install, it is simple to set up `gs` to run with it::

    gs -t minecraft -s status

This will generate a default `.gs_config.json` file. Edit this to match your existing install.

Java
****

You much have Java installed to run Minecraft. If you need help installing Java, consult the documentation on the Minecraft wiki:

* https://minecraft.gamepedia.com/Tutorials/Setting_up_a_server#Installing_Java_2

Firewall
********

Open any firewall ports you need as detailed on Minecraft wiki:

* https://minecraft.gamepedia.com/Tutorials/Setting_up_a_server#Firewalling.2C_NATs_and_external_IP_addresses

Install/Start
*************

Assuming you want the latest stable version of Minecraft and the server to run as user `minecraft` with all of the default settings::

        gs -t minecraft -u minecraft -s install
        gs start
        gs status

See `gs -t minecraft install --help` for more details.


ARK
~~~

Existing Install
****************

If you already have an existing install, it is simple to set up `gs` to run with it::

    gs -t ark -s status

This will generate a default `.gs_config.json` file. Edit this to match your existing install.

SteamCMD
********

Install SteamCMD according to the docs for your OS:

* Valve Docs: https://developer.valvesoftware.com/wiki/SteamCMD
* Arch Linux: https://wiki.archlinux.org/index.php/Steam#SteamCMD

Open File Limit
***************

Increase Open Files Limit as detailed on ARK wiki:

* https://ark.gamepedia.com/Dedicated_Server_Setup#Open_Files_Limit

Firewall
********

Open any firewall ports you need as detailed on ARK wiki:

* https://ark.gamepedia.com/Dedicated_Server_Setup#Port_Forwarding_and_Firewall

Install/Start
*************

Assuming you want the server to run as user `ark` with all of the default settings and no mods::

        gs -t ark -u ark -s install
        gs start
        gs status

See `gs -t ark install --help` for more details.


.. _Source RCON protocol: https://developer.valvesoftware.com/wiki/Source_RCON_Protocol

Multiple Instances
******************

It is common to run multiple ARK servers together as a cluster. To do this, you want to use the `instance_overrides` config option. Example `.gs_config.json`_

.. _.gs_config.json: https://gist.github.com/AngellusMortis/9547ae3f8be88768fa362157972983a9

You can run subcommands against all instances at once with `-ci @all`. You can even run them all in parellel (get for starting and stopping) with `-p`::

    gs start -ci @all -p
    gs status -ci @all
    gs stop -ci @all -p


Planned
-------

Stuff planned before the 1.0 release:

* Full Unit Test and code coverage (Python 2.7, 3.4+ support)
* Documentation
* Forge and Curse support for Minecraft servers
* Backup command for all servers
* Staging support to update servers while still running
* Probably more stuff and maybe more server types

Credits
---------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
