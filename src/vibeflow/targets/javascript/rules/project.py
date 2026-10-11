"""javascript project Rule definitions and parameter binding."""
from inspect import unwrap
from dataclasses import replace
from functools import wraps
from typing import Mapping, Any
from vibeflow.core.rules import RuleContext, RuleRecord, RuleResult
from vibeflow.core.rules import RuleDescriptor
from vibeflow.targets.shared.rule_support.project import project_parameter_defaults, _schema, _files, _dependencies, _structure, _duplicates
from vibeflow.targets.shared.quality_support import QualityPolicy


def project_quality_resources(policy: QualityPolicy | None = None):
    defaults = project_quality_rule_defaults(policy)
    rules = (
        RuleDescriptor("vibeflow.quality.files", params_schema=_schema(defaults["vibeflow.quality.files"]), params_defaults=defaults["vibeflow.quality.files"]),
        RuleDescriptor("vibeflow.quality.dependencies", params_schema=_schema(defaults["vibeflow.quality.dependencies"]), params_defaults=defaults["vibeflow.quality.dependencies"],
                       outputs={"graph": "vibeflow.module_graph.v1", "import_sites": "vibeflow.import_sites.v1", "chain": "vibeflow.module_chain.v1"}),
        RuleDescriptor("vibeflow.quality.structure", params_schema=_schema(defaults["vibeflow.quality.structure"]), params_defaults=defaults["vibeflow.quality.structure"],
                       inputs={"graph": "vibeflow.module_graph.v1", "import_sites": "vibeflow.import_sites.v1"},
                       outputs={"directories": "vibeflow.directories.v1", "clusters": "vibeflow.clusters.v1", "summary": "vibeflow.structure_summary.v1"}),
        RuleDescriptor("vibeflow.quality.duplicates"),
    )
    from vibeflow.targets.javascript.rulesets.project import project_quality_ruleset
    return rules, project_quality_ruleset()


def bound_project_quality_defaults(handlers, policy: QualityPolicy | None = None, *, rules, origins):
    """Configure only bindings that actually execute the standard project checks."""
    from vibeflow.targets.shared.rule_support.plugin import configured_rule_defaults
    defaults = project_quality_rule_defaults(policy)
    checks = tuple((check, defaults[resource_id])
                   for resource_id, check in project_quality_handlers().items())
    result = {}
    for resource_id, handler in handlers.items():
        check = unwrap(handler) if handler is not None else None
        for native, parameters in checks:
            if check is native and resource_id in rules:
                configured = configured_rule_defaults(rules[resource_id], parameters,
                    origins.get(("rules", resource_id)), factory=project_quality_resources)
                if configured:
                    result[resource_id] = configured
                break
    return result


def project_handler(checker):
    @wraps(checker, assigned=(), updated=())
    def check(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        if not context.facts.get("evaluate_sources", True):
            return RuleResult(state="unavailable")
        if "project_facts" not in context.facts and "analysis_cache" in context.facts:
            context = replace(context, facts={**context.facts,
                "project_facts": context.facts["analysis_cache"].project_facts(context.facts)})
        return checker(context, inputs, params)
    return check


def javascript_project_bindings():
    return {key: project_handler(checker) for key, checker in project_quality_handlers().items()}


def project_quality_rule_defaults(policy=None):
    return {"vibeflow.quality." + name: params for name, params in project_parameter_defaults(policy).items()}


def project_quality_handlers():
    return {"vibeflow.quality.files": _files, "vibeflow.quality.dependencies": _dependencies,
            "vibeflow.quality.structure": _structure, "vibeflow.quality.duplicates": _duplicates}
