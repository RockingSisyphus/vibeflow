from __future__ import annotations

from vibeflow import BaseLibInfo

BASE_LIB_INFO = BaseLibInfo(
    module="base_lib.math_tools",
    display_name="Math Tools",
    category="math",
    description="Pure arithmetic helpers for the minimal project.",
    version="0.1.0",
)


def add(left: int | float, right: int | float) -> int | float:
    return left + right
