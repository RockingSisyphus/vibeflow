"""Monitoring artifacts when Target discovery itself fails before runtime loading."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from vibeflow.core.run_status import run_status_record


def record_startup_failure(args, message, option_value):
    run_id = option_value(args, "--run-id") or uuid4().hex
    if (run_id in {".", ".."} or "/" in run_id or "\\" in run_id or "\x00" in run_id):
        return
    root = Path(option_value(args, "--run-root") or "runs").resolve()
    run_dir = root / run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return
    path = Path(option_value(args, "--status-file") or run_dir / "status.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = run_status_record("failed", str(message), stamp, [])
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                prefix="." + path.name + "-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(record, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    (run_dir / "business.log").write_text("", encoding="utf-8")
    (run_dir / "vibeflow.log").write_text(f"STATE failed {message}\n", encoding="utf-8")
