"""Computation helper, separate from the runtime plugin declaration/module."""

SHIFT_BY = 0


def plugin_shift(value: int | float) -> int | float:
    return value + SHIFT_BY
