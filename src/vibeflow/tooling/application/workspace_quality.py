"""Target-neutral aggregation for mixed-workspace quality reports."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence

from vibeflow.tooling.project.workspace_loader import load_workspace_config


_STATUS_RANK = {
    "PASS": 0,
    "CONCERNS": 1,
    "FAIL": 2,
    "ERROR": 3,
}


def main(argv: Sequence[str]) -> int:
    args = list(argv)
    workspace_value = _option_value(args, "--workspace")
    if not workspace_value:
        return _print_payload(
            {
                "status": "ERROR",
                "code": "WORKSPACE.CONFIG.MISSING",
                "error": "mixed workspace quality-check requires --workspace",
            },
            json_output="--json" in args,
        )
    workspace = load_workspace_config(workspace_value)
    root_reports: list[dict[str, object]] = []
    return_code = 0
    for root in workspace.roots:
        if not root.quality_enabled:
            root_reports.append(
                {
                    "id": root.id,
                    "target": root.project_target,
                    "status": "SKIPPED",
                    "path": str(root.path),
                }
            )
            continue
        report, code = _run_root_quality(
            root,
            args,
            workspace_path=workspace.path,
        )
        return_code = max(return_code, code)
        root_reports.append(
            {
                "id": root.id,
                "target": root.project_target,
                "status": str(report.get("status", "ERROR")),
                "path": str(root.path),
                "report": report,
            }
        )
    status = _aggregate_status(root_reports)
    if status in {"FAIL", "ERROR"}:
        return_code = max(return_code, 1)
    payload = {
        "status": status,
        "workspace": str(workspace.path),
        "roots": root_reports,
    }
    return _print_payload(
        payload,
        json_output="--json" in args,
        return_code=return_code,
    )


def _run_root_quality(
    root: object,
    args: list[str],
    *,
    workspace_path: Path,
) -> tuple[dict[str, object], int]:
    target = str(getattr(root, "project_target"))
    root_args = _root_arguments(
        args,
        path=Path(getattr(root, "path")),
        target=target,
        workspace_path=workspace_path,
    )
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    # A distribution launcher adds the embedded kernel ZIP to ``sys.path`` at
    # runtime.  Propagate the effective path so the isolated child works for
    # source checkouts, installed wheels, and the copyable distribution alike.
    environment["PYTHONPATH"] = os.pathsep.join(
        str(item) for item in sys.path if str(item)
    )
    command = [sys.executable, "-m", "vibeflow", *root_args]
    try:
        completed = subprocess.run(
            command,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        return (
            {
                "status": "ERROR",
                "code": "QUALITY.TARGET.PROCESS",
                "error": f"cannot start isolated {target} quality process: {exc}",
            },
            1,
        )
    code = int(completed.returncode)
    text = completed.stdout.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {
            "status": "ERROR",
            "code": "QUALITY.TARGET.REPORT",
            "error": "target quality command did not return one JSON report",
            "output": text,
        }
        diagnostic = completed.stderr.strip()
        if diagnostic:
            payload["stderr"] = diagnostic
        code = 1
    if not isinstance(payload, dict):
        payload = {
            "status": "ERROR",
            "code": "QUALITY.TARGET.REPORT",
            "error": "target quality report must be a JSON object",
        }
        code = 1
    return payload, code


def _root_arguments(
    args: list[str],
    *,
    path: Path,
    target: str,
    workspace_path: Path,
) -> list[str]:
    clean: list[str] = ["quality-check"]
    index = 1
    options_with_values = {"--workspace", "--path", "--project-target"}
    while index < len(args):
        item = args[index]
        if item == "--json":
            index += 1
            continue
        name = item.split("=", 1)[0]
        if name in options_with_values:
            index += 1 if "=" in item else 2
            continue
        if target == "python" and name == "--node-command":
            index += 1 if "=" in item else 2
            continue
        if target == "javascript" and name != "--node-command":
            index += 1
            if (
                "=" not in item
                and index < len(args)
                and not args[index].startswith("--")
            ):
                index += 1
            continue
        clean.append(item)
        if (
            target == "javascript"
            and name == "--node-command"
            and "=" not in item
            and index + 1 < len(args)
        ):
            clean.append(args[index + 1])
            index += 1
        index += 1
    clean.extend(
        (
            "--workspace",
            str(workspace_path),
            "--path",
            str(path),
            "--project-target",
            target,
            "--json",
        )
    )
    return clean


def _aggregate_status(reports: list[dict[str, object]]) -> str:
    statuses = [
        str(item.get("status", "ERROR"))
        for item in reports
        if item.get("status") != "SKIPPED"
    ]
    if not statuses:
        return "PASS"
    return max(statuses, key=lambda item: _STATUS_RANK.get(item, 3))


def _option_value(args: list[str], name: str) -> str:
    prefix = f"{name}="
    for index, item in enumerate(args):
        if item.startswith(prefix):
            return item[len(prefix) :]
        if item == name and index + 1 < len(args):
            return args[index + 1]
    return ""


def _print_payload(
    payload: dict[str, object],
    *,
    json_output: bool,
    return_code: int = 1,
) -> int:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("status", "ERROR"))
        for root in payload.get("roots", ()):
            if isinstance(root, dict):
                print(
                    f"{root.get('id', '')} [{root.get('target', '')}]: "
                    f"{root.get('status', 'ERROR')}"
                )
        if payload.get("error"):
            print(payload["error"])
    return return_code


__all__ = ["main"]
