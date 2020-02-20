import json
import re

import click

try:
    from json import JSONDecodeError as JSONError
except ImportError:
    JSONError = ValueError


def validate_int_list(context, param, value):
    if value is not None:
        try:
            values = value.split(",")
            for index in range(len(values)):
                values[index] = int(values[index])
            return values
        except ValueError:
            raise click.BadParameter("value need to be a comma seperated list of int")


def validate_instance_overrides(context, param, values):
    overrides = {}
    for value in values:
        parts = list(value.partition(":"))
        if len(parts) == 3:
            try:
                parts[2] = json.loads(parts[2])
            except JSONError:
                raise click.BadParameter("invalid override JSON", context, param)
            else:
                overrides[parts[0]] = parts[2]
        else:
            raise click.BadParameter("invalid override format", context, param)
    if len(overrides.keys()) == 0:
        overrides = None
    return overrides


def validate_key_value(context, param, values):
    return_dict = {}
    valid = True
    for value in values:
        if value.startswith("#") or value.startswith("="):
            valid = False
            continue

        parts = value.split("=")
        if len(parts) > 2:
            valid = False
            continue

        if len(parts) == 1:
            value = None
        elif len(parts) == 2:
            value = parts[1].strip()
        return_dict[parts[0]] = value

    if not valid and context is not None and param is not None:
        raise click.BadParameter(
            "invalid server key-value pair", context, param,
        )
    return return_dict


def validate_string_value(context, param, value):
    if len(value) > 0:
        match = re.match("^[^|]+$", value, re.I)
        if not match or not match.group() == value:
            raise click.BadParameter(
                "cannot contain a | character", context, param,
            )
