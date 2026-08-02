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
) -> SourceQualityReport:
    """Evaluate already-extracted facts without source, AST, paths or I/O."""

    active = policy or QualityPolicy()
    files = tuple(sorted(facts.files, key=lambda item: item.path))
    modules = {file.module for file in files}
    dependency_graph = _build_dependency_graph(files, modules)
    import_sites = _import_sites_by_edge(files, modules)
    findings: list[QualityFinding] = []
    target_findings = list(facts.findings)
    for file in files:
        owned = [
            finding
            for finding in target_findings
            if _finding_belongs_to_file(finding, file)
        ]
        target_findings = [
            finding for finding in target_findings if finding not in owned
        ]
        if not any(
            finding.rule_id.startswith("QUALITY.SYNTAX.")
            for finding in owned
        ):
            findings.extend(_file_findings(file, facts.root, active))
        findings.extend(owned)
    findings.extend(target_findings)

    directories, clusters, structure_summary, structure_findings = (
        analyze_directory_structure(
            files,
            dependency_graph,
            import_sites,
            active.thresholds,
        )
    )
    findings.extend(structure_findings)
    root_summary, root_findings = analyze_root_structure(
        files,
        dependency_graph,
        import_sites,
        active.structure_limits,
        roles=active.structure_roles,
    )
    structure_summary.update(root_summary)
    findings.extend(root_findings)
    graph_findings, longest_chain = dependency_findings(
        dependency_graph,
        import_sites,
        active.thresholds,
    )
    findings.extend(graph_findings)
    findings.extend(duplicate_function_findings(files))
    findings = _dedupe_findings(findings)
    has_error = any(finding.severity == "error" for finding in findings)
    status = "FAIL" if has_error else ("CONCERNS" if findings else "PASS")
    return SourceQualityReport(
        status=status,
        root=facts.root,
        thresholds=active.thresholds,
        files=files,
        dependency_graph=dependency_graph,
        longest_dependency_chain=tuple(longest_chain),
        findings=tuple(findings),
        directory_graph=directories,
        prefix_clusters=clusters,
        structure_summary=structure_summary,
    )


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
        ),
        (
            thresholds.warn_file_lines <= file.lines <= thresholds.max_file_lines,
            "QUALITY.FILE.WARN_LINES",
            "warning",
            f"file has {file.lines} lines",
        ),
        (
            file.bytes > thresholds.max_file_bytes,
            "QUALITY.FILE.MAX_BYTES",
            "error",
            f"file has {file.bytes} bytes",
        ),
        (
            file.function_count > thresholds.max_functions_per_file,
            "QUALITY.FILE.TOO_MANY_FUNCTIONS",
            "warning",
            f"file has {file.function_count} functions",
        ),
        (
            file.class_count > thresholds.max_classes_per_file,
            "QUALITY.FILE.TOO_MANY_CLASSES",
            "warning",
            f"file has {file.class_count} classes",
        ),
        (
            file.public_api_count > thresholds.max_public_api_per_file,
            "QUALITY.FILE.TOO_WIDE_PUBLIC_API",
            "warning",
            f"file exposes {file.public_api_count} public top-level objects",
        ),
        (
            file.branch_count > thresholds.max_file_branches,
            "QUALITY.FILE.TOO_MANY_BRANCHES",
            "warning",
            f"file has {file.branch_count} branches",
        ),
    )
    findings = [
        _finding(rule_id, severity, "file", file.path, source_path, 1, message)
        for matched, rule_id, severity, message in checks
        if matched
    ]
    for function in file.functions:
        object_id = f"{file.path}:{function.qualname}"
        function_checks = (
            (
                function.lines > thresholds.max_function_lines,
                "QUALITY.FUNCTION.MAX_LINES",
                f"function has {function.lines} lines",
            ),
            (
                function.branches > thresholds.max_function_branches,
                "QUALITY.FUNCTION.TOO_MANY_BRANCHES",
                f"function has {function.branches} branches",
            ),
            (
                function.max_nesting_depth > thresholds.max_function_nesting,
                "QUALITY.FUNCTION.TOO_DEEP_NESTING",
                f"function nesting depth is {function.max_nesting_depth}",
            ),
            (
                function.param_count > thresholds.max_function_params,
                "QUALITY.FUNCTION.TOO_MANY_PARAMS",
                f"function has {function.param_count} parameters",
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
            )
            for matched, rule_id, message in function_checks
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
) -> QualityFinding:
    return QualityFinding(
        rule_id=rule_id,
        severity=severity,
        object_type=object_type,
        object_id=object_id,
        source_location={"path": source_path, "line": line},
        message=message,
        suggested_fix_type="refactor",
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
