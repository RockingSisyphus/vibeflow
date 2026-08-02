"""Plain Python facts consumed by workflow quality evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from vibeflow.targets.python.project.base_lib_types import BaseLibScanReport


@dataclass(frozen=True)
class PythonNodeQualityFacts:
    """Source and base-lib facts for one registered Python node type."""

    type_key: str
    base_lib_imports: tuple[str, ...] = ()
    base_lib_report: BaseLibScanReport | None = None


__all__ = ["PythonNodeQualityFacts"]
