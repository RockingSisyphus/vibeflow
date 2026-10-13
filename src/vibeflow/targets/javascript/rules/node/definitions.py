"""javascript source Rule definitions."""
from vibeflow.core.rules import RuleDescriptor
from vibeflow.targets.shared.rule_support.implementation import _node, _base_lib, _chain
from vibeflow.targets.shared.rule_support.effect_records import EFFECT_POLICY_TYPE
from vibeflow.targets.shared.rule_support.import_policy import IMPORT_POLICY_SCHEMA


def source_rule_resources():
    scope_schema = {"effect_scope": {"type": "string"}, "policy": IMPORT_POLICY_SCHEMA}
    rules = (
        RuleDescriptor("vibeflow.async_lifecycle", description="Check explicit asynchronous task ownership and controller use.", handler="vibeflow.async_lifecycle", scope="source"),
        RuleDescriptor("vibeflow.no_side_effects", description="Check the explicitly selected effect policy.",
                       outputs={"effect_policy": EFFECT_POLICY_TYPE}, params_schema=scope_schema,
                       params_defaults={"effect_scope": "none", "policy": {}}, handler="vibeflow.no_side_effects", scope="source"),
        RuleDescriptor("vibeflow.node_architecture", description="Check statically resolved Node resource relations.", handler="vibeflow.node_architecture", scope="source"),
        RuleDescriptor("vibeflow.input_writes", description="Check finite direct Python entry input writes and simple local aliases.",
                       handler="vibeflow.input_writes", scope="source",
                       params_schema={"mutating_methods": {"type":"array", "items":{"type":"string"}}},
                       params_defaults={"mutating_methods":["append", "clear", "extend", "insert", "pop", "popitem", "remove", "setdefault", "sort", "update"]}),
        RuleDescriptor("vibeflow.node_interface", description="Check implementation-facing Node interface.", handler="vibeflow.node_interface", scope="source",
                       params_schema={"allowed_methods": {"type": "array", "items": {"type": "string"}}}, params_defaults={"allowed_methods": []}),
        RuleDescriptor("vibeflow.maintainability", description="Check source and helper maintainability.",
                       outputs={"metrics": "vibeflow.node_metrics.v1"}, handler="vibeflow.maintainability", scope="source",
                       params_schema={"policy": {"type": "object"}}, params_defaults={"policy": {}}),
        RuleDescriptor("vibeflow.import_side_effects", description="Inspect the selected module before import.",
                       params_schema=scope_schema, params_defaults={"effect_scope": "none", "policy": {}}, handler="vibeflow.import_side_effects", scope="source"),
    )
    return rules


def implementation_resources():
    return tuple(RuleDescriptor("vibeflow.implementation." + name,
                               params_schema={"policy": {"type": "object"}}, params_defaults={"policy": {}},
                               outputs={"diagnostics": "vibeflow.implementation_diagnostics.v1"})
                 for name in ("node", "base_lib", "dependency_chain"))


def implementation_handlers():
    return {"vibeflow.implementation.node": _node, "vibeflow.implementation.base_lib": _base_lib,
            "vibeflow.implementation.dependency_chain": _chain}
