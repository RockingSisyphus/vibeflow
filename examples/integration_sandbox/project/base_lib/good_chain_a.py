from __future__ import annotations

from base_lib.good_chain_b import add_two


def add_three(value: int | float) -> int | float:
    return add_two(value) + 1
