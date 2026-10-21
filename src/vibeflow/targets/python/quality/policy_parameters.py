"""Project configuration onto the parameters an actual native handler consumes."""

from dataclasses import replace
from inspect import unwrap
from weakref import WeakKeyDictionary

from vibeflow.targets.shared.rule_support.import_policy import normalized_import_policy
from vibeflow.targets.shared.quality_support.policy_data import merge_policy_data
from vibeflow.core.rules.models import plain
from vibeflow.targets.python.rules.node.policy import PurityPolicy


_POLICY_FIELDS = {
    "node_source": {"max_lines":"max_source_lines", "max_bytes":"max_source_bytes",
        "warn_lines":"warn_source_lines", "warn_bytes":"warn_source_bytes"},
    "complexity": {name:name for name in ("max_functions", "max_branches", "max_nesting_depth", "max_params", "max_contract_keys")},
    "imports": {"allowed_roots":"allowed_import_roots", "banned_roots":"banned_import_roots",
        "allowed_modules":"allowed_import_modules", "banned_modules":"banned_import_modules"},
    "maintainability": {name:name for name in ("warn_call_chain_length", "max_call_chain_length",
        "warn_dependency_chain_length", "max_dependency_chain_length")},
}
NUMERIC_POLICY_SECTIONS = ("node_source", "complexity", "maintainability")
_SOURCE_POLICY_CONSUMERS = WeakKeyDictionary()


def source_policy_consumer(handler, *, sections=NUMERIC_POLICY_SECTIONS, effect_defaults=False):
    """Record consumption by callable provenance, never a resource ID."""
    _SOURCE_POLICY_CONSUMERS[unwrap(handler)] = (tuple(sections), effect_defaults)
    return handler


def source_policy_parameters(policy=None):
    """Keep explicit configured import fields, including empty arrays."""
    active = policy if policy is not None else PurityPolicy()
    result = {section:{name:list(value) if isinstance(value := getattr(active, field), tuple) else value
                     for name, field in names.items()} for section, names in _POLICY_FIELDS.items()}
    configured = active.configured_import_fields if policy is not None else frozenset()
    if configured is not None:
        result["imports"] = {key:value for key,value in result["imports"].items() if key in configured}
    return result


def source_policy(params, *, sections=None, effect_defaults=True):
    """Construct judgments exclusively from supported effective parameters."""
    accepted = set(_POLICY_FIELDS if sections is None else sections)
    policy = params.get("policy", {})
    if not hasattr(policy, "items"):
        raise ValueError("rule policy must be an object")
    changes = {}
    for section, values in policy.items():
        if section not in accepted or section not in _POLICY_FIELDS or not hasattr(values, "items"):
            raise ValueError(f"unknown or unsupported rule policy section: {section}")
        for name, value in values.items():
            target = _POLICY_FIELDS[section].get(name)
            if target is None:
                raise ValueError(f"unknown rule policy parameter: {section}.{name}")
            if section != "imports":
                changes[target] = value
    if "imports" in accepted:
        imports = normalized_import_policy({"policy": {"imports":policy.get("imports", {})}}, effect_defaults=effect_defaults)
        changes.update({_POLICY_FIELDS["imports"][name]:tuple(value) for name,value in imports.items()})
    return PurityPolicy(**changes)


def _consumer(rule, handler):
    if not callable(handler) or rule.params_schema.get("policy", {}).get("type") != "object":
        return None
    return _SOURCE_POLICY_CONSUMERS.get(unwrap(handler))


def _configured_policy(policy, consumer):
    sections, effect_defaults = consumer
    configured = source_policy_parameters(policy)
    result = {section:configured[section] for section in sections}
    if "imports" in sections:
        imports = normalized_import_policy({}, effect_defaults=effect_defaults)
        imports.update(result["imports"])
        result["imports"] = imports
    return result


def _validate_local(policy, consumer):
    sections, effect_defaults = consumer
    source_policy({"policy":policy}, sections=sections, effect_defaults=effect_defaults)


def source_rule_defaults(rules, policy=None, *, handlers):
    """Configured consumed fields are defaults; Rule defaults remain authoritative."""
    result = dict(rules)
    for key, rule in rules.items():
        consumer = _consumer(rule, handlers.get(key))
        if consumer is not None:
            local = plain(rule.params_defaults.get("policy", {}))
            _validate_local(local, consumer)
            effective = _configured_policy(policy, consumer)
            merge_policy_data(effective, local)
            result[key] = replace(rule, params_defaults={**rule.params_defaults, "policy":effective})
    return result


def complete_source_policy_plan(plan, purity_policy=None, *, handlers):
    """Fill consumed configuration after Core's whole-object arbitration.

    A discarded Rule/call policy never returns through this completion.
    """
    invocations = []
    for invocation in plan.invocations:
        handler = handlers.get(invocation.rule.handler or invocation.rule.id, handlers.get(invocation.rule.id))
        consumer = _consumer(invocation.rule, handler)
        if consumer is not None:
            local_defaults = plain(invocation.rule.params_defaults.get("policy", {}))
            local = plain(invocation.params.get("policy", {}))
            _validate_local(local_defaults, consumer)
            _validate_local(local, consumer)
            defaults = _configured_policy(purity_policy, consumer)
            merge_policy_data(defaults, local_defaults)
            policy = _configured_policy(purity_policy, consumer)
            merge_policy_data(policy, local)
            rule = replace(invocation.rule, params_defaults={**invocation.rule.params_defaults, "policy":defaults})
            invocation = replace(invocation, rule=rule, params={**invocation.params, "policy":policy})
        invocations.append(invocation)
    return replace(plan, invocations=tuple(invocations))


def native_rule_bindings(registry, rules):
    """Resolve the same native callable provenance used by the loader."""
    from vibeflow.targets.shared.bindings import native_binding
    handlers = {}
    for rule in rules.values():
        key = rule.handler or rule.id
        handler = getattr(registry, "direct_bindings", {}).get(("rule", key))
        if handler is None:
            for catalog in registry.rule_catalogs or ():
                if hasattr(catalog, "origins"):
                    handler = native_binding(catalog, "rule", key)
                    if handler is not None:
                        break
        handlers[rule.id] = handler
    return handlers


def native_rule_origins(registry):
    """Retain the selected Catalog's actual declaration origins."""
    origins = {}
    for catalog in registry.rule_catalogs or ():
        declared = getattr(catalog, "origins", {})
        origins.update({("rules", rule.id):declared.get(("rules", rule.id)) for rule in catalog.rules})
    return origins
