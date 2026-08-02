from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from vibeflow.targets.javascript.build.publish import (
    AotPublishError,
    atomic_publish_directory,
    validate_owned_build_directory,
)


FORMAT = "vibeflow.aot-build.v1"


def _artifact(path: Path, marker: str) -> None:
    path.mkdir(parents=True)
    entry = path / "index.js"
    entry.write_text(f"export default {marker!r};\n", encoding="utf-8")
    entry_hash = hashlib.sha256(entry.read_bytes()).hexdigest()
    lock_hash = hashlib.sha256(b"lock").hexdigest()
    plan_hash = hashlib.sha256(marker.encode()).hexdigest()
    manifest = {
        "format": FORMAT,
        "abi_version": "vibeflow.workflow.v2",
        "project_target": "javascript",
        "workflow_id": "publish-test",
        "entry_mode": "sync",
        "target": "node",
        "profile": "single-esm",
        "entry": "index.js",
        "plan_sha256": plan_hash,
        "toolchain": {
            "node": "22.12.0",
            "typescript": "7.0.2",
            "esbuild": "0.28.1",
            "lock_sha256": lock_hash,
            "lock_files": ["package-lock.json"],
        },
        "external_packages": [],
        "host_extensions": [],
        "files": {"index.js": entry_hash},
    }
    (path / "vibeflow-build.json").write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )


def test_owned_build_validation_rejects_forged_minimal_manifest(
    tmp_path: Path,
) -> None:
    target = tmp_path / "dist"
    target.mkdir()
    (target / "notes.txt").write_text("user data", encoding="utf-8")
    (target / "vibeflow-build.json").write_text(
        json.dumps({"format": FORMAT}),
        encoding="utf-8",
    )

    with pytest.raises(AotPublishError) as captured:
        validate_owned_build_directory(target, manifest_format=FORMAT)

    assert captured.value.code == "VF_BUILD_REPLACE"
    assert (target / "notes.txt").read_text(encoding="utf-8") == "user data"


@pytest.mark.parametrize("mutation", ["content", "extra_file", "extra_dir"])
def test_owned_build_validation_rejects_modified_artifacts(
    tmp_path: Path,
    mutation: str,
) -> None:
    target = tmp_path / "dist"
    _artifact(target, "old")
    if mutation == "content":
        (target / "index.js").write_text("changed\n", encoding="utf-8")
    elif mutation == "extra_file":
        (target / "notes.txt").write_text("user data\n", encoding="utf-8")
    else:
        (target / "private").mkdir()

    with pytest.raises(AotPublishError, match="modified|untracked"):
        validate_owned_build_directory(target, manifest_format=FORMAT)


def test_atomic_publish_exchanges_complete_directories(
    tmp_path: Path,
) -> None:
    target = tmp_path / "dist"
    staging = tmp_path / "staging"
    _artifact(target, "old")
    _artifact(staging, "new")

    atomic_publish_directory(
        staging,
        target,
        replace=True,
        manifest_format=FORMAT,
    )

    assert "'new'" in (target / "index.js").read_text(encoding="utf-8")
    assert "'old'" in (staging / "index.js").read_text(encoding="utf-8")
    validate_owned_build_directory(target, manifest_format=FORMAT)
    validate_owned_build_directory(staging, manifest_format=FORMAT)


def test_atomic_publish_failure_preserves_existing_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "dist"
    staging = tmp_path / "staging"
    _artifact(target, "old")
    _artifact(staging, "new")

    def fail_exchange(_source: Path, _target: Path) -> None:
        raise AotPublishError(
            "VF_BUILD_ATOMIC_REPLACE",
            "exchange unavailable",
        )

    monkeypatch.setattr(
        "vibeflow.targets.javascript.build.publish._exchange_directories",
        fail_exchange,
    )
    with pytest.raises(AotPublishError) as captured:
        atomic_publish_directory(
            staging,
            target,
            replace=True,
            manifest_format=FORMAT,
        )

    assert captured.value.code == "VF_BUILD_ATOMIC_REPLACE"
    assert "'old'" in (target / "index.js").read_text(encoding="utf-8")
    assert "'new'" in (staging / "index.js").read_text(encoding="utf-8")
