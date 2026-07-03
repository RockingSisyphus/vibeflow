from __future__ import annotations

from vibeflow import BaseLibInfo


BASE_LIB_INFO = BaseLibInfo(
    module="base_lib.good_math",
    display_name="Sandbox Good Math",
    category="math",
    description="Pure arithmetic helpers used by sandbox math nodes.",
    version="0.1.0",
)


def add(left: int | float, right: int | float) -> int | float:
    return left + right


def multiply(left: int | float, right: int | float) -> int | float:
    return left * right


def clamp(value: int | float, low: int | float, high: int | float) -> int | float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def is_done(value: int | float, target: int | float) -> bool:
    return value >= target
