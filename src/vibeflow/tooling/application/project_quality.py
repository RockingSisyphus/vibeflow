"""Project governance and per-workflow checks without subprocess orchestration."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from vibeflow.core.findings import HealthReport
from vibeflow.tooling.project.preparation import ProjectPreparation
from vibeflow.tooling.project.workspace_loader import load_workspace_config, load_project_workspace


def add_quality_parser(subparsers):
    parser = subparsers.add_parser("quality-check", help="check project/root governance and all workflow declarations")
    _arguments(parser)


def _arguments(parser):
    parser.add_argument("--workspace", help="project vibeflow_config.jsonc")
    parser.add_argument("--path", help="path inside the project (default: current directory)")
    parser.add_argument("--node-command", default="node")
    parser.add_argument("--json", action="store_true")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vibeflow quality-check")
    _arguments(parser)
    return handle_quality_check(parser.parse_args(argv))


def handle_quality_check(args):
    try:
        workspace = load_workspace_config(args.workspace) if args.workspace else load_project_workspace(Path(args.path or "."))
        preparation = ProjectPreparation(workspace, node_command=args.node_command)
        governance = preparation.review(write_architecture=True)
        reports = []
        for document in governance.inventory.workflows:
            if document.path not in preparation.workflows:
                continue  # The preparation diagnostic already identifies the failed declaration.
            root = workspace.root_by_id(document.root_id)
            try:
                from vibeflow.tooling.application.project_targets import preparation_adapter
                report = preparation_adapter(root.project_target).review_workflow(workspace,document.path,
                    preparation=preparation,governance=replace(governance,findings=()))
            except Exception as error:
                report = {"status": "ERROR", "error": str(error), "code": getattr(error, "code", "WORKFLOW.CHECK"),
                    "diagnostics": list(getattr(error, "diagnostics", ()))}
            reports.append({"config": str(document.path), "root": root.id, **report})
        errors = [finding.to_dict() for finding in governance.findings if finding.severity == "error"]
        warnings = [finding.to_dict() for finding in governance.findings if finding.severity != "error"]
        status = "FAIL" if errors or any(item["status"] in {"FAIL", "ERROR"} for item in reports) else "CONCERNS" if warnings or any(item["status"] == "CONCERNS" for item in reports) else "PASS"
        payload = {"status": status, "workspace": str(workspace.path), "errors": errors,
            "warnings": warnings, "reports": reports, "governance": [item.to_dict() for item in governance.results], "project_architecture": str(governance.architecture_path)}
    except Exception as error:
        payload = {"status": "ERROR", "code": getattr(error, "rule_id", getattr(error, "code", "PROJECT.CHECK")), "error": str(error)}
    from vibeflow.tooling.application.result_scope import add_result_scope
    payload = add_result_scope(payload, "vibeflow_quality")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Project quality: " + payload["status"])
        for item in (*payload.get("errors", ()), *payload.get("warnings", ())):
            print(f"{item['rule_id']}: {item['message']}")
        for item in payload.get("reports", ()):
            print(f"{item['status']}: {item['config']}")
            for finding in item.get("diagnostics", ()):
                location = finding.get("source_location", {})
                source = ":".join(str(location[name]) for name in ("path", "line", "column") if name in location)
                print(f"{source}: " + json.dumps(finding, ensure_ascii=False))
        if payload.get("error"):
            print(f"{payload['code']}: {payload['error']}")
    return 0 if payload["status"] in {"PASS", "CONCERNS"} else 1
