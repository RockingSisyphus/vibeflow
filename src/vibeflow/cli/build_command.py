from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping


def add_build_parser(subparsers: argparse._SubParsersAction) -> None:
    build = subparsers.add_parser(
        "build",
        help="compile a workflow into a standalone JavaScript/TypeScript AOT artifact",
    )
    build.add_argument(
        "--workspace",
        required=True,
        help="workspace vibeflow_config.jsonc path",
    )
    build.add_argument("--config", required=True, help="workflow JSONC path")
    build.add_argument("--target", required=True, choices=("browser", "node"))
    build.add_argument(
        "--profile",
        required=True,
        choices=("esm-module", "single-esm", "web-app"),
    )
    build.add_argument("--out-dir", required=True, help="dedicated output directory")
    build.add_argument("--entry-name", default="", help="JavaScript entry file name")
    build.add_argument(
        "--sourcemap",
        choices=("none", "external", "inline"),
        default="external",
    )
    build.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing VibeFlow-owned AOT output",
    )
    build.add_argument("--html", dest="html_template", help="web-app HTML template")
    build.add_argument(
        "--app-entry",
        help="web-app JavaScript/TypeScript application entry",
    )
    build.add_argument(
        "--workflow-id",
        default="",
        help="stable public workflow identifier",
    )
    build.add_argument("--node-command", default="node", help=argparse.SUPPRESS)


def handle_build(args: argparse.Namespace) -> int:
    from vibeflow.aot.project_build import (
        ProjectBuildRequest,
        build_project_aot,
    )

    try:
        result = build_project_aot(
            ProjectBuildRequest(
                workspace=Path(args.workspace),
                config=Path(args.config),
                out_dir=Path(args.out_dir),
                target=args.target,
                profile=args.profile,
                workflow_id=args.workflow_id,
                entry_name=args.entry_name,
                sourcemap=args.sourcemap,
                replace=args.replace,
                html_template=(
                    Path(args.html_template) if args.html_template else None
                ),
                app_entry=Path(args.app_entry) if args.app_entry else None,
                node_command=args.node_command,
            )
        )
    except Exception as exc:
        diagnostics = getattr(exc, "diagnostics", ())
        payload: dict[str, object] = {
            "status": "ERROR",
            "code": str(getattr(exc, "code", "VF_BUILD_FAILED")),
            "error": str(getattr(exc, "message", str(exc))),
        }
        if diagnostics:
            payload["diagnostics"] = [
                dict(item) if isinstance(item, Mapping) else str(item)
                for item in diagnostics
            ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    payload = {
        "status": "PASS",
        "workflow_id": result.prepared.plan.workflow_id,
        "target": args.target,
        "profile": args.profile,
        "out_dir": str(result.out_dir),
        "entry": str(result.entry),
        "manifest": str(result.manifest),
        "files": list(result.files),
        "toolchain": result.build.toolchain.to_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


__all__ = ["add_build_parser", "handle_build"]
