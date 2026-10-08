from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class AotPlanError(ValueError):
    """Raised when a canonical workflow cannot target JavaScript."""

    def __init__(self, message: str, *, code: str = "VF_PLAN") -> None:
        super().__init__(message)
        self.code = code


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


@dataclass
class ProjectBuildError(RuntimeError):
    code: str
    message: str
    node_path: tuple[str, ...] = ()
    diagnostics: tuple[Mapping[str, Any], ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        location = ".".join(self.node_path)
        suffix = f" ({location})" if location else ""
        return f"{self.code}: {self.message}{suffix}"


__all__ = ["AotPlanError", "AotBuildError", "ProjectBuildError"]
