"""Filesystem adapter for the target-neutral project-quality evaluator."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from vibeflow.targets.shared.quality_support import (
    ProjectQualityFacts,
    QualityPolicy,
    QualityReport,
    QualityStructureLimits,
    QualityStructureRoles,
    QualityThresholds,
    evaluate_project_quality,
)
from vibeflow.targets.python.quality import PythonSource, analyze_python_source
from vibeflow.targets.python.quality.parse_cache import parse_python_source
from vibeflow.targets.python.quality.source_context import PythonSourceFile
from vibeflow.targets.python.quality.policy_parameters import source_rule_defaults
from vibeflow.targets.shared.bindings import native_binding
from vibeflow.targets.python.rules.project import bound_project_quality_defaults
from vibeflow.core.descriptors.contributions import contribution_facts
from vibeflow.core.rules import RuleContext
from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins


DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".ipynb_checkpoints",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "distribution",
        "node_modules",
        "references",
        "site-packages",
        "tests",
        "vendor",
        "venv",
        "vibeflow_distribution",
        "./sandbox/python/integration",
        "./sandbox/javascript/integration",
    }
)

def scan_code_quality(
    root: Path | str,
    *,
    thresholds: QualityThresholds | None = None,
    structure_limits: QualityStructureLimits | None = None,
    structure_roles: QualityStructureRoles | None = None,
    excluded_dirs: Iterable[str] = DEFAULT_EXCLUDED_DIRS,
    check_side_effects: bool = False,
    _parse_cache=None,
) -> QualityReport:
    """Read Python files, ask the Python Target for facts, then call Core."""

    resolved_root = Path(root).resolve()
    catalog = load_builtin_plugins("python").catalogs
    policy = QualityPolicy(
        thresholds=thresholds or QualityThresholds(),
        structure_limits=structure_limits,
        structure_roles=structure_roles or QualityStructureRoles(),
    )
    handlers = {item.id: native_binding(catalog, "rule", item.id) for item in catalog.rules}
    declared = {item.id: item for item in catalog.rules}
    defaults = bound_project_quality_defaults(handlers, policy, rules=declared, origins=catalog.origins)
    rules = {item.id: replace(item, params_defaults={**item.params_defaults, **defaults.get(item.id, {})})
             for item in catalog.rules}
    rules = source_rule_defaults(rules, handlers=handlers)
    selected = ("vibeflow.quality.project", "vibeflow.no_side_effects") if check_side_effects else ("vibeflow.quality.project",)
    files = []
    findings = []
    effect_sources = []
    parse_cache = _parse_cache if _parse_cache is not None else {}
    excluded = set(excluded_dirs)
    for path in _iter_python_files(resolved_root, excluded):
        relative_path = _relative_path(resolved_root, path)
        source = PythonSource(
            module=_module_name(resolved_root, path),
            relative_path=relative_path,
            source_path=str(path),
            text=path.read_text(encoding="utf-8"),
        )
        result = analyze_python_source(source, _parse_cache=parse_cache)
        files.append(result.file)
        findings.extend(result.findings)
        if check_side_effects and not result.findings:
            tree = parse_python_source(source.source_path, source.text, parse_cache)
            effect_sources.append((source, PythonSourceFile(source.source_path,source.module,source.text,_tree=tree)))
    return evaluate_project_quality(
        ProjectQualityFacts(
            root=str(resolved_root),
            files=tuple(files),
            findings=tuple(findings),
        ),
        policy,
        rulesets=selected,
        rules=rules,
        ruleset_catalog=catalog.rulesets,
        handlers=handlers,
        context=RuleContext(facts={**contribution_facts(catalog), "python_sources":tuple(effect_sources)},
                            subject={"kind":"python_source", "id":str(resolved_root)}, target="python"),
    )


def _iter_python_files(
    root: Path,
    excluded_dirs: set[str],
) -> Iterable[Path]:
    if root.is_file() and root.suffix == ".py":
        if not _skip_file(root):
            yield root
        return
    anywhere, rooted = _split_excluded_dirs(excluded_dirs)
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if any(part in anywhere for part in relative.parts):
            continue
        if any(relative == item or item in relative.parents for item in rooted):
            continue
        if not _skip_file(path):
            yield path


def _split_excluded_dirs(
    excluded_dirs: set[str],
) -> tuple[set[str], tuple[Path, ...]]:
    anywhere = {item for item in excluded_dirs if not item.startswith("./")}
    rooted = tuple(
        Path(item[2:])
        for item in sorted(excluded_dirs)
        if item.startswith("./") and item[2:]
    )
    return anywhere, rooted


def _skip_file(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".generated.py", "_pb2.py", "_pb2_grpc.py")) or name in {
        "build_distribution.py",
        "credentials.py",
        "secrets.py",
    }


def _relative_path(root: Path, path: Path) -> str:
    if root.is_file():
        return path.name
    return path.relative_to(root).as_posix()


def _module_name(root: Path, path: Path) -> str:
    if root.is_file():
        return path.stem
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or path.stem


__all__ = ["DEFAULT_EXCLUDED_DIRS", "scan_code_quality"]
