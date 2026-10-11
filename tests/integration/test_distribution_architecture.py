"""Architecture freshness through real launchers from extracted release ZIPs."""

import json
import os
import subprocess
import sys
import zipfile

import pytest

from distribution.build import ARCHIVE_ROOT_NAME, build_release_set
from vibeflow.tooling.project.config_loader import strip_jsonc_comments


@pytest.fixture(scope="module")
def releases(tmp_path_factory):
    root = tmp_path_factory.mktemp("architecture-releases")
    return build_release_set(
        root / "collaborative",
        autonomous_output=root / "autonomous",
        archive_dir=root / "archives",
        run_self_check=False,
    )


@pytest.fixture(params=["collaborative", "autonomous"])
def distribution(releases, request, tmp_path):
    with zipfile.ZipFile(getattr(releases, request.param).archive) as archive:
        archive.extractall(tmp_path)
    root = tmp_path / ARCHIVE_ROOT_NAME
    _command(root, ["npm", "ci", "--prefix", "javascript_project"])
    return root


def _command(root, arguments, *, expected=0):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(arguments, cwd=root, env=environment,
                               text=True, capture_output=True, check=False)
    assert completed.returncode == expected, completed.stdout + completed.stderr
    return completed


def _architecture(root, *, check=False):
    return _command(root, [sys.executable, "-I", "run.py", "architecture",
        "--config", "javascript_project/configs/main.jsonc",
        "--output", "javascript_project/ARCHITECTURE.jsonc", *(["--check"] if check else [])])


def test_javascript_architecture_immediate_check_passes(distribution):
    _architecture(distribution)
    _architecture(distribution, check=True)


def test_javascript_architecture_repeated_exports_are_identical(distribution):
    output = distribution / "javascript_project/ARCHITECTURE.jsonc"
    _architecture(distribution)
    first = output.read_bytes()
    _architecture(distribution)
    assert output.read_bytes() == first
    document = json.loads(strip_jsonc_comments(first.decode("utf-8")))
    states = document["rule_checks"]["facts"]["source_load_states"]
    assert states["nodes/process_payload.ts"] == "loaded"
    assert not any("vibeflow-js-resources-" in path for path in states)


def test_javascript_architecture_still_detects_workflow_changes(distribution):
    _architecture(distribution)
    config = distribution / "javascript_project/configs/main.jsonc"
    document = json.loads(strip_jsonc_comments(config.read_text(encoding="utf-8")))
    document["pipeline"]["nodes"][2]["description"] = "Changed processing description"
    config.write_text(json.dumps(document), encoding="utf-8")
    completed = _command(distribution, [sys.executable, "-I", "run.py", "architecture",
        "--config", "javascript_project/configs/main.jsonc",
        "--output", "javascript_project/ARCHITECTURE.jsonc", "--check"], expected=1)
    assert json.loads(completed.stdout)["code"] == "ARCHITECTURE.DOCUMENT.STALE"
