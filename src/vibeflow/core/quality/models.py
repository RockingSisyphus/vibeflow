from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from vibeflow.core.findings import Finding


_UNSET = object()


@dataclass(frozen=True)
class QualityThresholds:
    max_file_lines: int = 500
    warn_file_lines: int = 450
    max_file_bytes: int = 60000
    max_functions_per_file: int = 40
    max_classes_per_file: int = 20
    max_public_api_per_file: int = 30
    max_file_branches: int = 150
    max_directory_fanout: int = 25
    max_directory_fanin: int = 25
    max_prefix_cluster_files: int = 12
    max_public_entry_bypass_imports: int = 3
    max_dependency_distance: int = 3
    max_scattered_dependency_directories: int = 6
    max_function_lines: int = 80
    max_function_branches: int = 12
    max_function_nesting: int = 4
    max_function_params: int = 6
    warn_dependency_chain: int = 6
    max_dependency_chain: int = 10

    def to_dict(self) -> dict[str, int]:
        return {
            "max_file_lines": self.max_file_lines,
            "warn_file_lines": self.warn_file_lines,
            "max_file_bytes": self.max_file_bytes,
            "max_functions_per_file": self.max_functions_per_file,
            "max_classes_per_file": self.max_classes_per_file,
            "max_public_api_per_file": self.max_public_api_per_file,
            "max_file_branches": self.max_file_branches,
            "max_directory_fanout": self.max_directory_fanout,
            "max_directory_fanin": self.max_directory_fanin,
            "max_prefix_cluster_files": self.max_prefix_cluster_files,
            "max_public_entry_bypass_imports": self.max_public_entry_bypass_imports,
            "max_dependency_distance": self.max_dependency_distance,
            "max_scattered_dependency_directories": self.max_scattered_dependency_directories,
            "max_function_lines": self.max_function_lines,
            "max_function_branches": self.max_function_branches,
            "max_function_nesting": self.max_function_nesting,
            "max_function_params": self.max_function_params,
            "warn_dependency_chain": self.warn_dependency_chain,
            "max_dependency_chain": self.max_dependency_chain,
        }


@dataclass(frozen=True)
class QualityStructureLimits:
    enabled: bool = True
    warn_root_code_files: int = 96
    max_root_code_files: int = 120
    warn_code_dirs: int = 18
    max_code_dirs: int = 24
    warn_code_files_per_dir: int = 12
    max_code_files_per_dir: int = 16
    warn_code_dir_depth: int = 3
    max_code_dir_depth: int = 4
    warn_child_code_dirs_per_dir: int = 6
    max_child_code_dirs_per_dir: int = 8
    warn_root_level_code_files: int = 1
    max_root_level_code_files: int = 2
    allowed_root_code_files: tuple[str, ...] = ("__init__.py", "registry.py")
    enforce_role_imports: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "warn_root_code_files": self.warn_root_code_files,
            "max_root_code_files": self.max_root_code_files,
            "warn_code_dirs": self.warn_code_dirs,
            "max_code_dirs": self.max_code_dirs,
            "warn_code_files_per_dir": self.warn_code_files_per_dir,
            "max_code_files_per_dir": self.max_code_files_per_dir,
            "warn_code_dir_depth": self.warn_code_dir_depth,
            "max_code_dir_depth": self.max_code_dir_depth,
            "warn_child_code_dirs_per_dir": self.warn_child_code_dirs_per_dir,
            "max_child_code_dirs_per_dir": self.max_child_code_dirs_per_dir,
            "warn_root_level_code_files": self.warn_root_level_code_files,
            "max_root_level_code_files": self.max_root_level_code_files,
            "allowed_root_code_files": list(self.allowed_root_code_files),
            "enforce_role_imports": self.enforce_role_imports,
        }


@dataclass(frozen=True)
class QualityStructureRoles:
    base_lib_paths: tuple[str, ...] = ("base_lib",)
    base_lib_modules: tuple[str, ...] = ()


@dataclass(frozen=True, init=False)
class QualityFinding(Finding):
    """Source-quality view of the shared :class:`~vibeflow.core.Finding`."""

    def __init__(
        self,
        rule_id: str | object = _UNSET,
        severity: str = "",
        object_type: str | object = _UNSET,
        object_id: str | object = _UNSET,
        message: str = "",
        source_location: Mapping[str, object] | None = None,
        suggested_fix_type: str | object = _UNSET,
        details: Mapping[str, object] | None = None,
        root_id: str = "",
        root_path: str = "",
        source_path: str = "",
        *,
        code: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        suggested_fix: str | None = None,
    ) -> None:
        resolved_code = code if rule_id is _UNSET else str(rule_id)
        if resolved_code is None:
            raise TypeError("rule_id is required")
        resolved_type = subject_type if object_type is _UNSET else str(object_type)
        resolved_id = subject_id if object_id is _UNSET else str(object_id)
        resolved_fix = (
            suggested_fix
            if suggested_fix_type is _UNSET
            else str(suggested_fix_type)
        )
        object.__setattr__(self, "code", resolved_code)
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "subject_type", resolved_type or "")
        object.__setattr__(self, "subject_id", resolved_id or "")
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "source_location", source_location or {})
        object.__setattr__(self, "suggested_fix", resolved_fix or "refactor")
        object.__setattr__(self, "details", details or {})
        object.__setattr__(self, "root_id", root_id)
        object.__setattr__(self, "root_path", root_path)
        object.__setattr__(self, "source_path", source_path)

    def to_dict(self) -> dict[str, object]:
        return self.common_dict()


