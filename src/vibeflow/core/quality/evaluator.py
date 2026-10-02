"""Pure, target-neutral project-quality evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from .dependencies import dependency_findings
from .duplicates import duplicate_function_findings
from .models import (
    FileQuality,
    ProjectQualityFacts,
    QualityFinding,
    QualityPolicy,
    SourceQualityReport,
)
from .root_structure import analyze_root_structure
from .structure import analyze_directory_structure


def evaluate_project_quality(
    facts: ProjectQualityFacts,
    policy: QualityPolicy | None = None,
    *,
    rulesets=None,
    rules=None,
    ruleset_catalog=None,
    handlers=None,
    entrypoint: str = "static",
    context=None,
) -> SourceQualityReport:
    """Run an explicit Rule selection over the supplied source scope.

    ``None`` selects the default project Ruleset; ``()`` requests facts only.
    Resources and callables can be supplied by any composition root. Neither
    this function nor the Rule handlers discover additional files or Nodes.
    """
    from dataclasses import replace
    from vibeflow.core.rules import RuleCall, RuleContext, RuleDescriptor, RulesetDescriptor, compile_ruleset, execute_rule_plan
    from vibeflow.core.rules.builtin.project_quality import project_quality_handlers, project_quality_resources
    from vibeflow.core.quality.rule_report import project_quality_report

    active = policy or QualityPolicy()
    normalized = ProjectQualityFacts(facts.root, tuple(sorted(facts.files, key=lambda item: item.path)), facts.findings)
    builtin_rules, default_set = project_quality_resources(active)
    resources = {item.id: item for item in builtin_rules}
    resources.update(_resources_by_id(rules))
    sets = {default_set.id: default_set, **_resources_by_id(ruleset_catalog)}
    selected = (default_set.id,) if rulesets is None else (rulesets,) if isinstance(rulesets, (str, RuleDescriptor, RulesetDescriptor)) else tuple(rulesets)
    implementations = {**project_quality_handlers(), **dict(handlers or {})}
    base_context = context or RuleContext(subject={"kind": "source", "id": facts.root},
        scope={"root": facts.root, "files": tuple(item.path for item in normalized.files)}, phase=entrypoint)
    active_context = replace(base_context, facts={**base_context.facts, "project_facts": normalized}, phase=entrypoint)
    executions, selected_ids = [], []
    for item in selected:
        if isinstance(item, RuleDescriptor):
            resources[item.id] = item
            item = RulesetDescriptor("rule:" + item.id, (RuleCall("check", item.id),))
        elif isinstance(item, str) and item not in sets and item in resources:
            item = RulesetDescriptor("rule:" + item, (RuleCall("check", item),))
        plan = compile_ruleset(item, rules=resources, rulesets=sets, entrypoint=entrypoint)
        selected_ids.append(plan.ruleset_id)
        executions.append(execute_rule_plan(plan, active_context, handlers=implementations))
    return project_quality_report(normalized, active, tuple(executions), tuple(selected_ids))


def _resources_by_id(resources):
    if resources is None:
        return {}
    return dict(resources) if isinstance(resources, Mapping) else {item.id: item for item in resources}


def _file_findings(
    file: FileQuality,
    root: str,
    policy: QualityPolicy,
) -> list[QualityFinding]:
    thresholds = policy.thresholds
    source_path = _source_path(root, file.path)
    checks = (
        (
            file.lines > thresholds.max_file_lines,
            "QUALITY.FILE.MAX_LINES",
            "error",
            f"file has {file.lines} lines",
            file.lines, thresholds.max_file_lines,
        ),
        (
            thresholds.warn_file_lines <= file.lines <= thresholds.max_file_lines,
            "QUALITY.FILE.WARN_LINES",
            "warning",
            f"file has {file.lines} lines",
            file.lines, thresholds.warn_file_lines,
        ),
        (
            file.bytes > thresholds.max_file_bytes,
            "QUALITY.FILE.MAX_BYTES",
            "error",
            f"file has {file.bytes} bytes",
            file.bytes, thresholds.max_file_bytes,
        ),
        (
            file.function_count > thresholds.max_functions_per_file,
            "QUALITY.FILE.TOO_MANY_FUNCTIONS",
            "warning",
            f"file has {file.function_count} functions",
            file.function_count, thresholds.max_functions_per_file,
        ),
        (
            file.class_count > thresholds.max_classes_per_file,
            "QUALITY.FILE.TOO_MANY_CLASSES",
            "warning",
            f"file has {file.class_count} classes",
            file.class_count, thresholds.max_classes_per_file,
        ),
        (
            file.public_api_count > thresholds.max_public_api_per_file,
            "QUALITY.FILE.TOO_WIDE_PUBLIC_API",
            "warning",
            f"file exposes {file.public_api_count} public top-level objects",
            file.public_api_count, thresholds.max_public_api_per_file,
        ),
        (
            file.branch_count > thresholds.max_file_branches,
            "QUALITY.FILE.TOO_MANY_BRANCHES",
            "warning",
            f"file has {file.branch_count} branches",
            file.branch_count, thresholds.max_file_branches,
        ),
    )
    findings = [
        _finding(rule_id, severity, "file", file.path, source_path, 1, message, {"actual": actual, "limit": limit})
        for matched, rule_id, severity, message, actual, limit in checks
        if matched
    ]
    for function in file.functions:
        object_id = f"{file.path}:{function.qualname}"
        function_checks = (
            (
                function.lines > thresholds.max_function_lines,
                "QUALITY.FUNCTION.MAX_LINES",
                f"function has {function.lines} lines",
                function.lines, thresholds.max_function_lines,
            ),
            (
                function.branches > thresholds.max_function_branches,
                "QUALITY.FUNCTION.TOO_MANY_BRANCHES",
                f"function has {function.branches} branches",
                function.branches, thresholds.max_function_branches,
            ),
            (
                function.max_nesting_depth > thresholds.max_function_nesting,
                "QUALITY.FUNCTION.TOO_DEEP_NESTING",
                f"function nesting depth is {function.max_nesting_depth}",
                function.max_nesting_depth, thresholds.max_function_nesting,
            ),
            (
                function.param_count > thresholds.max_function_params,
                "QUALITY.FUNCTION.TOO_MANY_PARAMS",
                f"function has {function.param_count} parameters",
                function.param_count, thresholds.max_function_params,
            ),
        )
        findings.extend(
            _finding(
                rule_id,
                "warning",
                "function",
                object_id,
                source_path,
                function.line_start,
                message,
                {"actual": actual, "limit": limit},
            )
            for matched, rule_id, message, actual, limit in function_checks
            if matched
        )
    return findings


def _finding(
    rule_id: str,
    severity: str,
    object_type: str,
    object_id: str,
    source_path: str,
    line: int,
    message: str,
    details: Mapping[str, object] | None = None,
) -> QualityFinding:
    return QualityFinding(
        rule_id=rule_id,
        severity=severity,
        object_type=object_type,
        object_id=object_id,
        source_location={"path": source_path, "line": line},
        message=message,
        suggested_fix_type="refactor",
        details=details or {},
    )


def _source_path(root: str, relative: str) -> str:
    if not root or root == ".":
        return relative
    normalized_root = root.replace("\\", "/")
    normalized_relative = relative.replace("\\", "/")
    if normalized_root == normalized_relative or normalized_root.endswith(
        f"/{normalized_relative}"
    ):
        return root
    if root.endswith(("/", "\\")):
        return f"{root}{relative}"
    separator = "\\" if "\\" in root and "/" not in root else "/"
    return f"{root}{separator}{relative}"


def _finding_belongs_to_file(
    finding: QualityFinding,
    file: FileQuality,
) -> bool:
    if finding.object_id == file.path or finding.object_id.startswith(
        f"{file.path}:"
    ):
        return True
    source_path = str(finding.source_location.get("path", "")).replace(
        "\\", "/"
    )
    relative = file.path.replace("\\", "/")
    return source_path == relative or source_path.endswith(f"/{relative}")


def _build_dependency_graph(
    files: Sequence[FileQuality],
    modules: set[str],
) -> dict[str, tuple[str, ...]]:
    graph: dict[str, tuple[str, ...]] = {}
    for file in files:
        targets = {
            target
            for imported in file.imports
            if (target := _resolve_internal_import(imported, modules))
            and target != file.module
        }
        graph[file.module] = tuple(sorted(targets))
    return graph


def _import_sites_by_edge(
    files: Sequence[FileQuality],
    modules: set[str],
) -> dict[tuple[str, str], tuple[dict[str, object], ...]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for file in files:
        for site in file.import_sites:
            target = _resolve_internal_import(site.imported, modules)
            if not target or target == file.module:
                continue
            row = site.to_dict()
            row["target_module"] = target
            grouped.setdefault((file.module, target), []).append(row)
    return {edge: tuple(rows) for edge, rows in grouped.items()}


def _resolve_internal_import(imported: str, modules: set[str]) -> str | None:
    if imported in modules:
        return imported
    parts = imported.split(".")
    while len(parts) > 1:
        parts.pop()
        candidate = ".".join(parts)
        if candidate in modules:
            return candidate
    return None


def _dedupe_findings(
    findings: Sequence[QualityFinding],
) -> list[QualityFinding]:
    unique: dict[tuple[object, ...], QualityFinding] = {}
    for finding in findings:
        key = (
            finding.rule_id,
            finding.severity,
            finding.object_type,
            finding.object_id,
            json.dumps(
                finding.source_location,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            finding.message,
            json.dumps(
                finding.details,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )
        unique.setdefault(key, finding)
    return list(unique.values())


__all__ = ["evaluate_project_quality"]
