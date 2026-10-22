"""Project-review rules over precisely scoped, Target-extracted facts.

Numeric configuration supplies Rule defaults. Explicit call parameters and
local graph overrides use the same precedence as every other review Rule.
"""

from dataclasses import asdict, fields

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.shared.quality_support.models import (
    SourceQualityFacts, QualityPolicy, QualityStructureConventions,
    QualityStructureLimits, QualityThresholds,
)
from vibeflow.core.rules.models import RuleRecord, RuleResult, plain


_FILE_LIMITS = ("max_file_lines", "warn_file_lines", "max_file_bytes", "max_functions_per_file",
               "max_classes_per_file", "max_public_api_per_file", "max_file_branches",
               "max_function_lines", "max_function_branches", "max_function_nesting", "max_function_params")
_DEPENDENCY_LIMITS = ("warn_dependency_chain", "max_dependency_chain")
_STRUCTURE_LIMITS = tuple(item.name for item in fields(QualityThresholds)
                          if item.name not in {*_FILE_LIMITS, *_DEPENDENCY_LIMITS})


def source_quality_defaults(policy: QualityPolicy | None = None) -> dict[str, dict[str, object]]:
    """Translate existing numeric configuration into ordinary Rule defaults.

    The result belongs at the composition root, before graph compilation;
    handlers do not consult a second policy object in their fact context.
    """
    active = policy or QualityPolicy()
    thresholds = active.thresholds.to_dict()
    structure = (active.structure_limits or QualityStructureLimits(enabled=False)).to_dict()
    return {
        "files": {name: thresholds[name] for name in _FILE_LIMITS},
        "dependencies": {name: thresholds[name] for name in _DEPENDENCY_LIMITS},
        "structure": {
            **{name: thresholds[name] for name in _STRUCTURE_LIMITS}, **structure,
            "structure_conventions": plain(asdict(active.structure_conventions)),
        },
        "duplicates": {},
    }


def _policy(params):
    threshold_names = {item.name for item in fields(QualityThresholds)}
    structure_names = {item.name for item in fields(QualityStructureLimits)}
    limits = {name: plain(value) for name, value in params.items() if name in structure_names}
    if "allowed_root_code_files" in limits:
        limits["allowed_root_code_files"] = tuple(limits["allowed_root_code_files"])
    conventions = plain(params.get("structure_conventions", {}))
    for name in ("suggested_entry_files", "public_entry_stems", "ignored_prefix_stems", "internal_suffixes", "distance_exempt_stems"):
        if name in conventions:
            conventions[name] = tuple(conventions[name])
    return QualityPolicy(
        thresholds=QualityThresholds(**{name: value for name, value in params.items() if name in threshold_names}),
        structure_limits=QualityStructureLimits(**limits) if limits else None,
        structure_conventions=QualityStructureConventions(**conventions),
    )


def _facts(context):
    value = context.facts.get("source_quality")
    if value is None:
        return None
    if not isinstance(value, SourceQualityFacts):
        raise TypeError("source_quality must be Target-extracted SourceQualityFacts for the current check scope")
    return value


def _unavailable(context):
    return RuleResult(findings=(HealthFinding(rule_id="RULE.FACT.UNAVAILABLE", severity="error",
        object_type=str(context.subject.get("kind", "source")),
        object_id=str(context.subject.get("definition_id", context.subject.get("id", "scope"))),
        failure_layer="rule", message="source_quality facts are unavailable for the current check scope"),), state="unavailable")


def _syntax_findings(facts):
    return tuple(item for item in facts.findings if item.rule_id.startswith("QUALITY.SYNTAX."))


def _files(context, inputs, params):
    from vibeflow.targets.shared.rule_support.source_measurements import _file_findings, _finding_belongs_to_file
    facts = _facts(context)
    if facts is None:
        return _unavailable(context)
    policy = _policy(params)
    syntax = _syntax_findings(facts)
    findings = list(syntax)
    for file in facts.files:
        syntax_failed = any(item.rule_id.startswith("QUALITY.SYNTAX.") and _finding_belongs_to_file(item, file) for item in facts.findings)
        if not syntax_failed:
            findings.extend(_file_findings(file, facts.root, policy))
    return RuleResult(findings=tuple(findings), state="unavailable" if syntax else "completed")


def _dependencies(context, inputs, params):
    from vibeflow.targets.shared.quality_support.dependencies import dependency_findings
    from vibeflow.targets.shared.rule_support.source_measurements import _build_dependency_graph, _import_sites_by_edge
    facts = _facts(context)
    if facts is None:
        return _unavailable(context)
    if _syntax_findings(facts):
        return RuleResult(findings=_syntax_findings(facts), state="unavailable")
    modules = {file.module for file in facts.files}
    graph = _build_dependency_graph(facts.files, modules)
    sites = _import_sites_by_edge(facts.files, modules)
    findings, chain = dependency_findings(graph, sites, _policy(params).thresholds)
    portable_sites = tuple({"source": source, "target": target, "sites": values}
                           for (source, target), values in sorted(sites.items()))
    return RuleResult({"graph": RuleRecord("vibeflow.module_graph.v1", graph),
                       "import_sites": RuleRecord("vibeflow.import_sites.v1", portable_sites),
                       "chain": RuleRecord("vibeflow.module_chain.v1", chain)}, tuple(findings))


def _structure(context, inputs, params):
    from vibeflow.targets.shared.quality_support.root_structure import analyze_root_structure
    from vibeflow.targets.shared.quality_support.structure import analyze_directory_structure
    facts = _facts(context)
    if facts is None:
        return _unavailable(context)
    if _syntax_findings(facts):
        return RuleResult(findings=_syntax_findings(facts), state="unavailable")
    policy = _policy(params)
    graph = inputs["graph"].value
    sites = {(item["source"], item["target"]): tuple(item["sites"])
             for item in inputs["import_sites"].value}
    directories, clusters, summary, findings = analyze_directory_structure(
        facts.files, graph, sites, policy.thresholds, policy.structure_conventions)
    root_summary, root_findings = analyze_root_structure(facts.files, policy.structure_limits,
        conventions=policy.structure_conventions)
    summary.update(root_summary)
    return RuleResult({"directories": RuleRecord("vibeflow.directories.v1", directories),
                       "clusters": RuleRecord("vibeflow.clusters.v1", clusters),
                       "summary": RuleRecord("vibeflow.structure_summary.v1", summary)}, tuple((*findings, *root_findings)))


def _duplicates(context, inputs, params):
    from vibeflow.targets.shared.quality_support.duplicates import duplicate_function_findings
    facts = _facts(context)
    if facts is None:
        return _unavailable(context)
    if _syntax_findings(facts):
        return RuleResult(findings=_syntax_findings(facts), state="unavailable")
    return RuleResult(findings=tuple(duplicate_function_findings(facts.files)))


def _schema(defaults):
    def kind(value):
        return "boolean" if isinstance(value, bool) else "integer" if isinstance(value, int) else "array" if isinstance(value, list) else "object"
    return {name: {"type": kind(value)} for name, value in defaults.items()}


__all__ = ["source_quality_defaults"]
