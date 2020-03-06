from typing import List, Optional
import inspect
import sys
import importlib

from gs_manager.servers.base import EmptyServer, BaseServer


__all__ = ["get_servers", "EmptyServer", "BaseServer"]


def get_servers() -> List[str]:
    server_classes = inspect.getmembers(
        sys.modules[__name__], predicate=inspect.isclass
    )
    types = []
    for server_name, server_klass in server_classes:
        if issubclass(server_klass, EmptyServer):
            types.append(server_klass.name)

    return types


def get_server_class(klass_name: str) -> Optional[EmptyServer]:
    module_path = "gs_manager.servers"

    if "." not in klass_name:
        server_classes = inspect.getmembers(
            sys.modules[__name__], predicate=inspect.isclass
        )
        for server_name, server_klass in server_classes:
            if (
                issubclass(server_klass, EmptyServer)
                and server_klass.name == klass_name
            ):
                return server_klass

    try:
        module_path, klass_name = klass_name.rsplit(".", 1)
        module = importlib.import_module(module_path)
        klass = getattr(module, klass_name)
    except (ValueError, ModuleNotFoundError, AttributeError):
        return None

    if not (inspect.isclass(klass) and issubclass(klass, EmptyServer)):
        return None

    return klass
