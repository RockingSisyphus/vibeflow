from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from .code_quality_structure_distance import (
    dependency_distance_findings,
    dependency_distance_summary,
    directory_for_path,
    is_internal_module,
)
from .code_quality_types import DirectoryQuality, FileQuality, PrefixClusterQuality, QualityFinding, QualityThresholds


def analyze_directory_structure(
    files: Sequence[FileQuality],
    dependency_graph: Mapping[str, Sequence[str]],
    thresholds: QualityThresholds,
) -> tuple[tuple[DirectoryQuality, ...], tuple[PrefixClusterQuality, ...], dict[str, object], list[QualityFinding]]:
    module_directories = {file.module: directory_for_path(file.path) for file in files}
    directories = _directory_reports(module_directories, dependency_graph)
    clusters = _prefix_clusters(files, dependency_graph)
    distance_summary = dependency_distance_summary(module_directories, dependency_graph)
    summary = _structure_summary(directories, clusters, distance_summary)
    findings = [
        *_directory_findings(directories, thresholds),
        *_prefix_cluster_findings(clusters, thresholds),
        *_public_boundary_findings(clusters, files, dependency_graph, thresholds),
        *dependency_distance_findings(clusters, files, dependency_graph, thresholds),
    ]
    return directories, clusters, summary, findings


def _directory_reports(
    module_directories: Mapping[str, str],
    dependency_graph: Mapping[str, Sequence[str]],
) -> tuple[DirectoryQuality, ...]:
    modules_by_directory: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    internal_imports: dict[str, int] = defaultdict(int)
    external_imports: dict[str, int] = defaultdict(int)

    for module, directory in module_directories.items():
        modules_by_directory[directory].add(module)
        for target in dependency_graph.get(module, ()):
            target_directory = module_directories.get(target)
            if target_directory is None:
                continue
            if target_directory == directory:
                internal_imports[directory] += 1
            else:
                external_imports[directory] += 1
                outgoing[directory].add(target_directory)
                incoming[target_directory].add(directory)

    reports = []
    for directory in sorted(modules_by_directory):
        reports.append(
            DirectoryQuality(
                directory=directory,
                module_count=len(modules_by_directory[directory]),
                internal_import_count=internal_imports[directory],
                external_import_count=external_imports[directory],
                outgoing_directories=tuple(sorted(outgoing[directory])),
                incoming_directories=tuple(sorted(incoming[directory])),
            )
        )
    return tuple(reports)


def _prefix_clusters(
    files: Sequence[FileQuality],
    dependency_graph: Mapping[str, Sequence[str]],
) -> tuple[PrefixClusterQuality, ...]:
    files_by_module = {file.module: file for file in files}
    prefix_groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for file in files:
        stem = PurePosixPath(file.path).stem
        if stem == "__init__":
            continue
        directory = directory_for_path(file.path)
        for prefix in _candidate_prefixes(stem):
            prefix_groups[(directory, prefix)].add(file.module)

    selected = _select_prefix_groups(prefix_groups)
    clusters = []
    for directory, prefix, modules in selected:
        module_set = set(modules)
        cluster_files = tuple(sorted(files_by_module[module].path for module in modules))
        internal_edges = tuple(
            sorted(
                (source, target)
                for source in modules
                for target in dependency_graph.get(source, ())
                if target in module_set
            )
        )
        external_incoming = tuple(
            sorted(
                source
                for source, targets in dependency_graph.items()
                if source not in module_set and any(target in module_set for target in targets)
            )
        )
        public_entries = tuple(
            sorted(
                module
                for module in modules
                if _is_public_entry_candidate(files_by_module[module].path, prefix)
            )
        )
        clusters.append(
            PrefixClusterQuality(
                cluster_name=_cluster_name(directory, prefix),
                directory=directory,
                prefix=prefix,
                files=cluster_files,
                modules=tuple(modules),
                public_entry_candidates=public_entries,
                internal_dependency_edges=internal_edges,
                external_incoming_modules=external_incoming,
            )
        )
    return tuple(sorted(clusters, key=lambda cluster: cluster.cluster_name))


