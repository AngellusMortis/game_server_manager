# -*- coding: utf-8 -*-

"""Top-level package for Game Server Manager."""

__author__ = """Christopher Bailey"""
__email__ = "cbailey@mort.is"
__version__ = "0.1.0"

from ._version import get_versions

__version__ = get_versions()["version"]
del get_versions
