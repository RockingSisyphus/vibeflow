from __future__ import annotations

import argparse
from pathlib import Path


class InvalidRunIdError(ValueError):
    """Raised when a run id is not a single safe path component."""


class RunDirectoryExistsError(FileExistsError):
    """Raised when a checked run cannot atomically claim its run directory."""


def validate_run_id(run_id: object) -> str:
    value = str(run_id)
    if (
        not value
        or "\x00" in value
        or value in {".", ".."}
        or Path(value).is_absolute()
        or "/" in value
        or "\\" in value
    ):
        raise InvalidRunIdError("run id must be one non-empty path component without '.'/'..' or path separators")
    return value


def parse_run_id_argument(value: str) -> str:
    try:
        return validate_run_id(value)
    except InvalidRunIdError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def prepare_run_dir(run_root: str | Path | None, run_id: object) -> Path:
    safe_run_id = validate_run_id(run_id)
    run_dir = (Path(run_root) if run_root is not None else Path("runs")) / safe_run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise RunDirectoryExistsError(str(run_dir)) from exc
    return run_dir
