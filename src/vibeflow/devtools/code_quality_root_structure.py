from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from .code_quality_structure_distance import directory_for_path
from .code_quality_types import FileQuality, ImportSite, QualityFinding, QualityStructureLimits


_ROOT_DIR = "(root)"
_NODE_ROLES = frozenset({"nodes", "task_nodes"})
_BASE_LIB_ROLE = "base_lib"
_PLUGIN_ROLE = "plugins"


def analyze_root_structure(
    files: Sequence[FileQuality],
    dependency_graph: Mapping[str, Sequence[str]],
    import_sites_by_edge: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
    limits: QualityStructureLimits | None,
) -> tuple[dict[str, object], tuple[QualityFinding, ...]]:
    if limits is None or not limits.enabled:
        return {}, ()
    stats = _root_stats(files)
    findings = [
        *_root_count_findings(stats, limits),
        *_directory_file_count_findings(stats, limits),
        *_directory_depth_findings(stats, limits),
        *_child_directory_findings(stats, limits),
        *_root_level_file_findings(stats, limits),
    ]
    if limits.enforce_role_imports:
        findings.extend(_role_import_findings(files, dependency_graph, import_sites_by_edge))
    return _summary(stats, limits), tuple(findings)


def _root_stats(files: Sequence[FileQuality]) -> dict[str, object]:
    direct_files: Counter[str] = Counter()
    directory_depths: dict[str, int] = {}
    child_code_dirs: dict[str, set[str]] = defaultdict(set)
    root_level_files: list[str] = []
    code_dirs: set[str] = set()
    files_by_dir: dict[str, list[str]] = defaultdict(list)

    for file in files:
        path = PurePosixPath(file.path)
        parent = _directory(path)
        direct_files[parent] += 1
        files_by_dir[parent].append(file.path)
        if parent == _ROOT_DIR:
            root_level_files.append(file.path)
            directory_depths[parent] = 0
            continue
        code_dirs.add(parent)
        parts = path.parent.parts
        directory_depths[parent] = max(directory_depths.get(parent, 0), len(parts))
        for index, part in enumerate(parts):
            base = "/".join(parts[:index]) if index else _ROOT_DIR
            child_code_dirs[base].add(part)

    return {
        "code_file_count": len(files),
        "code_dir_count": len(code_dirs),
        "direct_files": direct_files,
        "directory_depths": directory_depths,
        "child_code_dirs": child_code_dirs,
        "root_level_files": tuple(sorted(root_level_files)),
        "files_by_dir": {directory: tuple(sorted(values)) for directory, values in files_by_dir.items()},
    }


def _root_count_findings(stats: Mapping[str, object], limits: QualityStructureLimits) -> list[QualityFinding]:
    return [
        *filter(
            None,
            (
                _threshold_finding(
                    "QUALITY.STRUCTURE.ROOT_TOO_MANY_CODE_FILES",
                    "root",
                    "root",
                    int(stats["code_file_count"]),
                    limits.warn_root_code_files,
                    limits.max_root_code_files,
                    "root has {actual} Python code files",
                    {"code_file_count": stats["code_file_count"]},
                ),
                _threshold_finding(
                    "QUALITY.STRUCTURE.ROOT_TOO_MANY_CODE_DIRS",
                    "root",
                    "root",
                    int(stats["code_dir_count"]),
                    limits.warn_code_dirs,
                    limits.max_code_dirs,
                    "root has {actual} code directories",
                    {"code_dir_count": stats["code_dir_count"]},
                ),
            ),
        )
    ]


def _directory_file_count_findings(stats: Mapping[str, object], limits: QualityStructureLimits) -> list[QualityFinding]:
    direct_files = stats["direct_files"]
    files_by_dir = stats["files_by_dir"]
    assert isinstance(direct_files, Counter)
    assert isinstance(files_by_dir, dict)
    findings: list[QualityFinding] = []
    for directory, count in sorted(direct_files.items()):
        finding = _threshold_finding(
            "QUALITY.STRUCTURE.DIRECTORY_TOO_MANY_CODE_FILES",
            "directory",
            directory,
            count,
            limits.warn_code_files_per_dir,
            limits.max_code_files_per_dir,
            "directory has {actual} Python code files",
            {"directory": directory, "files": files_by_dir.get(directory, ())},
            source_path=_first_path(files_by_dir.get(directory, ())),
        )
        if finding:
            findings.append(finding)
    return findings


def _directory_depth_findings(stats: Mapping[str, object], limits: QualityStructureLimits) -> list[QualityFinding]:
    depths = stats["directory_depths"]
    files_by_dir = stats["files_by_dir"]
    assert isinstance(depths, dict)
    assert isinstance(files_by_dir, dict)
    findings: list[QualityFinding] = []
    for directory, depth in sorted(depths.items()):
        if directory == _ROOT_DIR:
            continue
        finding = _threshold_finding(
            "QUALITY.STRUCTURE.DIRECTORY_TOO_DEEP",
            "directory",
            directory,
            int(depth),
            limits.warn_code_dir_depth,
            limits.max_code_dir_depth,
            "directory depth is {actual}",
            {"directory": directory, "depth": depth},
            source_path=_first_path(files_by_dir.get(directory, ())),
        )
        if finding:
            findings.append(finding)
    return findings


