"""Portable run-status records for external observers."""

import json
from collections.abc import Mapping


RUN_STATES = frozenset({"starting", "running", "succeeded", "failed"})


def snapshot_info(info: object) -> list[dict[str, object]]:
    if not isinstance(info, list) or any(not isinstance(item, Mapping) for item in info):
        raise ValueError("run info must be an array of JSON objects")

    def mapping(value):
        if isinstance(value, Mapping):
            return dict(value)
        raise TypeError(f"{type(value).__name__} is not a JSON value")

    try:
        return json.loads(json.dumps(info, allow_nan=False, default=mapping))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"run info must contain JSON values: {exc}") from exc


def run_status_record(state: str, error: str | None, updated_at: str,
                      info: list[dict[str, object]] | None = None) -> dict[str, object]:
    if state not in RUN_STATES:
        raise ValueError("run state must be starting, running, succeeded or failed")
    if error is not None and not isinstance(error, str):
        raise ValueError("run error must be a string or null")
    record = {"state": state, "error": error, "updated_at": updated_at}
    if info is not None:
        record["info"] = snapshot_info(info)
    return record
