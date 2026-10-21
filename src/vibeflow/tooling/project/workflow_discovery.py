"""Find hand-authored workflow configuration documents for quality reports."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from vibeflow.tooling.project.config_loader import ConfigLoadError, load_raw_config_document
from vibeflow.tooling.project.document_kinds import is_architecture_document_text
from vibeflow.tooling.project.inventory import inventory_root


def is_workflow_config(path: Path) -> bool:
    if path.suffix.lower() not in {".json", ".jsonc"}:
        return False
    text = path.read_text(encoding="utf-8")
    if is_architecture_document_text(text):
        return False
    document = load_raw_config_document(path)
    return isinstance(document.data.get("pipeline"), Mapping) and "type_key" not in document.data


def workflow_configs_for_root(root) -> tuple[Path, ...]:
    workflows, issues = inventory_root(root)
    if issues:
        raise ConfigLoadError("PROJECT.INVENTORY.INCOMPLETE",
            "cannot enumerate workflows: " + "; ".join(f"{item.path}: {item.message}" for item in issues),
            "source", {"path": str(issues[0].path)})
    return tuple(item.path for item in workflows)


__all__ = ["is_workflow_config", "workflow_configs_for_root"]