def _child_directory_findings(stats: Mapping[str, object], limits: QualityStructureLimits) -> list[QualityFinding]:
    child_dirs = stats["child_code_dirs"]
    assert isinstance(child_dirs, defaultdict)
    findings: list[QualityFinding] = []
    for directory, children in sorted(child_dirs.items()):
        finding = _threshold_finding(
            "QUALITY.STRUCTURE.DIRECTORY_TOO_MANY_CHILD_CODE_DIRS",
            "directory",
            directory,
            len(children),
            limits.warn_child_code_dirs_per_dir,
            limits.max_child_code_dirs_per_dir,
            "directory has {actual} direct child code directories",
            {"directory": directory, "child_code_dirs": tuple(sorted(children))},
        )
        if finding:
            findings.append(finding)
    return findings


def _root_level_file_findings(stats: Mapping[str, object], limits: QualityStructureLimits) -> list[QualityFinding]:
    root_files = tuple(path for path in stats["root_level_files"] if PurePosixPath(path).name not in limits.allowed_root_code_files)
    finding = _threshold_finding(
        "QUALITY.STRUCTURE.ROOT_LEVEL_CODE_FILE",
        "root",
        "root",
        len(root_files),
        limits.warn_root_level_code_files,
        limits.max_root_level_code_files,
        "root has {actual} non-allowlisted top-level Python files",
        {"files": root_files, "allowed_root_code_files": limits.allowed_root_code_files},
        source_path=_first_path(root_files),
    )
    return [finding] if finding else []


def _role_import_findings(
    files: Sequence[FileQuality],
    dependency_graph: Mapping[str, Sequence[str]],
    import_sites_by_edge: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
) -> list[QualityFinding]:
    files_by_module = {file.module: file for file in files}
    findings: list[QualityFinding] = []
    for source, targets in sorted(dependency_graph.items()):
        source_file = files_by_module.get(source)
        if source_file is None:
            continue
        source_role = _role_for_path(source_file.path)
        for target in sorted(targets):
            target_file = files_by_module.get(target)
            if target_file is None:
                continue
            finding = _role_import_finding(source, target, source_role, _role_for_path(target_file.path), import_sites_by_edge)
            if finding:
                findings.append(finding)
    return findings


def _role_import_finding(source: str, target: str, source_role: str, target_role: str, import_sites_by_edge) -> QualityFinding | None:
    if source_role == _BASE_LIB_ROLE and target_role != _BASE_LIB_ROLE:
        return _import_finding("QUALITY.STRUCTURE.BASE_LIB_UPWARD_IMPORT", source, target, "base_lib module imports a project layer module", import_sites_by_edge)
    if _is_node_role(source_role) and target_role != _BASE_LIB_ROLE:
        return _import_finding("QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT", source, target, "node module imports project code outside declared base_lib", import_sites_by_edge)
    if source_role == _PLUGIN_ROLE and _is_node_role(target_role):
        return _import_finding("QUALITY.STRUCTURE.PLUGIN_NODE_IMPORT", source, target, "plugin module imports node code", import_sites_by_edge)
    return None


def _import_finding(rule_id: str, source: str, target: str, message: str, import_sites_by_edge) -> QualityFinding:
    sites = tuple(import_sites_by_edge.get((source, target), ()))
    return QualityFinding(
        rule_id=rule_id,
        severity="error",
        object_type="module_dependency",
        object_id=f"{source} -> {target}",
        source_location=_first_site_location(sites),
        message=f"{message}: {source} -> {target}",
        suggested_fix_type="clarify_structure",
        details={"source": source, "target": target, "import_sites": sites},
    )


def _threshold_finding(
    rule_id: str,
    object_type: str,
    object_id: str,
    actual: int,
    warn: int,
    max_: int,
    message_template: str,
    details: Mapping[str, object],
    *,
    source_path: str = "",
) -> QualityFinding | None:
    if actual > max_:
        severity = "error"
        limit_kind = "max"
        limit = max_
    elif actual >= warn:
        severity = "warning"
        limit_kind = "warn"
        limit = warn
    else:
        return None
    return QualityFinding(
        rule_id=rule_id,
        severity=severity,
        object_type=object_type,
        object_id=object_id,
        source_location={"path": source_path} if source_path else {},
        message=message_template.format(actual=actual),
        suggested_fix_type="clarify_structure",
        details={"actual": actual, "limit": limit, "limit_kind": limit_kind, **details},
    )


def _summary(stats: Mapping[str, object], limits: QualityStructureLimits) -> dict[str, object]:
    direct_files = stats["direct_files"]
    depths = stats["directory_depths"]
    child_dirs = stats["child_code_dirs"]
    assert isinstance(direct_files, Counter)
    assert isinstance(depths, dict)
    assert isinstance(child_dirs, defaultdict)
    return {
        "root_layout": {
            "code_files": stats["code_file_count"],
            "code_dirs": stats["code_dir_count"],
            "max_code_dir_depth": max((int(value) for value in depths.values()), default=0),
            "max_code_files_per_dir": max(direct_files.values(), default=0),
            "max_child_code_dirs_per_dir": max((len(values) for values in child_dirs.values()), default=0),
            "root_level_code_files": list(stats["root_level_files"]),
            "structure_limits": limits.to_dict(),
        }
    }


def _directory(path: PurePosixPath) -> str:
    directory = directory_for_path(str(path))
    return directory if directory and directory != "." else _ROOT_DIR


def _role_for_path(path: str) -> str:
    parts = PurePosixPath(path).parts
    return parts[0] if len(parts) > 1 else _ROOT_DIR


def _is_node_role(role: str) -> bool:
    return role in _NODE_ROLES or role.endswith("_nodes")


def _first_path(paths: Sequence[str]) -> str:
    return str(paths[0]) if paths else ""


def _first_site_location(sites: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    if not sites:
        return {}
    site = sites[0]
    return {"path": site.get("path", ""), "line": site.get("line", 1), "column": site.get("column", 1)}
