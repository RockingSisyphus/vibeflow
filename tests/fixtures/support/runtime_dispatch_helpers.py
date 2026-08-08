"""Local helper fixtures for runtime-dispatch provenance tests."""


def invoke(value):
    return value()


def identity(value):
    return value


def accept_without_invoking(value):
    return value is not None
