from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass
class WorkspaceConfigError(ValueError):
    rule_id: str
    message: str
    source_location: Mapping[str, object]
    failure_layer: str = "workspace"

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ArchitectureDocumentSpec:
    workflow: str
    document: str
    workflow_path: Path
    document_path: Path
    registration_field: str