def _structure_summary(
    directories: tuple[DirectoryQuality, ...],
    clusters: tuple[PrefixClusterQuality, ...],
    distance_summary: Mapping[str, object],
) -> dict[str, object]:
    cross_directory_dependencies = sum(len(directory.outgoing_directories) for directory in directories)
    most_connected = sorted(
        directories,
        key=lambda directory: (
            len(directory.incoming_directories) + len(directory.outgoing_directories),
            directory.external_import_count,
            directory.directory,
        ),
        reverse=True,
    )[:5]
    return {
        "directory_count": len(directories),
        "cross_directory_dependencies": cross_directory_dependencies,
        "prefix_cluster_count": len(clusters),
        "dependency_distance": dict(distance_summary),
        "most_connected_directories": [
            {
                "directory": directory.directory,
                "fanin": len(directory.incoming_directories),
                "fanout": len(directory.outgoing_directories),
                "external_import_count": directory.external_import_count,
            }
            for directory in most_connected
        ],
        "largest_prefix_clusters": [
            {
                "cluster_name": cluster.cluster_name,
                "file_count": len(cluster.files),
                "public_entry_candidates": list(cluster.public_entry_candidates),
            }
            for cluster in sorted(clusters, key=lambda item: (len(item.files), item.cluster_name), reverse=True)[:5]
        ],
    }


def _directory_findings(
    directories: tuple[DirectoryQuality, ...],
    thresholds: QualityThresholds,
) -> list[QualityFinding]:
    findings = []
    for directory in directories:
        fanout = len(directory.outgoing_directories)
        fanin = len(directory.incoming_directories)
        if fanout > thresholds.max_directory_fanout:
            findings.append(
                _structure_finding(
                    "QUALITY.STRUCTURE.DIRECTORY_FANOUT",
                    directory,
                    f"directory depends on {fanout} other directories",
                    {"fanout": fanout, "outgoing_directories": directory.outgoing_directories},
                )
            )
        if fanin > thresholds.max_directory_fanin:
            findings.append(
                _structure_finding(
                    "QUALITY.STRUCTURE.DIRECTORY_FANIN",
                    directory,
                    f"directory is depended on by {fanin} other directories",
                    {"fanin": fanin, "incoming_directories": directory.incoming_directories},
                )
            )
    return findings


def _prefix_cluster_findings(
    clusters: tuple[PrefixClusterQuality, ...],
    thresholds: QualityThresholds,
) -> list[QualityFinding]:
    findings = []
    for cluster in clusters:
        file_count = len(cluster.files)
        if file_count > thresholds.max_prefix_cluster_files:
            findings.append(
                QualityFinding(
                    rule_id="QUALITY.STRUCTURE.PREFIX_CLUSTER_SHOULD_BE_PACKAGE",
                    severity="warning",
                    object_type="prefix_cluster",
                    object_id=cluster.cluster_name,
                    message=f"prefix cluster has {file_count} files and may deserve a package",
                    suggested_fix_type="extract_package",
                    details={
                        "cluster_name": cluster.cluster_name,
                        "files": cluster.files,
                        "public_entry_candidates": cluster.public_entry_candidates,
                        "suggested_package_dir": _suggested_package_dir(cluster),
                        "suggested_layout": _suggested_package_layout(cluster),
                        "import_update_candidates": cluster.external_incoming_modules,
                    },
                )
            )
    return findings


def _public_boundary_findings(
    clusters: tuple[PrefixClusterQuality, ...],
    files: Sequence[FileQuality],
    dependency_graph: Mapping[str, Sequence[str]],
    thresholds: QualityThresholds,
) -> list[QualityFinding]:
    files_by_module = {file.module: file for file in files}
    module_clusters = {
        module: cluster
        for cluster in clusters
        for module in cluster.modules
    }
    findings = []
    for source, targets in dependency_graph.items():
        if source.startswith("tests"):
            continue
        targets_by_cluster: dict[str, list[str]] = defaultdict(list)
        for target in targets:
            cluster = module_clusters.get(target)
            if cluster is None or source in cluster.modules:
                continue
            if is_internal_module(files_by_module[target].path):
                findings.append(_internal_module_imported_finding(source, target, cluster))
                targets_by_cluster[cluster.cluster_name].append(target)
        findings.extend(
            _public_entry_bypass_findings(
                source,
                targets_by_cluster,
                {cluster.cluster_name: cluster for cluster in clusters},
                thresholds,
            )
        )
    return findings


def _internal_module_imported_finding(
    source: str,
    target: str,
    cluster: PrefixClusterQuality,
) -> QualityFinding:
    return QualityFinding(
        rule_id="QUALITY.STRUCTURE.INTERNAL_MODULE_IMPORTED_EXTERNALLY",
        severity="warning",
        object_type="dependency_pair",
        object_id=f"{source} -> {target}",
        message="external module imports a cluster internal module directly",
        suggested_fix_type="use_public_entry",
        details={
            "source": source,
            "target": target,
            "cluster_name": cluster.cluster_name,
            "public_entry_candidates": cluster.public_entry_candidates,
        },
    )


