"""Default review selections, independent of language implementation."""

from vibeflow.core.rules.models import EFFECT_POLICY_TYPE, RuleCall, RuleDescriptor, RulesetDescriptor
from vibeflow.builtin.import_policy import IMPORT_POLICY_SCHEMA


def builtin_effect_resources() -> tuple[tuple[RuleDescriptor, ...], tuple[RulesetDescriptor, ...]]:
    scope_schema = {"effect_scope": {"type": "string"}, "policy": IMPORT_POLICY_SCHEMA}
    rules = (
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
        RuleDescriptor("vibeflow.workflow", description="Check current workflow architecture facts.",
                       outputs={"planned_events": "vibeflow.planned_events.v1", "workflow_review": "vibeflow.workflow_review.v1"},
                       params_schema={"nodeset_max_depth": {"type": "integer"}, "nodeset_warn_width": {"type": "integer"}},
                       params_defaults={"nodeset_max_depth": 4, "nodeset_warn_width": 10}, handler="vibeflow.workflow"),
    )
    scopes = {"process": "none", "io": "terminal", "python_io": "python_io", "document": "python_io",
              "data_store": "python_io", "global_state": "global_state", "base_lib": "none"}
    rulesets = []
    for name, scope in scopes.items():
        calls = (RuleCall("effects", rule_id="vibeflow.no_side_effects", params={"effect_scope": scope}),
                 RuleCall("interface", rule_id="vibeflow.node_interface"),
                 RuleCall("maintainability", rule_id="vibeflow.maintainability"),
                 RuleCall("imports", rule_id="vibeflow.import_side_effects", params={"effect_scope": scope}))
        if name != "base_lib":
            calls += (RuleCall("architecture", rule_id="vibeflow.node_architecture"),
                      RuleCall("inputs", rule_id="vibeflow.input_writes"))
        review_calls = ("effects", "maintainability") if name == "base_lib" else ("effects", "architecture", "inputs", "interface", "maintainability")
        rulesets.append(RulesetDescriptor("vibeflow." + name, calls=calls,
                        entrypoints={"static": review_calls, "run": review_calls, "import": ("imports",)}))
    rulesets.append(RulesetDescriptor("vibeflow.workflow", calls=(RuleCall("workflow", rule_id="vibeflow.workflow"),),
                    entrypoints={"static": ("workflow",), "run": ("workflow",)}))
    for name, scope in (("plugin", "none"), ("host_extension", "python_io")):
        rulesets.append(RulesetDescriptor("vibeflow." + name, calls=(
            RuleCall("imports", rule_id="vibeflow.import_side_effects"),
            RuleCall("effects", rule_id="vibeflow.no_side_effects", params={"effect_scope":scope}),
            RuleCall("interface", rule_id="vibeflow.node_interface"),
            RuleCall("maintainability", rule_id="vibeflow.maintainability")),
            entrypoints={"import":("imports",), "static":("effects","interface","maintainability"), "run":("effects","interface","maintainability")}))
    rulesets.append(RulesetDescriptor("vibeflow.plugin_declaration", calls=(
        RuleCall("imports", rule_id="vibeflow.import_side_effects"),
        RuleCall("maintainability", rule_id="vibeflow.maintainability")),
        entrypoints={"import":("imports",), "static":("maintainability",), "run":("maintainability",)}))
    return rules, tuple(rulesets)


__all__ = ["builtin_effect_resources"]
