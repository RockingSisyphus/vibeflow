from __future__ import annotations

from base_lib.good_chain_b import add_two
from vibeflow import BaseLibInfo


BASE_LIB_INFO = BaseLibInfo(
    module="base_lib.good_chain_a",
    display_name="Sandbox Add Three Chain",
    category="math",
    description="Entry point for a short pure base_lib addition chain.",
    version="0.1.0",
)


def add_three(value: int | float) -> int | float:
    return add_two(value) + 1