@dataclass(frozen=True)
class FunctionQuality:
    qualname: str
    line_start: int
    line_end: int
    lines: int
    branches: int
    max_nesting_depth: int
    param_count: int
    ast_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        return {
            "qualname": self.qualname,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "lines": self.lines,
            "branches": self.branches,
            "max_nesting_depth": self.max_nesting_depth,
            "param_count": self.param_count,
            "ast_fingerprint": self.ast_fingerprint,
        }


@dataclass(frozen=True)
class ImportSite:
    source_module: str
    imported: str
    raw_import: str
    path: str
    line: int
    column: int

    def to_dict(self) -> dict[str, object]:
        return {
            "source_module": self.source_module,
            "imported": self.imported,
            "raw_import": self.raw_import,
            "path": self.path,
            "line": self.line,
            "column": self.column,
        }


@dataclass(frozen=True)
class FileQuality:
    path: str
    module: str
    lines: int
    bytes: int
    function_count: int
    class_count: int
    public_api_count: int
    branch_count: int
    max_nesting_depth: int
    imports: tuple[str, ...]
    functions: tuple[FunctionQuality, ...]
    import_sites: tuple[ImportSite, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "module": self.module,
            "lines": self.lines,
            "bytes": self.bytes,
            "function_count": self.function_count,
            "class_count": self.class_count,
            "public_api_count": self.public_api_count,
            "branch_count": self.branch_count,
            "max_nesting_depth": self.max_nesting_depth,
            "imports": list(self.imports),
            "import_sites": [site.to_dict() for site in self.import_sites],
            "functions": [function.to_dict() for function in self.functions],
        }


@dataclass(frozen=True)
class DirectoryQuality:
    directory: str
    module_count: int
    internal_import_count: int
    external_import_count: int
    outgoing_directories: tuple[str, ...]
    incoming_directories: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "directory": self.directory,
            "module_count": self.module_count,
            "internal_import_count": self.internal_import_count,
            "external_import_count": self.external_import_count,
            "outgoing_directories": list(self.outgoing_directories),
            "incoming_directories": list(self.incoming_directories),
        }


@dataclass(frozen=True)
class PrefixClusterQuality:
    cluster_name: str
    directory: str
    prefix: str
    files: tuple[str, ...]
    modules: tuple[str, ...]
    public_entry_candidates: tuple[str, ...]
    internal_dependency_edges: tuple[tuple[str, str], ...]
    external_incoming_modules: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "cluster_name": self.cluster_name,
            "directory": self.directory,
            "prefix": self.prefix,
            "files": list(self.files),
            "modules": list(self.modules),
            "public_entry_candidates": list(self.public_entry_candidates),
            "internal_dependency_edges": [list(edge) for edge in self.internal_dependency_edges],
            "external_incoming_modules": list(self.external_incoming_modules),
        }


@dataclass(frozen=True)
class ProjectQualityFacts:
    """Target-extracted facts consumed by the pure Core quality evaluator."""

    root: str
    files: tuple[FileQuality, ...] = ()
    findings: tuple[QualityFinding, ...] = ()


@dataclass(frozen=True)
class QualityPolicy:
    """All target-neutral policy needed to evaluate project facts."""

    thresholds: QualityThresholds = field(default_factory=QualityThresholds)
    structure_limits: QualityStructureLimits | None = None
    structure_roles: QualityStructureRoles = field(default_factory=QualityStructureRoles)


