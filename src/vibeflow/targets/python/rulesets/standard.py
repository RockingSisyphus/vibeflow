"""python default Rule combinations and phase entrypoints."""
from vibeflow.core.rules import RuleCall, RuleRelation, RulesetDescriptor


def standard_rulesets():
    scopes = {"process": "none", "io": "terminal", "python_io": "python_io", "document": "python_io",
              "data_store": "python_io", "global_state": "global_state", "base_lib": "none"}
    rulesets = []
    for name, scope in scopes.items():
        calls = (RuleCall("effects", rule_id="vibeflow.no_side_effects", params={"effect_scope": scope}),
                 RuleCall("interface", rule_id="vibeflow.node_interface"),
                 RuleCall("async", rule_id="vibeflow.async_lifecycle"),
                 RuleCall("maintainability", rule_id="vibeflow.maintainability"),
                 RuleCall("imports", rule_id="vibeflow.import_side_effects", params={"effect_scope": scope}))
        if name != "base_lib":
            calls += (RuleCall("architecture", rule_id="vibeflow.node_architecture"),
                      RuleCall("inputs", rule_id="vibeflow.input_writes"))
        review_calls = ("effects", "maintainability") if name == "base_lib" else ("effects", "architecture", "inputs", "interface", "async", "maintainability")
        rulesets.append(RulesetDescriptor("vibeflow." + name, calls=calls,
                        entrypoints={"static": review_calls, "run": review_calls, "import": ("imports",)}))
    topics = ("flow", "join", "nodesets", "duplicates", "planned", "review")
    rulesets.append(RulesetDescriptor("vibeflow.workflow",
        calls=(RuleCall("analysis", rule_id="vibeflow.workflow.analysis"),
               *(RuleCall(name, rule_id="vibeflow.workflow." + name) for name in topics),
               RuleCall("summary", rule_id="vibeflow.workflow")),
        relations=(*(RuleRelation(name, "analysis", "requires", {"analysis": "graphs"}) for name in topics),
                   RuleRelation("summary", "planned", "requires", {"events": "events"}),
                   RuleRelation("summary", "review", "requires", {"review": "review"}),
                   *(RuleRelation("summary", name, "requires") for name in topics if name not in {"planned", "review"})),
        entrypoints={"static": ("summary",), "run": ("summary",)},
        workflow_default=True, graph_scope="effective_subtree"))
    for name, scope in (("plugin", "none"), ("host_extension", "python_io")):
        rulesets.append(RulesetDescriptor("vibeflow." + name, calls=(
            RuleCall("imports", rule_id="vibeflow.import_side_effects"),
            RuleCall("effects", rule_id="vibeflow.no_side_effects", params={"effect_scope":scope}),
            RuleCall("interface", rule_id="vibeflow.node_interface"),
                 RuleCall("async", rule_id="vibeflow.async_lifecycle"),
            RuleCall("maintainability", rule_id="vibeflow.maintainability")),
            entrypoints={"import":("imports",), "static":("effects","interface","maintainability"), "run":("effects","interface","maintainability")}))
    rulesets.append(RulesetDescriptor("vibeflow.plugin_declaration", calls=(
        RuleCall("imports", rule_id="vibeflow.import_side_effects"),
        RuleCall("maintainability", rule_id="vibeflow.maintainability")),
        entrypoints={"import":("imports",), "static":("maintainability",), "run":("maintainability",)}))
    return tuple(rulesets)
