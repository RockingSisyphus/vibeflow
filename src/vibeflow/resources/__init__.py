from __future__ import annotations

from importlib import resources


def schema_text(name: str) -> str:
    if not name.endswith(".schema.json"):
        name = f"{name}.schema.json"
    return (resources.files(__package__) / "schema" / name).read_text(encoding="utf-8")


__all__ = ["schema_text"]
