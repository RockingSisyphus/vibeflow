"""Locate the checked run's centralized display artifacts without scanning history."""
import json
from pathlib import Path


def preview_directory(run_dir):
    run_dir = Path(run_dir)
    pointer = json.loads((run_dir / "preview.json").read_text(encoding="utf-8"))
    directory = (run_dir / pointer["directory"]).resolve()
    metadata = json.loads((directory / "record.json").read_text(encoding="utf-8"))
    assert metadata["id"] == pointer["id"]
    assert metadata["category"] == "run"
    return directory


def preview_snapshot(run_dir):
    text=(preview_directory(run_dir)/"snapshot.js").read_text(encoding="utf-8")
    payload=json.loads(text[len("VibeFlowPreview.snapshot("):-3])
    assert payload["version"]==2
    return payload


def preview_architecture(run_dir):
    return preview_snapshot(run_dir)["architecture"]
