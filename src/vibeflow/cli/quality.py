from __future__ import annotations

import argparse
from pathlib import Path


def add_quality_parser(subparsers) -> None:
    quality = subparsers.add_parser("quality-check", help="run standalone Python code quality checks")
    quality.add_argument("--workspace", required=False, help="workspace vibeflow_config.jsonc path")
    quality.add_argument("--path", required=False, default=None, help="project directory or Python file to inspect")
    quality.add_argument("--json", action="store_true", help="emit full quality report JSON")
    quality.add_argument("--check-side-effects", action="store_true", help="also warn about side-effect capable imports and calls")
    quality.add_argument("--max-lines", type=int, default=500, help="maximum Python file lines before error")
    quality.add_argument("--warn-lines", type=int, default=450, help="Python file lines before warning")
    quality.add_argument("--max-bytes", type=int, default=60000, help="maximum Python file bytes before error")
    quality.add_argument("--max-file-branches", type=int, default=150, help="maximum Python file branch count before warning")
    quality.add_argument("--max-directory-fanout", type=int, default=25, help="maximum directory fanout before warning")
    quality.add_argument("--max-directory-fanin", type=int, default=25, help="maximum directory fanin before warning")
    quality.add_argument("--max-prefix-cluster-files", type=int, default=12, help="maximum same-prefix files before package warning")
    quality.add_argument("--max-public-entry-bypass-imports", type=int, default=3, help="maximum direct internal imports from one cluster before warning")
    quality.add_argument("--max-dependency-distance", type=int, default=3, help="maximum module path distance before warning")
    quality.add_argument("--max-scattered-dependency-directories", type=int, default=6, help="maximum far dependency directories before warning")
    quality.add_argument("--max-function-lines", type=int, default=80, help="maximum function lines before warning")
    quality.add_argument("--max-function-branches", type=int, default=12, help="maximum function branch count before warning")
    quality.add_argument("--max-function-nesting", type=int, default=4, help="maximum function nesting depth before warning")
    quality.add_argument("--max-function-params", type=int, default=6, help="maximum function parameter count before warning")
    quality.add_argument("--warn-dependency-depth", type=int, default=6, help="dependency chain length before warning")
    quality.add_argument("--max-dependency-depth", type=int, default=10, help="dependency chain length before error")
    _add_structure_arguments(quality)
    quality.add_argument("--include-references", action="store_true", help="also scan references/ directories")


def handle_quality_check(args: argparse.Namespace) -> int:
    from vibeflow.devtools.code_quality import DEFAULT_EXCLUDED_DIRS, QualityThresholds, format_quality_summary, scan_code_quality
    from vibeflow.devtools.code_quality_types import QualityStructureLimits
    from vibeflow.health.types import HealthReport

    thresholds = _quality_thresholds(args, QualityThresholds)
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    if args.include_references:
        excluded_dirs.discard("references")
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
        print(report.to_json() if args.json else _format_health_summary(report))
        return 0 if report.status in {"PASS", "CONCERNS"} else 1
    print(report.to_json() if args.json else format_quality_summary(report))
    return 0 if report.status in {"PASS", "CONCERNS"} else 1


def _add_structure_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--enable-structure-limits", action="store_true", help="enable root structure limits for --path scans")
    parser.add_argument("--no-structure-limits", action="store_true", help="disable workspace/root structure limits")
    parser.add_argument("--warn-root-code-files", type=int, default=None, help="root Python file count before warning")
    parser.add_argument("--max-root-code-files", type=int, default=None, help="root Python file count before error")
    parser.add_argument("--warn-code-dirs", type=int, default=None, help="code directory count before warning")
    parser.add_argument("--max-code-dirs", type=int, default=None, help="code directory count before error")
    parser.add_argument("--warn-code-files-per-dir", type=int, default=None, help="direct Python files per directory before warning")
    parser.add_argument("--max-code-files-per-dir", type=int, default=None, help="direct Python files per directory before error")
    parser.add_argument("--warn-code-dir-depth", type=int, default=None, help="code directory depth before warning")
    parser.add_argument("--max-code-dir-depth", type=int, default=None, help="code directory depth before error")
    parser.add_argument("--warn-child-code-dirs-per-dir", type=int, default=None, help="direct child code directories before warning")
    parser.add_argument("--max-child-code-dirs-per-dir", type=int, default=None, help="direct child code directories before error")
    parser.add_argument("--warn-root-level-code-files", type=int, default=None, help="non-allowlisted top-level Python files before warning")
    parser.add_argument("--max-root-level-code-files", type=int, default=None, help="non-allowlisted top-level Python files before error")


def _quality_thresholds(args: argparse.Namespace, threshold_cls):
    return threshold_cls(
        max_file_lines=args.max_lines,
        warn_file_lines=args.warn_lines,
        max_file_bytes=args.max_bytes,
        max_file_branches=args.max_file_branches,
        max_directory_fanout=args.max_directory_fanout,
        max_directory_fanin=args.max_directory_fanin,
        max_prefix_cluster_files=args.max_prefix_cluster_files,
        max_public_entry_bypass_imports=args.max_public_entry_bypass_imports,
        max_dependency_distance=args.max_dependency_distance,
        max_scattered_dependency_directories=args.max_scattered_dependency_directories,
        max_function_lines=args.max_function_lines,
        max_function_branches=args.max_function_branches,
        max_function_nesting=args.max_function_nesting,
        max_function_params=args.max_function_params,
        warn_dependency_chain=args.warn_dependency_depth,
        max_dependency_chain=args.max_dependency_depth,
    )


def _workspace_quality_report(args, thresholds, structure_overrides, structure_enabled, excluded_dirs):
    from vibeflow.health.types import HealthReport
    from vibeflow.workspace import scan_workspace_code_quality

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
    from vibeflow.cli.reports import format_finding_text

    lines = [report.status]
    lines.extend(format_finding_text(finding) for finding in (*report.errors, *report.warnings))
    return "\n".join(lines)


def _load_workspace_for_quality(path: Path):
    from vibeflow.health.types import HealthFinding, HealthReport
    from vibeflow.workspace import WorkspaceConfigError, load_workspace_config

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


def _quality_structure_enabled(args: argparse.Namespace, has_overrides: bool) -> bool | None:
    if args.no_structure_limits:
        return False
    if args.enable_structure_limits or has_overrides:
        return True
    return None


def _quality_structure_overrides(args: argparse.Namespace) -> dict[str, object]:
    fields = (
        "warn_root_code_files",
        "max_root_code_files",
        "warn_code_dirs",
        "max_code_dirs",
        "warn_code_files_per_dir",
        "max_code_files_per_dir",
        "warn_code_dir_depth",
        "max_code_dir_depth",
        "warn_child_code_dirs_per_dir",
        "max_child_code_dirs_per_dir",
        "warn_root_level_code_files",
        "max_root_level_code_files",
    )
    return {field: getattr(args, field) for field in fields if getattr(args, field) is not None}
