from __future__ import annotations

from typing import Mapping


def summarize_mapping(values: Mapping[str, object]) -> dict[str, object]:
    return {str(key): summarize_value(value) for key, value in values.items()}


def summarize_value(value: object) -> dict[str, object]:
    summary: dict[str, object] = {"type": type(value).__name__}
    if isinstance(value, Mapping):
        summary["keys"] = sorted(str(key) for key in value.keys())
        summary["size"] = len(value)
        return summary
    if isinstance(value, (list, tuple, set)):
        summary["size"] = len(value)
        return summary
    if isinstance(value, (str, bytes)):
        summary["size"] = len(value)
        return summary
    if value is None or isinstance(value, (int, float, bool)):
        summary["scalar"] = True
        return summary
    summary["repr_type"] = type(value).__qualname__
    return summary
