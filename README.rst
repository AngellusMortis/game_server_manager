===================
Game Server Manager
===================


.. image:: https://img.shields.io/pypi/v/game_server_manager.svg
        :target: https://pypi.python.org/pypi/game_server_manager

.. image:: https://img.shields.io/travis/AngellusMortis/game_server_manager.svg
        :target: https://travis-ci.org/AngellusMortis/game_server_manager

.. image:: https://readthedocs.org/projects/game-server-manager/badge/?version=latest
        :target: https://game-server-manager.readthedocs.io/en/latest/?badge=latest
        :alt: Documentation Status

.. image:: https://pyup.io/repos/github/AngellusMortis/game_server_manager/shield.svg
     :target: https://pyup.io/repos/github/AngellusMortis/game_server_manager/
     :alt: Updates


Simple command to manage and control various types of game servers.


* Free software: MIT license
* (Coming soon!) Documentation: https://game-server-manager.readthedocs.io.


Requirements
------------

* POSIX Complient System - built and tested on Arch Linux, but should work on any Linux, MAC OSX or Windows Subsystem for Linux version
        * Uses and requires `sudo`, `rm`, `mkdir`, `ps`, `ln`, `ls`, `chown`, `vim`, and optionally `screen` (for screen based servers), `java` (for Java based servers) and `steamcmd` (for Steam based servers)
* Python - built and tested with 3.6, but for full 1.0 release, unit tests will suppport 2.7 and 3.4+

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

Full 1.0 release will be in PyPi, but until then, it will likely only exist in github::

        sudo pip install -e -e git+ssh://git@github.com/AngellusMortis/game_server_manager.git@master@egg=game_server_manager
        gs --help

`gs` will attempt to use `.gs_config.json` as the main configuration file. If this does not exist, you must provide all configuration options via command line. `-t` will speciify type of gameserver and `-s` will save a `.gs_config.json` file based on your commandline parameters.

Minecraft
~~~~~~~~~

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

        gs -t ark -u ark -s validate
        gs start
        gs status

See `gs -t ark install --help` for more details.


.. _Source RCON protocol: https://developer.valvesoftware.com/wiki/Source_RCON_Protocol

Credits
---------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage

