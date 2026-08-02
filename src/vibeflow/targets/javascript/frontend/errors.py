from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class AotBuildError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostics: tuple[Mapping[str, Any], ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class ProjectBuildError(RuntimeError):
    code: str
    message: str
    node_path: tuple[str, ...] = ()
    diagnostics: tuple[Mapping[str, Any], ...] = ()

    def __str__(self) -> str:
        location = ".".join(self.node_path)
        suffix = f" ({location})" if location else ""
        return f"{self.code}: {self.message}{suffix}"


__all__ = ["AotBuildError", "ProjectBuildError"]
