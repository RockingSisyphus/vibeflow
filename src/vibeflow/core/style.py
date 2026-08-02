"""Language-neutral visual metadata contract used by workflow validation.

This module owns only the data-level style vocabulary.  Renderers may add
format-specific presentation rules, but parsing a workflow must not import a
renderer.
"""

from __future__ import annotations

import re


NODE_STYLE_FIELDS = ("fill", "stroke", "text")

# These colours are reserved by the public VibeFlow visual contract.  Keeping
# the values in Core lets an in-memory workflow be validated without loading a
# renderer or touching the filesystem.
RESERVED_SYSTEM_COLORS = frozenset(
    {
        "#ececff",
        "#9370db",
        "#333333",
        "#fee2e2",
        "#dc2626",
        "#7f1d1d",
        "#fef3c7",
        "#d97706",
        "#78350f",
        "#e0f2fe",
        "#0284c7",
        "#0c4a6e",
        "#f0fdf4",
        "#16a34a",
        "#14532d",
        "#ede9fe",
        "#7c3aed",
        "#3b0764",
        "#f0fdfa",
        "#0f766e",
        "#134e4a",
        "#fef08a",
        "#ca8a04",
        "#713f12",
        "#ecfdf5",
        "#059669",
        "#064e3b",
        "#eff6ff",
        "#2563eb",
        "#1e3a8a",
        "#f5f3ff",
    }
)

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def is_hex_color(value: object) -> bool:
    return isinstance(value, str) and bool(_HEX_COLOR_RE.fullmatch(value))


def normalize_hex_color(value: str) -> str:
    return value.lower()


def is_reserved_system_color(value: str) -> bool:
    return normalize_hex_color(value) in RESERVED_SYSTEM_COLORS


__all__ = [
    "NODE_STYLE_FIELDS",
    "RESERVED_SYSTEM_COLORS",
    "is_hex_color",
    "is_reserved_system_color",
    "normalize_hex_color",
]
