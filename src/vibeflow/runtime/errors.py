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


class DelegateCliExit(BaseException):
    """Internal control flow for an authorized business CLI exit."""

    def __init__(self, exit_code: int, *, source: str) -> None:
        super().__init__(exit_code)
        self.exit_code = exit_code
        self.source = source


def normalize_delegate_cli_system_exit(exc: SystemExit, *, source: str) -> DelegateCliExit:
    value = exc.code
    if value is None:
        return DelegateCliExit(0, source=source)
    if type(value) is not int or not 0 <= value <= 255:
        raise PipelineRuntimeError(f"delegate CLI SystemExit from '{source}' must use an integer code from 0 to 255")
    return DelegateCliExit(value, source=source)
