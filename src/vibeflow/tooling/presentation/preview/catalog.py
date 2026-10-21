"""Append-only local catalog. Data scripts work under file:// without fetch."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4


def script_call(method, value):
    return "VibeFlowPreview." + method + "(" + json.dumps(value, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c") + ");\n"


def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid4().hex)
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_catalog(root):
    index = Path(root).resolve() / "vibeflow-preview" / "index.js"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.touch(exist_ok=True)


def append_record(root: Path, metadata):
    data = script_call("record", metadata).encode("utf-8")
    index = root / "vibeflow-preview" / "index.js"
    fd = os.open(index, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
    try:
        if os.write(fd, data) != len(data):
            raise OSError("incomplete preview catalog append; use preview --reindex")
    finally:
        os.close(fd)


@dataclass
class PreviewRecord:
    root: Path
    metadata: dict

    @property
    def directory(self):
        return self.root / "vibeflow-preview" / "snapshots" / self.metadata["id"]

    def update(self, status: str, *, error: str | None = None):
        self.metadata.update(status=status, updated_at=utc_now(), revision=self.metadata.get("revision", 0) + 1)
        if error is not None:
            self.metadata["error"] = error
        atomic_write(self.directory / "record.json", json.dumps(self.metadata, ensure_ascii=False, indent=2))
        append_record(self.root, self.metadata)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_record(root, workflow, category, status):
    if category not in {"review", "build", "run"}:
        raise ValueError(f"unknown preview category: {category}")
    now = utc_now()
    identity = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ-") + uuid4().hex[:12]
    result = PreviewRecord(Path(root).resolve(), dict(version=3, id=identity, category=category, status=status,
        created_at=now, updated_at=now, workflow=workflow, views=[]))
    result.directory.mkdir(parents=True, exist_ok=False)
    return result


def reindex(root):
    root = Path(root).resolve()
    (root / "vibeflow-preview").mkdir(parents=True, exist_ok=True)
    # Reset before scanning: a producer persists record.json before opening the
    # append descriptor, so a concurrent writer is either replayed or appends to
    # this new index. Revisions prevent an older replay from reversing status.
    atomic_write(root / "vibeflow-preview" / "index.js", "")
    records, errors, obsolete = [], [], 0
    for path in sorted((root / "vibeflow-preview" / "snapshots").glob("*/record.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value,dict):
                raise ValueError("snapshot record must be an object")
            if value.get("version") != 3:
                obsolete += 1
                continue
            if not isinstance(value, dict) or not isinstance(value.get("workflow"), dict):
                raise ValueError("snapshot record must contain workflow metadata")
            if value["id"] != path.parent.name:
                raise ValueError("snapshot ID does not match its directory")
            records.append(value)
            append_record(root, value)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({"path": str(path), "error": str(exc)})
    return {"records": len(records), "obsolete": obsolete, "errors": errors, "output": str(root / "vibeflow-preview.html")}
