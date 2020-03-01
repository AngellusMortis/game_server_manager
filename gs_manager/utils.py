import os
import re
from typing import List, Union

import click

__all__ = ["to_pascal_case", "to_snake_case", "get_server_path"]


def to_pascal_case(name: str) -> str:
    return to_snake_case(name).replace("_", " ").title().replace(" ", "")


def to_snake_case(name: str) -> str:
    return re.sub("([a-z])([A-Z])", r"\1_\2", name).lower()


def get_server_path(path: Union[str, List[str]]) -> str:
    context = click.get_current_context()
    return os.path.join(context.params["server_path"], path)
