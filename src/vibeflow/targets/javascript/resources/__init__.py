"""Packaged resources owned by the JavaScript Target."""

from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable


RESOURCE_NAMES = frozenset(
    {
        "runtime_helpers.mjs",
        "plugin_worker.mjs",
        "plugin_abi.d.ts",
        "toolchain_driver.mjs",
    }
)


def resource(name: str) -> Traversable:
    if name not in RESOURCE_NAMES:
        raise ValueError(f"unknown JavaScript Target resource: {name}")
    return files(__package__).joinpath(name)


def read_text(name: str) -> str:
    return resource(name).read_text(encoding="utf-8")


__all__ = ["RESOURCE_NAMES", "read_text", "resource"]
