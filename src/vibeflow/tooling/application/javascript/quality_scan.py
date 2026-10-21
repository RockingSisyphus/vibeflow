"""Compose selected project Rules over JavaScript Target parser facts."""
from collections.abc import Iterable, MutableMapping
from dataclasses import replace
from pathlib import Path

from vibeflow.targets.javascript.rules.source_quality import bound_source_quality_defaults
from vibeflow.core.descriptors.contributions import contribution_facts
from vibeflow.targets.shared.quality_support import SourceQualityFacts, QualityReport, evaluate_source_quality
from vibeflow.core.rules import RuleContext
from vibeflow.targets.javascript.build.quality_source import (
    DEFAULT_EXCLUDED_DIRS, collect_javascript_quality_facts, javascript_quality_policy,
    _file_fact, _finding_fact,
)
from vibeflow.targets.javascript.build.toolchain import DriverQualityResult
from vibeflow.targets.shared.bindings import native_binding
from vibeflow.tooling.project.resources import load_builtin_plugins


def scan_javascript_quality(
    root: Path | str, *, package_root: Path | str, thresholds=None,
    structure_limits=None, structure_roles=None, registered_catalogs=None,
    excluded_dirs: Iterable[str] = DEFAULT_EXCLUDED_DIRS, node_command="node",
    facts_cache: MutableMapping[str, DriverQualityResult] | None = None,
    catalog=None,
) -> QualityReport:
    """Reuse an assembled Catalog, or assemble once for an independent scan."""
    if catalog is None:
        catalog = load_builtin_plugins("javascript").catalogs
    selected = Path(root).expanduser().resolve()
    facts = collect_javascript_quality_facts(selected, package_root=package_root,
        registered_catalogs=registered_catalogs, excluded_dirs=excluded_dirs,
        node_command=node_command, facts_cache=facts_cache)
    if structure_roles is not None and structure_roles._resource_scopes:
        from vibeflow.targets.shared.quality_support.resource_imports import implementation_import_scopes
        structure_roles = replace(structure_roles, _resource_scopes=
            implementation_import_scopes(structure_roles._resource_scopes, facts.implementations))
    policy = javascript_quality_policy(thresholds=thresholds,
        structure_limits=structure_limits, structure_roles=structure_roles)
    handlers = {item.id: native_binding(catalog, "rule", item.id) for item in catalog.rules}
    declared = {item.id: item for item in catalog.rules}
    defaults = bound_source_quality_defaults(handlers, policy, rules=declared, origins=catalog.origins)
    rules = {item.id: replace(item, params_defaults={**item.params_defaults, **defaults.get(item.id, {})})
             for item in catalog.rules}
    project_facts = SourceQualityFacts(str(selected if selected.is_dir() else selected.parent),
        tuple(_file_fact(item) for item in facts.files), tuple(_finding_fact(item) for item in facts.findings))
    return evaluate_source_quality(project_facts, policy, rulesets=("vibeflow.quality.source",),
        rules=rules, ruleset_catalog=catalog.rulesets, handlers=handlers,
        context=RuleContext(facts=contribution_facts(catalog),
            subject={"kind":"source", "id":project_facts.root}, target="javascript"))
