"""Small I/O helpers for the independent arithmetic sandbox runners."""
from __future__ import annotations

from tests.fixtures.support.preview import preview_directory, preview_architecture, preview_snapshot

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
PLUGIN_EXPECTED = {
    "baseline": {"default": [5, 13, 1], "override": [6, 14, 2]},
    "edited": {"default": [6, 14, 2]},
    "restored": {"default": [5, 13, 1]},
}


def workspace(fixture, work, toolchain=None):
    shutil.copytree(fixture / "project", work / "project", ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    shutil.copy2(fixture / "vibeflow_config.jsonc", work / "vibeflow_config.jsonc")
    if (work / "project/package.json").exists():
        if toolchain:
            (work / "project/node_modules").symlink_to(toolchain.resolve() / "node_modules", target_is_directory=True)
        else:
            subprocess.run(["npm", "ci"], cwd=work / "project", check=True)
    return work / "vibeflow_config.jsonc"


def value(context, key):
    item = context.get(key)
    return item["value"] if isinstance(item, Mapping) and "value" in item else item.value if hasattr(item, "value") else item


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def assert_artifacts(run_dir):
    health = json.loads((run_dir / "health_report.json").read_text())
    assert health["status"] in {"PASS", "CONCERNS"} and not health["errors"], health
    for name in ("architecture.jsonc", "snapshot.js"):
        assert (preview_directory(run_dir) / name).is_file(), name
    assert preview_architecture(run_dir)["workflow"]["nodes"]
    assert not list(preview_directory(run_dir).glob("*.svg"))


def cli(arguments, *, stdin=None):
    result = subprocess.run([os.sys.executable, "-m", "vibeflow", *map(str, arguments)],
        input=stdin, capture_output=True, env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"})
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()
    return result


def main(run, label, *, javascript=False):
    parser = argparse.ArgumentParser(description=label)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--toolchain-root", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vibeflow-addition-") as temporary:
        work = args.work_dir.resolve() if args.work_dir else Path(temporary)
        work.mkdir(parents=True, exist_ok=True)
        started = perf_counter()
        report = run(work, toolchain=args.toolchain_root)
        report["seconds"] = round(perf_counter() - started, 3)
        (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"{label}: {report['status']} observations={len(report['observations'])} seconds={report['seconds']} report={work / 'report.json'}")
