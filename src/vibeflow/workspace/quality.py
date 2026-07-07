from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from vibeflow.devtools.code_quality import DEFAULT_EXCLUDED_DIRS, QualityThresholds, scan_code_quality
from vibeflow.devtools.code_quality_types import DirectoryQuality, FileQuality, PrefixClusterQuality, QualityFinding, QualityReport, QualityStructureLimits
from vibeflow.workspace.types import WorkspaceConfig, WorkspaceRoot


def scan_workspace_code_quality(
    workspace: WorkspaceConfig,
    *,
    thresholds: QualityThresholds | None = None,
    structure_overrides: Mapping[str, object] | None = None,
    structure_enabled: bool | None = None,
    excluded_dirs=DEFAULT_EXCLUDED_DIRS,
    check_side_effects: bool = False,
) -> QualityReport:
    active_thresholds = thresholds or QualityThresholds()
    files: list[FileQuality] = []
    findings: list[QualityFinding] = []
    dependency_graph: dict[str, tuple[str, ...]] = {}
    directory_graph: list[DirectoryQuality] = []
    prefix_clusters: list[PrefixClusterQuality] = []
    longest: tuple[str, ...] = ()
    roots_payload: list[dict[str, object]] = []
    for root in workspace.roots:
        if not root.quality_enabled:
            continue
        report = scan_code_quality(
            root.path,
            thresholds=active_thresholds,
            structure_limits=_structure_limits_for_root(root.quality_structure, overrides=structure_overrides, enabled=structure_enabled),
            excluded_dirs=excluded_dirs,
            check_side_effects=check_side_effects,
        )
        roots_payload.append({"id": root.id, "path": str(root.path), "files": len(report.files), "status": report.status})
        files.extend(_prefix_quality_files(report.files, root=root))
        findings.extend(_prefix_quality_findings(report.findings, root=root))
        dependency_graph.update(_prefix_dependency_graph(report.dependency_graph, root=root))
        directory_graph.extend(_prefix_directories(report.directory_graph, root=root))
        prefix_clusters.extend(_prefix_clusters(report.prefix_clusters, root=root))
        chain = tuple(f"{root.id}.{item}" for item in report.longest_dependency_chain)
        if len(chain) > len(longest):
            longest = chain
    has_error = any(finding.severity == "error" for finding in findings)
    status = "FAIL" if has_error else ("CONCERNS" if findings else "PASS")
    return QualityReport(
        status=status,
        root=str(workspace.root),
        thresholds=active_thresholds,
        files=tuple(sorted(files, key=lambda item: item.path)),
        dependency_graph=dependency_graph,
        longest_dependency_chain=longest,
        findings=tuple(findings),
        directory_graph=tuple(directory_graph),
        prefix_clusters=tuple(prefix_clusters),
        structure_summary={"workspace_roots": roots_payload},
        workspace_roots=tuple(roots_payload),
    )


def _prefix_quality_files(files: tuple[FileQuality, ...], *, root: WorkspaceRoot) -> tuple[FileQuality, ...]:
    return tuple(replace(file, path=f"{root.id}/{file.path}", module=f"{root.id}.{file.module}") for file in files)


def _prefix_quality_findings(findings: tuple[QualityFinding, ...], *, root: WorkspaceRoot) -> tuple[QualityFinding, ...]:
    out: list[QualityFinding] = []
    for finding in findings:
        location = dict(finding.source_location)
        raw_path = str(location.get("path", "")).strip()
        source_path = str((root.path / raw_path).resolve()) if raw_path and not Path(raw_path).is_absolute() else (raw_path or str(root.path))
        location["path"] = f"{root.id}/{raw_path}" if raw_path else raw_path
        object_id = finding.object_id
        if finding.object_type in {"file", "function"} and not object_id.startswith(f"{root.id}/"):
            object_id = f"{root.id}/{object_id}"
        out.append(replace(finding, object_id=object_id, source_location=location, root_id=root.id, root_path=str(root.path), source_path=source_path))
    return tuple(out)


def _structure_limits_for_root(
    limits: QualityStructureLimits,
    *,
    overrides: Mapping[str, object] | None,
    enabled: bool | None,
) -> QualityStructureLimits:
    values = {}
    if overrides:
        values.update(overrides)
    if enabled is not None:
        values["enabled"] = enabled
    return replace(limits, **values) if values else limits


def _prefix_dependency_graph(graph: Mapping[str, Any], *, root: WorkspaceRoot) -> dict[str, tuple[str, ...]]:
    return {f"{root.id}.{source}": tuple(f"{root.id}.{target}" for target in targets) for source, targets in graph.items()}


def _prefix_directories(values: tuple[DirectoryQuality, ...], *, root: WorkspaceRoot) -> tuple[DirectoryQuality, ...]:
    return tuple(replace(item, directory=f"{root.id}/{item.directory}") for item in values)


def _prefix_clusters(values: tuple[PrefixClusterQuality, ...], *, root: WorkspaceRoot) -> tuple[PrefixClusterQuality, ...]:
    return tuple(
        replace(
            item,
            cluster_name=f"{root.id}/{item.cluster_name}",
            directory=f"{root.id}/{item.directory}",
            files=tuple(f"{root.id}/{path}" for path in item.files),
            modules=tuple(f"{root.id}.{module}" for module in item.modules),
            public_entry_candidates=tuple(f"{root.id}.{module}" for module in item.public_entry_candidates),
            internal_dependency_edges=tuple((f"{root.id}.{source}", f"{root.id}.{target}") for source, target in item.internal_dependency_edges),
            external_incoming_modules=tuple(f"{root.id}.{module}" for module in item.external_incoming_modules),
        )
        for item in values
    )
