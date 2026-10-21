"""Filesystem adapter for the target-neutral project-quality evaluator."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from vibeflow.targets.shared.quality_support import (
    SourceQualityFacts,
    QualityPolicy,
    QualityReport,
    QualityStructureLimits,
    QualityStructureRoles,
    QualityThresholds,
    evaluate_source_quality,
)
from vibeflow.targets.python.quality import PythonSource, analyze_python_source
from vibeflow.targets.python.quality.parse_cache import parse_python_source
from vibeflow.targets.python.quality.source_context import PythonSourceFile
from vibeflow.targets.python.quality.policy_parameters import source_rule_defaults
from vibeflow.targets.shared.bindings import native_binding
from vibeflow.targets.python.rules.source_quality import bound_source_quality_defaults
from vibeflow.core.descriptors.contributions import contribution_facts
from vibeflow.core.rules import RuleContext
from vibeflow.tooling.application.python.project.source_files import DEFAULT_EXCLUDED_DIRS, _iter_python_files, _relative_path, _module_name
from vibeflow.tooling.project.resources import load_builtin_plugins



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
    defaults = bound_source_quality_defaults(handlers, policy, rules=declared, origins=catalog.origins)
    rules = {item.id: replace(item, params_defaults={**item.params_defaults, **defaults.get(item.id, {})})
             for item in catalog.rules}
    rules = source_rule_defaults(rules, handlers=handlers)
    selected = ("vibeflow.quality.source", "vibeflow.no_side_effects") if check_side_effects else ("vibeflow.quality.source",)
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
    return evaluate_source_quality(
        SourceQualityFacts(
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












__all__ = ["DEFAULT_EXCLUDED_DIRS", "scan_code_quality"]
