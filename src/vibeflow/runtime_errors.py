from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PipelineRuntimeError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return f"Pipeline runtime error: {self.detail}"


@dataclass
class BoundaryRuntimeError(PipelineRuntimeError):
    pass
