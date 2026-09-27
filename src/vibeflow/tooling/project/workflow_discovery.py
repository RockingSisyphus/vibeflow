"""Find hand-authored workflow configuration documents for quality reports."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from vibeflow.tooling.project.config_loader import load_raw_config_document
from vibeflow.tooling.project.document_kinds import is_architecture_document_text


def is_workflow_config(path: Path) -> bool:
    if path.suffix.lower() not in {".json", ".jsonc"}:
        return False
    try:
        text = path.read_text(encoding="utf-8")
        if is_architecture_document_text(text):
            return False
        document = load_raw_config_document(path)
    except (OSError, ValueError):
        return False
    return isinstance(document.data.get("pipeline"), Mapping) and "type_key" not in document.data


def workflow_configs_for_root(root) -> tuple[Path, ...]:
    configs = {item.workflow_path.resolve() for item in root.architecture_documents}
    directory = root.path / "configs"
    if directory.is_dir():
        configs.update(path.resolve() for path in directory.rglob("*.jsonc") if is_workflow_config(path))
    return tuple(sorted(configs))


__all__ = ["is_workflow_config", "workflow_configs_for_root"]