def _public_entry_bypass_findings(
    source: str,
    targets_by_cluster: Mapping[str, list[str]],
    clusters_by_name: Mapping[str, PrefixClusterQuality],
    thresholds: QualityThresholds,
) -> list[QualityFinding]:
    findings = []
    for cluster_name, targets in targets_by_cluster.items():
        cluster = clusters_by_name[cluster_name]
        if not cluster.public_entry_candidates or len(targets) <= thresholds.max_public_entry_bypass_imports:
            continue
        findings.append(
            QualityFinding(
                rule_id="QUALITY.STRUCTURE.PUBLIC_ENTRY_BYPASSED",
                severity="warning",
                object_type="dependency_cluster",
                object_id=f"{source} -> {cluster_name}",
                message=f"module imports {len(targets)} internal modules from one cluster",
                suggested_fix_type="use_public_entry",
                details={
                    "source": source,
                    "cluster_name": cluster_name,
                    "targets": tuple(sorted(targets)),
                    "public_entry_candidates": cluster.public_entry_candidates,
                },
            )
        )
    return findings


def _candidate_prefixes(stem: str) -> tuple[str, ...]:
    parts = stem.split("_")
    if len(parts) == 1:
        return (stem,)
    prefixes = ["_".join(parts[:index]) for index in range(1, len(parts))]
    prefixes.append(stem)
    return tuple(prefixes)


def _select_prefix_groups(
    prefix_groups: Mapping[tuple[str, str], set[str]],
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    selected: list[tuple[str, str, tuple[str, ...]]] = []
    claimed_modules: set[str] = set()
    candidates = sorted(
        (
            (directory, prefix, tuple(sorted(modules)))
            for (directory, prefix), modules in prefix_groups.items()
            if len(modules) >= 2
        ),
        key=lambda item: (len(item[2]), len(item[1]), item[0], item[1]),
        reverse=True,
    )
    for directory, prefix, modules in candidates:
        if any(module in claimed_modules for module in modules):
            continue
        selected.append((directory, prefix, modules))
        claimed_modules.update(modules)
    return tuple(sorted(selected, key=lambda item: _cluster_name(item[0], item[1])))


def _is_public_entry_candidate(path: str, prefix: str) -> bool:
    stem = PurePosixPath(path).stem
    return stem in {prefix, "__init__", "api", "types"} or stem.endswith("_types")


def _cluster_name(directory: str, prefix: str) -> str:
    return prefix if directory == "." else f"{directory}/{prefix}"


def _suggested_package_dir(cluster: PrefixClusterQuality) -> str:
    return cluster.prefix if cluster.directory == "." else f"{cluster.directory}/{cluster.prefix}"


def _suggested_package_layout(cluster: PrefixClusterQuality) -> tuple[str, ...]:
    package_dir = _suggested_package_dir(cluster)
    entries = {f"{package_dir}/__init__.py"}
    for path in cluster.files:
        stem = PurePosixPath(path).stem
        if stem == cluster.prefix:
            continue
        if stem.startswith(f"{cluster.prefix}_"):
            entries.add(f"{package_dir}/{stem.removeprefix(cluster.prefix + '_')}.py")
        else:
            entries.add(f"{package_dir}/{stem}.py")
    return tuple(sorted(entries))


def _structure_finding(
    rule_id: str,
    directory: DirectoryQuality,
    message: str,
    details: Mapping[str, object],
) -> QualityFinding:
    return QualityFinding(
        rule_id=rule_id,
        severity="warning",
        object_type="directory",
        object_id=directory.directory,
        message=message,
        suggested_fix_type="clarify_structure",
        details={"directory": directory.directory, **_structure_suggestion(rule_id), **details},
    )


def _structure_suggestion(rule_id: str) -> dict[str, object]:
    if rule_id == "QUALITY.STRUCTURE.DIRECTORY_FANIN":
        return {
            "suggestion": "consider adding or clarifying a public API module for this directory",
            "suggested_entry_files": ("__init__.py", "api.py"),
        }
    if rule_id == "QUALITY.STRUCTURE.DIRECTORY_FANOUT":
        return {
            "suggestion": "consider splitting coordinator responsibilities or moving tightly coupled files closer together",
        }
    return {}
