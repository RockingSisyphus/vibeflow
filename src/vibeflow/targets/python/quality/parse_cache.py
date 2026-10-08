"""Command-local syntax reuse, independent of ownership and review policy."""

import ast


def parse_python_source(path, text, cache=None):
    key = str(path), text
    if cache is not None and key in cache:
        value = cache[key]
        if isinstance(value, tuple):
            raise SyntaxError(*value)
        return value
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as error:
        if cache is not None:
            cache[key] = error.args
        raise
    if cache is not None:
        cache[key] = tree
    return tree
