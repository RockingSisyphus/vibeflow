"""Temporary real projects and observations; no replacement VibeFlow checker."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_project(work, target, *, example="domain_rules", toolchain=None):
    destination = work / target
    shutil.copytree(ROOT / "sandbox" / target / example, destination,
                    ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc", ".artifacts"))
    import runpy
    copy_archival_inputs = runpy.run_path(str(ROOT / "tests/fixtures/support/code_plugins.py"))["copy_archival_inputs"]
    copy_archival_inputs(ROOT / "sandbox" / target / example, destination)
    project = destination / "project"
    if target == "javascript":
        if toolchain is None:
            raise FileNotFoundError("JavaScript cases require the locked toolchain")
        (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    return destination, project


def diagnostics(value):
    if isinstance(value, dict):
        if ("code" in value or "rule_id" in value) and ("message" in value or "error" in value):
            yield value
        for item in value.values():
            yield from diagnostics(item)
    elif isinstance(value, list):
        for item in value:
            yield from diagnostics(item)


def records(value):
    if isinstance(value, dict):
        if isinstance(value.get("type_id"), str) and "value" in value:
            yield value
        for item in value.values():
            yield from records(item)
    elif isinstance(value, list):
        for item in value:
            yield from records(item)


def normalize(process, *, metrics=None):
    try:
        payload = json.loads(process.stdout)
        valid_json = isinstance(payload, dict)
    except ValueError:
        payload, valid_json = {}, False
    found = list(diagnostics(payload))
    codes = sorted({(str(item.get("code", item.get("rule_id"))), item.get("severity", "error")) for item in found},
                   key=lambda item: (item[0], repr(item[1])))
    status = payload.get("status", "PASS" if process.returncode == 0 else "ERROR")
    if process.returncode and status in {"PASS", "CONCERNS"}:
        status = "ERROR"
    locations = [{"code": str(item.get("code", item.get("rule_id"))), **item.get("source_location", {})}
                 for item in found if isinstance(item.get("source_location"), dict)]
    message = "\n".join(str(item.get("message", item.get("error", ""))) for item in found)
    if payload.get("error"):
        message += "\n" + str(payload["error"])
    if not valid_json:
        message += process.stderr
    return {"status": status, "codes": [{"code": code, "severity": severity} for code, severity in codes],
            "positions": locations, "message": message, "metrics": {
                "exit_code": process.returncode, "json_output": valid_json, **(metrics or {})},
            "payload": payload, "stderr": process.stderr}


def command(project, arguments, *, name, executable=None, timeout=120):
    import runpy
    helpers = runpy.run_path(str(ROOT / "tests/fixtures/support/code_plugins.py"))
    if "--workspace" in arguments:
        helpers["prepare_workspace_fixture"](arguments[list(arguments).index("--workspace") + 1])
    else:
        helpers["migrate_fixture"](project)
    cmd = [*(executable or [sys.executable, "-m", "vibeflow"]), *map(str, arguments)]
    process = subprocess.run(cmd, cwd=project, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                             text=True, capture_output=True, check=False, timeout=timeout)
    logs = project.parent / "observations"
    logs.mkdir(exist_ok=True)
    write(logs / (name + ".json"), {"command": cmd, "exit_code": process.returncode,
                                    "stdout": process.stdout, "stderr": process.stderr})
    return normalize(process)


def cli(project, command_name, *, name, extra=(), config=None):
    arguments = [command_name, "--workspace", project.parent / "vibeflow_config.jsonc"]
    if command_name != "quality-check":
        arguments += ["--config", config or project / "configs/model.jsonc"]
    if command_name in {"validate", "quality-check", "review-rules"}:
        arguments.append("--json")
    arguments.extend(extra)
    return command(project, arguments, name=name)


def row(case_id, title, family, actual, expected=None, *, classification="new_feature"):
    return {"id": case_id, "title": title, "family": family, "classification": classification,
            "expected": {"should_accept": True, "metrics": {"exit_code": 0, "json_output": True}, **(expected or {})},
            "actual": actual}