@dataclass(frozen=True)
class QualityReport:
    status: str
    root: str
    thresholds: QualityThresholds
    files: tuple[FileQuality, ...]
    dependency_graph: Mapping[str, Sequence[str]]
    longest_dependency_chain: tuple[str, ...]
    findings: tuple[QualityFinding, ...]
    directory_graph: tuple[DirectoryQuality, ...] = ()
    prefix_clusters: tuple[PrefixClusterQuality, ...] = ()
    structure_summary: Mapping[str, object] = field(default_factory=dict)
    workspace_roots: tuple[Mapping[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        errors = [finding.to_dict() for finding in self.findings if finding.severity == "error"]
        warnings = [finding.to_dict() for finding in self.findings if finding.severity == "warning"]
        payload = {
            "status": self.status,
            "root": self.root,
            "summary": {
                "files": len(self.files),
                "errors": len(errors),
                "warnings": len(warnings),
                "score": _quality_score(errors, warnings),
                "longest_dependency_chain_length": len(self.longest_dependency_chain),
            },
            "scope_summary": _scope_summary(self.files, self.findings),
            "top_offenders": _top_offenders(self.files, self.findings),
            "thresholds": self.thresholds.to_dict(),
            "files": [file.to_dict() for file in self.files],
            "dependency_graph": {key: list(value) for key, value in sorted(self.dependency_graph.items())},
            "directory_graph": [directory.to_dict() for directory in self.directory_graph],
            "prefix_clusters": [cluster.to_dict() for cluster in self.prefix_clusters],
            "structure_summary": dict(self.structure_summary),
            "longest_dependency_chain": list(self.longest_dependency_chain),
            "errors": errors,
            "warnings": warnings,
        }
        if self.workspace_roots:
            payload["workspace_roots"] = [dict(root) for root in self.workspace_roots]
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=False)


# The descriptive name is used by the new Core API.  The historical name stays
# available so CLI JSON and callers do not need a migration merely because the
# implementation moved between layers.
SourceQualityReport = QualityReport


def _scope_summary(files: tuple[FileQuality, ...], findings: tuple[QualityFinding, ...]) -> dict[str, dict[str, int]]:
    summary = {
        "src": {"files": 0, "errors": 0, "warnings": 0},
        "tests": {"files": 0, "errors": 0, "warnings": 0},
        "devtools": {"files": 0, "errors": 0, "warnings": 0},
        "other": {"files": 0, "errors": 0, "warnings": 0},
    }
    for file in files:
        summary[_scope_for_text(file.path)]["files"] += 1
    for finding in findings:
        scope = _scope_for_finding(finding)
        if finding.severity == "error":
            summary[scope]["errors"] += 1
        elif finding.severity == "warning":
            summary[scope]["warnings"] += 1
    return summary


def _quality_score(errors: list[dict[str, object]], warnings: list[dict[str, object]]) -> int:
    return max(0, 100 - len(errors) * 10 - len(warnings) * 2)


def _top_offenders(files: tuple[FileQuality, ...], findings: tuple[QualityFinding, ...]) -> dict[str, list[dict[str, object]]]:
    file_findings: dict[str, list[QualityFinding]] = {file.path: [] for file in files}
    function_findings: dict[str, list[QualityFinding]] = {}
    for finding in findings:
        path = str(finding.source_location.get("path", "")) or finding.object_id.split(":", 1)[0]
        rel_path = _rel_path_for_finding(path, file_findings)
        if rel_path:
            file_findings.setdefault(rel_path, []).append(finding)
        if finding.object_type == "function":
            function_findings.setdefault(finding.object_id, []).append(finding)
    return {
        "files": _top_files(files, file_findings),
        "functions": _top_functions(files, function_findings),
    }


def _top_files(files: tuple[FileQuality, ...], file_findings: dict[str, list[QualityFinding]]) -> list[dict[str, object]]:
    rows = []
    for file in files:
        findings = file_findings.get(file.path, [])
        score = len([item for item in findings if item.severity == "error"]) * 10 + len([item for item in findings if item.severity == "warning"]) * 2 + file.lines // 100 + file.branch_count
        if score:
            rows.append({"path": file.path, "score": score, "lines": file.lines, "branches": file.branch_count, "findings": len(findings)})
    return sorted(rows, key=lambda row: (-int(row["score"]), str(row["path"])))[:10]


def _top_functions(files: tuple[FileQuality, ...], function_findings: dict[str, list[QualityFinding]]) -> list[dict[str, object]]:
    rows = []
    for file in files:
        for function in file.functions:
            object_id = f"{file.path}:{function.qualname}"
            findings = function_findings.get(object_id, [])
            score = len(findings) * 5 + function.lines // 20 + function.branches + function.max_nesting_depth + function.param_count
            if score:
                rows.append({"object_id": object_id, "score": score, "lines": function.lines, "branches": function.branches, "params": function.param_count, "findings": len(findings)})
    return sorted(rows, key=lambda row: (-int(row["score"]), str(row["object_id"])))[:10]


def _rel_path_for_finding(path: str, known: dict[str, list[QualityFinding]]) -> str:
    normalized = path.replace("\\", "/")
    if normalized in known:
        return normalized
    for rel_path in known:
        if normalized.endswith(rel_path.replace("\\", "/")):
            return rel_path
    return normalized


def _scope_for_finding(finding: QualityFinding) -> str:
    path = str(finding.source_location.get("path", ""))
    if path:
        return _scope_for_text(path)
    return _scope_for_text(finding.object_id)


def _scope_for_text(value: str) -> str:
    normalized = value.replace("\\", "/")
    if (
        "src/vibeflow/devtools/" in normalized
        or "src/vibeflow/tooling/devtools/" in normalized
    ):
        return "devtools"
    if normalized.startswith("tests/") or "/tests/" in normalized:
        return "tests"
    if normalized.startswith("src/") or "/src/" in normalized:
        return "src"
    return "other"


__all__ = [
    "DirectoryQuality",
    "FileQuality",
    "FunctionQuality",
    "ImportSite",
    "PrefixClusterQuality",
    "ProjectQualityFacts",
    "QualityFinding",
    "QualityPolicy",
    "QualityReport",
    "QualityStructureLimits",
    "QualityStructureRoles",
    "QualityThresholds",
    "SourceQualityReport",
]
