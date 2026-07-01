from __future__ import annotations

from pathlib import PurePosixPath
from typing import Mapping, Sequence

from .code_quality_types import FileQuality, PrefixClusterQuality, QualityFinding, QualityThresholds


def dependency_distance_summary(
    module_directories: Mapping[str, str],
    dependency_graph: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    distances = [
        path_distance(module_directories[source], module_directories[target])
        for source, targets in dependency_graph.items()
        for target in targets
        if source in module_directories and target in module_directories
    ]
    return {
        "edge_count": len(distances),
        "max_distance": max(distances, default=0),
        "far_edge_count": sum(distance >= 3 for distance in distances),
    }


def dependency_distance_findings(
    clusters: tuple[PrefixClusterQuality, ...],
    files: Sequence[FileQuality],
    dependency_graph: Mapping[str, Sequence[str]],
    thresholds: QualityThresholds,
) -> list[QualityFinding]:
    files_by_module = {file.module: file for file in files}
    module_clusters = {module: cluster for cluster in clusters for module in cluster.modules}
    findings = []
    for source, targets in dependency_graph.items():
        if _is_distance_exempt_source(source):
            continue
        far_directories: set[str] = set()
        for target in targets:
            if source not in files_by_module or target not in files_by_module:
                continue
            distance = module_path_distance(files_by_module[source], files_by_module[target])
            if distance <= thresholds.max_dependency_distance:
                continue
            target_directory = directory_for_path(files_by_module[target].path)
            far_directories.add(target_directory)
            if is_internal_module(files_by_module[target].path):
                findings.append(_distant_internal_import_finding(source, target, distance, module_clusters.get(target)))
        if len(far_directories) > thresholds.max_scattered_dependency_directories:
            findings.append(_scattered_dependency_finding(source, far_directories))
    return findings


def directory_for_path(path: str) -> str:
    parent = PurePosixPath(path).parent
    if parent == PurePosixPath("."):
        return "."
    return parent.as_posix()


def is_internal_module(path: str) -> bool:
    stem = PurePosixPath(path).stem
    if stem == "__init__":
        return False
    return stem.startswith("_") or stem.endswith(("_helpers", "_rules", "_visitors", "_validators"))


def module_path_distance(source: FileQuality, target: FileQuality) -> int:
    return path_distance(directory_for_path(source.path), directory_for_path(target.path))


def path_distance(source_directory: str, target_directory: str) -> int:
    source_parts = _directory_parts(source_directory)
    target_parts = _directory_parts(target_directory)
    common = 0
    for left, right in zip(source_parts, target_parts):
        if left != right:
            break
        common += 1
    return (len(source_parts) - common) + (len(target_parts) - common)


def _distant_internal_import_finding(
    source: str,
    target: str,
    distance: int,
    cluster: PrefixClusterQuality | None,
) -> QualityFinding:
    details: dict[str, object] = {"source": source, "target": target, "distance": distance}
    if cluster is not None:
        details["cluster_name"] = cluster.cluster_name
        details["public_entry_candidates"] = cluster.public_entry_candidates
        details["suggestion"] = "import through a public entry candidate or move the caller closer to the cluster"
    else:
        details["suggestion"] = "move the dependency behind a closer public boundary or relocate tightly coupled files"
    return QualityFinding(
        rule_id="QUALITY.STRUCTURE.DISTANT_INTERNAL_IMPORT",
        severity="warning",
        object_type="dependency_pair",
        object_id=f"{source} -> {target}",
        message=f"module imports distant internal module at path distance {distance}",
        suggested_fix_type="use_nearer_or_public_boundary",
        details=details,
    )


def _scattered_dependency_finding(source: str, far_directories: set[str]) -> QualityFinding:
    return QualityFinding(
        rule_id="QUALITY.STRUCTURE.CLUSTER_SCATTERED_DEPENDENCY",
        severity="warning",
        object_type="module",
        object_id=source,
        message=f"module depends on {len(far_directories)} distant directories",
        suggested_fix_type="clarify_structure",
        details={
            "source": source,
            "far_directories": tuple(sorted(far_directories)),
            "suggestion": "group related dependencies behind a local facade or split this module by dependency area",
        },
    )


def _is_distance_exempt_source(module: str) -> bool:
    leaf = module.rsplit(".", 1)[-1]
    return leaf in {"runtime", "runner", "health", "cli", "cli_reports", "cli_config", "cli_node"}


def _directory_parts(directory: str) -> tuple[str, ...]:
    if directory == ".":
        return ()
    return tuple(part for part in PurePosixPath(directory).parts if part)
