"""JavaScript source adapter for the shared project-quality evaluator."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import replace
import os
from pathlib import Path

from vibeflow.core.quality import (
    FileQuality,
    FunctionQuality,
    ImportSite,
    ProjectQualityFacts,
    QualityFinding,
    QualityPolicy,
    QualityReport,
    QualityStructureConventions,
    QualityStructureLimits,
    QualityStructureRoles,
    QualityThresholds,
    evaluate_project_quality,
)
from vibeflow.targets.javascript.build.toolchain import AotToolchainError, DriverQualityResult, run_quality_facts_driver
from vibeflow.targets.javascript.build.quality_implementation import registered_implementation_requests


SOURCE_SUFFIXES = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"})
DEFAULT_EXCLUDED_DIRS = frozenset({
    ".git", ".hg", ".pytest_cache", ".venv", "build", "dist",
    "node_modules", "vendor", "coverage", ".next", ".turbo",
    "generated", "__generated__", ".svelte-kit", ".output", ".cache",
    "references",
})


def javascript_quality_policy(*, thresholds: QualityThresholds | None = None,
                              structure_limits: QualityStructureLimits | None = None,
                              structure_roles: QualityStructureRoles | None = None) -> QualityPolicy:
    if structure_limits is not None and structure_limits.allowed_root_code_files == QualityStructureLimits().allowed_root_code_files:
        structure_limits = replace(structure_limits, allowed_root_code_files=("index.ts", "index.js", "index.tsx", "index.jsx", "index.mts", "index.mjs"))
    return QualityPolicy(
        thresholds=thresholds or QualityThresholds(), structure_limits=structure_limits,
        structure_roles=structure_roles or QualityStructureRoles(base_lib_paths=(), infer_roles_from_path=False),
        structure_conventions=QualityStructureConventions(
            code_label="JavaScript/TypeScript", package_entry="index.ts",
            suggested_entry_files=("index.ts", "index.js"), public_entry_stems=("index", "api", "types"),
            ignored_prefix_stems=("index",), internal_suffixes=("_helpers", "_rules", "_visitors", "_validators", "-internal"),
            source_extension=".ts", require_exports_for_public_entry=True,
        ),
    )


def scan_javascript_quality(
    root: Path | str,
    *,
    package_root: Path | str,
    thresholds: QualityThresholds | None = None,
    structure_limits: QualityStructureLimits | None = None,
    structure_roles: QualityStructureRoles | None = None,
    registered_catalogs: object | None = None,
    excluded_dirs: Iterable[str] = DEFAULT_EXCLUDED_DIRS,
    node_command: str = "node",
    facts_cache: MutableMapping[str, DriverQualityResult] | None = None,
) -> QualityReport:
    """Scan handwritten sources once and evaluate language-neutral rules in Core."""

    selected = Path(root).expanduser().resolve()
    files = tuple(_iter_source_files(selected, set(excluded_dirs)))
    project_root = selected if selected.is_dir() else selected.parent
    ownership, _ = (
        registered_implementation_requests(
            registered_catalogs,
            project_root=project_root,
            selected_files=tuple(str(path) for path in files),
        )
        if registered_catalogs is not None else ([], {})
    )
    facts = run_quality_facts_driver(
        {
            "qualityRoot": str(project_root),
            "qualityFiles": [str(path) for path in files],
            "qualityImplementations": ownership,
        },
        package_root=package_root,
        node_command=node_command,
    )
    if facts_cache is not None and selected.is_dir():
        facts_cache[str(selected)] = facts
    parsed_files = tuple(_file_fact(item) for item in facts.files)
    if {item.path for item in parsed_files} != {
        (path.relative_to(selected if selected.is_dir() else selected.parent)).as_posix()
        for path in files
    }:
        raise AotToolchainError("QUALITY.FACTS.MISSING", "JavaScript parser omitted selected source files")
    findings = list(_finding_fact(item) for item in facts.findings)
    return evaluate_project_quality(
        ProjectQualityFacts(
            root=str(selected if selected.is_dir() else selected.parent),
            files=parsed_files,
            findings=tuple(findings),
        ),
        javascript_quality_policy(
            thresholds=thresholds,
            structure_limits=structure_limits,
            structure_roles=structure_roles,
        ),
    )


def _iter_source_files(root: Path, excluded: set[str]) -> Iterable[Path]:
    if root.is_file():
        if not _accepted(root):
            raise ValueError(f"not a JavaScript/TypeScript source file: {root}")
        yield root
        return
    if not root.is_dir():
        raise ValueError(f"quality path does not exist: {root}")
    anywhere = {item for item in excluded if not item.startswith("./")}
    rooted = tuple(Path(item[2:]) for item in excluded if item.startswith("./"))
    for directory, children, names in os.walk(root, followlinks=False):
        current = Path(directory)
        relative_dir = current.relative_to(root)
        children[:] = [
            name for name in sorted(children)
            if name not in anywhere
            and not any(
                (relative_dir / name) == item or item in (relative_dir / name).parents
                for item in rooted
            )
        ]
        for name in sorted(names):
            path = current / name
            relative = path.relative_to(root)
            if _accepted(path) and not any(relative == item or item in relative.parents for item in rooted):
                yield path.resolve()


def _accepted(path: Path) -> bool:
    name = path.name.lower()
    suffix = path.suffix.lower()
    return (
        path.is_file()
        and suffix in SOURCE_SUFFIXES
        and not name.endswith((f".generated{suffix}", f".min{suffix}"))
        and not name.startswith(("bundle.", "chunk."))
    )


def _file_fact(row: Mapping[str, object]) -> FileQuality:
    functions = tuple(
        FunctionQuality(
            qualname=str(item["qualname"]),
            line_start=int(item["line_start"]),
            line_end=int(item["line_end"]),
            lines=int(item["lines"]),
            branches=int(item["branches"]),
            max_nesting_depth=int(item["max_nesting_depth"]),
            param_count=int(item["param_count"]),
            ast_fingerprint=str(item["ast_fingerprint"]),
        )
        for item in row["functions"]
    )
    sites = tuple(
        ImportSite(
            source_module=str(item["source_module"]),
            imported=str(item["imported"]),
            raw_import=str(item["raw_import"]),
            path=str(item["path"]),
            line=int(item["line"]),
            column=int(item["column"]),
        )
        for item in row["import_sites"]
    )
    return FileQuality(
        path=str(row["path"]),
        module=str(row["module"]),
        lines=int(row["lines"]),
        bytes=int(row["bytes"]),
        function_count=int(row["function_count"]),
        class_count=int(row["class_count"]),
        public_api_count=int(row["public_api_count"]),
        branch_count=int(row["branch_count"]),
        max_nesting_depth=int(row["max_nesting_depth"]),
        imports=tuple(str(value) for value in row["imports"]),
        functions=functions,
        import_sites=sites,
    )


def _finding_fact(row: Mapping[str, object]) -> QualityFinding:
    return QualityFinding(
        rule_id=str(row["code"]),
        severity=str(row["severity"]),
        object_type=str(row["object_type"]),
        object_id=str(row["object_id"]),
        message=str(row["message"]),
        source_location={
            "path": str(row["path"]),
            "line": int(row["line"]),
            "column": int(row["column"]),
        },
        suggested_fix_type="fix_syntax",
    )


__all__ = ["DEFAULT_EXCLUDED_DIRS", "javascript_quality_policy", "scan_javascript_quality"]
