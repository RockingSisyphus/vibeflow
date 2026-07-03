from __future__ import annotations

from vibeflow import BaseLibInfo


BASE_LIB_INFO = BaseLibInfo(
    module="base_lib.sandbox_arithmetic",
    display_name="Sandbox Arithmetic",
    category="math",
    description="Simple add, subtract, multiply, and divide helpers for resource config integration tests.",
    version="0.1.0",
)


def add(left: int | float, right: int | float) -> int | float:
    return left + right


def subtract(left: int | float, right: int | float) -> int | float:
    return left - right


def multiply(left: int | float, right: int | float) -> int | float:
    return left * right


def divide(left: int | float, right: int | float) -> int | float:
    return left / right
