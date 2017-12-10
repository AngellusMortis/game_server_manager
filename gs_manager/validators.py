import json

import click

try:
    from json import JSONDecodeError as JSONError
except ImportError:
    JSONError = ValueError


def validate_int_list(context, param, value):
    if value is not None:
        try:
            values = value.split(',')
            for index in range(len(values)):
                values[index] = int(values[index])
            return values
        except ValueError:
            raise click.BadParameter(
                'value need to be a comma seperated list of int')


def validate_instance_overrides(context, param, values):
    overrides = {}
    for value in values:
        parts = list(value.partition(':'))
        if len(parts) == 3:
            try:
                parts[2] = json.loads(parts[2])
            except JSONError:
                raise click.BadParameter(
                    'invalid override JSON', context, param)
            else:
                overrides[parts[0]] = parts[2]
        else:
            raise click.BadParameter('invalid override format', context, param)
    if len(overrides.keys()) == 0:
        overrides = None
    return overrides


def validate_key_value(context, param, values):
    return_dict = {}
    for value in values:
        parts = value.split('=')
        if len(parts) <= 2 and not parts[0] == '':
            value = None
            if len(parts) == 2:
                value = parts[1]
            return_dict[parts[0]] = value
        else:
            raise click.BadParameter(
                'invalid server key-value pair', context, param)
    return return_dict
