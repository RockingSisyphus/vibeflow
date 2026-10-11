"""Explicit standard-plugin assembly for project Rule behavior checks."""
from dataclasses import replace


def evaluate_standard_project_quality(facts, policy=None, **kwargs):
    from vibeflow.targets.python.rules.project import bound_project_quality_defaults
    from vibeflow.targets.shared.quality_support import evaluate_project_quality
    from vibeflow.targets.shared.bindings import native_binding
    from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins
    catalog = load_builtin_plugins("project").catalogs
    handlers = {item.id:native_binding(catalog,"rule",item.id) for item in catalog.rules}
    handlers.update(kwargs.pop("handlers", {}) or {})
    declared = {item.id:item for item in catalog.rules}
    defaults = bound_project_quality_defaults(handlers, policy, rules=declared, origins=catalog.origins)
    rules = {item.id:replace(item,params_defaults={**item.params_defaults,**defaults.get(item.id,{})})
             for item in catalog.rules}
    extra = kwargs.pop("rules", ()) or ()
    rules.update(extra if hasattr(extra,"items") else {item.id:item for item in extra})
    rulesets = {item.id:item for item in catalog.rulesets}
    extra = kwargs.pop("ruleset_catalog", ()) or ()
    rulesets.update(extra if hasattr(extra,"items") else {item.id:item for item in extra})
    selected = kwargs.pop("rulesets", ("vibeflow.quality.project",))
    return evaluate_project_quality(facts,policy,rulesets=selected,rules=rules,
        ruleset_catalog=rulesets,handlers=handlers,**kwargs)
