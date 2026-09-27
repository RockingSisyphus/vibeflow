from __future__ import annotations

import argparse
import json
from pathlib import Path


from vibeflow.tooling.application.quality_options import (
    add_quality_limit_arguments,
    _quality_thresholds,
    _quality_structure_overrides,
    _quality_structure_enabled,
)


def add_quality_parser(subparsers) -> None:
    quality = subparsers.add_parser("quality-check", help="run standalone Python code quality checks")
    quality.add_argument("--workspace", required=False, help="workspace vibeflow_config.jsonc path")
    quality.add_argument("--path", required=False, default=None, help="project directory or Python file to inspect")
    quality.add_argument(
        "--project-target",
        choices=("python", "javascript"),
        default=None,
        help=argparse.SUPPRESS,
    )
    quality.add_argument("--json", action="store_true", help="emit full quality report JSON")
    quality.add_argument("--check-side-effects", action="store_true", help="also warn about side-effect capable imports and calls")
    add_quality_limit_arguments(quality)


def handle_quality_check(args: argparse.Namespace) -> int:
    from vibeflow.core.result_scope import add_result_scope
    from vibeflow.core.quality import QualityStructureLimits, QualityThresholds
    from vibeflow.tooling.application.python.quality_output import format_quality_summary
    from vibeflow.tooling.application.python.project.quality_scan import DEFAULT_EXCLUDED_DIRS, scan_code_quality
    from vibeflow.core.findings import HealthReport

    thresholds = _quality_thresholds(args, QualityThresholds)
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    if args.include_references:
        excluded_dirs.discard("references")
    excluded_dirs.update(f"./{name}" for name in args.exclude_dir)
    excluded_dirs.update(f"./{path}" for path in args.exclude_path)
    structure_overrides = _quality_structure_overrides(args)
    structure_enabled = _quality_structure_enabled(args, bool(structure_overrides))
    if getattr(args, "workspace", None) and args.path is None:
        report = _workspace_quality_report(args, thresholds, structure_overrides, structure_enabled, excluded_dirs)
    else:
        report = scan_code_quality(
            Path(args.path or "."),
            thresholds=thresholds,
            structure_limits=QualityStructureLimits(**structure_overrides) if structure_enabled is True else None,
            excluded_dirs=excluded_dirs,
            check_side_effects=bool(args.check_side_effects),
        )
    if isinstance(report, HealthReport):
        source_payload = report.to_dict()
        payload = add_result_scope(
            {**source_payload, "source_quality": source_payload, "reports": []},
            "vibeflow_quality",
            checked_ids=None if report.status in {"PASS", "CONCERNS"} else (),
        )
        print(
            json.dumps(payload, ensure_ascii=False, indent=2)
            if args.json
            else _format_health_summary(report)
        )
        return 0 if report.status in {"PASS", "CONCERNS"} else 1
    source_payload = report.to_dict()
    workflow_reports = _python_quality_workflow_reports(args)
    statuses = {str(item.get("status", "ERROR")) for item in workflow_reports}
    status = (
        "FAIL" if report.status == "FAIL" or statuses.intersection({"FAIL", "ERROR"})
        else "CONCERNS" if report.status == "CONCERNS" or "CONCERNS" in statuses
        else "PASS"
    )
    payload = add_result_scope(
        {**source_payload, "status": status, "source_quality": source_payload, "reports": workflow_reports},
        "vibeflow_quality",
        checked_ids=None,
    )
    print(
        json.dumps(payload, ensure_ascii=False, indent=2)
        if args.json
        else "\n".join((f"Project quality: {status}", format_quality_summary(report), *(f"Workflow: {item['status']} {item['config']}" for item in workflow_reports)))
    )
    return 0 if status in {"PASS", "CONCERNS"} else 1


def _python_quality_workflow_reports(args: argparse.Namespace) -> list[dict[str, object]]:
    from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
    from vibeflow.tooling.project.workflow_discovery import workflow_configs_for_root
    from vibeflow.tooling.project.workspace_loader import find_project_config, load_project_workspace, load_workspace_config

    if args.workspace and args.path is None:
        workspace = load_workspace_config(args.workspace)
    else:
        selected = Path(args.path or ".").resolve()
        if not selected.is_dir():
            return []
        project = find_project_config(selected)
        if project is None or project.parent != selected:
            return []
        workspace = load_project_workspace(project)
    reports = []
    for root in workspace.roots:
        if root.project_target != "python" or not root.quality_enabled:
            continue
        for config in workflow_configs_for_root(root):
            result = validate_workspace_config_path(config, workspace=workspace)
            reports.append({"config": str(config), **result.to_dict()})
    return reports


def _workspace_quality_report(args, thresholds, structure_overrides, structure_enabled, excluded_dirs):
    from vibeflow.core.findings import HealthReport
    from vibeflow.tooling.application.python.workspace_service import scan_workspace_code_quality

    workspace = _load_workspace_for_quality(Path(args.workspace))
    if isinstance(workspace, HealthReport):
        return workspace
    return scan_workspace_code_quality(
        workspace,
        thresholds=thresholds,
        structure_overrides=structure_overrides,
        structure_enabled=structure_enabled,
        excluded_dirs=excluded_dirs,
        check_side_effects=bool(args.check_side_effects),
    )


def _format_health_summary(report) -> str:
    from vibeflow.core.result_scope import add_result_scope, format_result_scope
    from vibeflow.tooling.application.python.reports import format_finding_text

    payload = add_result_scope(
        report.to_dict(),
        "vibeflow_quality",
        checked_ids=None if report.status in {"PASS", "CONCERNS"} else (),
    )
    lines = [format_result_scope(payload)]
    lines.extend(format_finding_text(finding) for finding in (*report.errors, *report.warnings))
    return "\n".join(lines)


def _load_workspace_for_quality(path: Path):
    from vibeflow.core.findings import HealthFinding, HealthReport
    from vibeflow.tooling.application.python.workspace_service import WorkspaceConfigError, load_workspace_config

    try:
        return load_workspace_config(path)
    except WorkspaceConfigError as exc:
        return HealthReport(
            status="ERROR",
            errors=(
                HealthFinding(
                    rule_id=exc.rule_id,
                    severity="error",
                    object_type="workspace",
                    object_id=str(path),
                    source_location=dict(exc.source_location),
                    failure_layer=exc.failure_layer,
                    message=exc.message,
                    suggested_fix_type="fix_config",
                ),
            ),
        )
