"""Default resources use the same contributions and bindings as SDK resources."""
from pathlib import Path

from vibeflow.builtin.plugin import project_plugin
from vibeflow.builtin.implementation import implementation_handlers, implementation_resources
from vibeflow.core.descriptors import compose_contributions
from vibeflow.core.quality import FileQuality, ProjectQualityFacts, evaluate_project_quality
from vibeflow.core.quality.implementation import ImplementationLimits, ImplementationMetrics
from vibeflow.core.rules import RuleCall, RuleContext, RuleRelation, RulesetDescriptor, compile_ruleset, execute_rule_plan
from vibeflow.targets.python.sdk import Plugin, rule
from vibeflow.tooling.application.plugin_definitions import attach_plugin_definitions
from vibeflow.targets.shared.bindings import native_binding


def test_core_project_evaluator_has_no_implicit_standard_selection(monkeypatch):
    import vibeflow.builtin.plugin as providers
    monkeypatch.setattr(providers, "project_plugin", lambda: (_ for _ in ()).throw(AssertionError("implicit provider")))
    file = FileQuality("large.py", "large", 10000, 100000, 0, 0, 0, 0, 0, (), ())
    report = evaluate_project_quality(ProjectQualityFacts("/scope", (file,)))
    assert report.status == "PASS"
    assert report.checked_rulesets == ()
    assert report.rule_executions == ()


def test_contributed_native_replacement_is_resolved_by_its_own_origin():
    observed = []
    @rule(id="example.files", scope="source")
    def custom(context, inputs, params):
        from vibeflow.core.rules import RuleResult
        observed.append(context.require("marker"))
        return RuleResult()
    external = Plugin("example", resources=(custom,))
    standard = project_plugin()
    catalog = compose_contributions((standard.contributions(), external.contributions()))
    attach_plugin_definitions(catalog, {"python": (standard, external)})
    selected = RulesetDescriptor("example.review", (RuleCall("files", "vibeflow.quality.files"),),
        (RuleRelation("$self", "files", "overrides", replace_rule="example.files"),))
    plan = compile_ruleset(selected, rules=catalog.rules, rulesets=catalog.rulesets)
    handlers = {item.rule.id:native_binding(catalog, "rule", item.rule.id) for item in plan.invocations}
    result = execute_rule_plan(plan, RuleContext(facts={"marker":"external"}), handlers=handlers)
    assert result.status == "PASS"
    assert observed == ["external"]
    assert native_binding(catalog, "rule", "example.files") is custom
    origin = catalog.origins[("rules", "vibeflow.quality.files")]
    assert Path(origin.path).is_file()
    assert origin.line > 0
    assert not origin.path.startswith("builtin:")
    descriptor = catalog.rules.require("vibeflow.quality.files")
    assert not descriptor.handler
    assert origin.symbol == "project_quality_resources"
    assert catalog.origins[("rulesets", "vibeflow.quality.project")].symbol == "project_quality_resources"
    implementation = descriptor.implementations[0].source
    assert implementation.export == "_files"
    assert Path(implementation.ref).is_file()


def test_portable_implementation_rule_applies_selected_policy_parameters():
    resources = {item.id:item for item in implementation_resources()}
    context = RuleContext(facts={"metrics":ImplementationMetrics(source_lines=10),
        "limits":ImplementationLimits(max_source_lines=5, warn_source_lines=None)})
    def check(limit):
        selection = RulesetDescriptor("policy", (RuleCall("source", "vibeflow.implementation.node",
            params={"policy":{"node_source":{"max_lines":limit}}}),))
        return execute_rule_plan(compile_ruleset(selection, rules=resources), context, handlers=implementation_handlers())
    rejected, accepted = check(1), check(1000)
    assert rejected.status == "FAIL"
    assert accepted.status == "PASS"
    assert rejected.findings[0].details["limit"] == 1


def test_core_graph_models_and_parser_do_not_select_standard_plugins():
    from vibeflow.core.flow import GraphConfig
    from vibeflow.core.config.graph import parse_graph_config_data
    assert GraphConfig(()).rulesets is None
    graph = parse_graph_config_data({"pipeline":{"nodes":[{"id":"root","type_used":"example.node","display_name":"Call","description":"An explicit call instance."}]},"nodesets":[{
        "type_key":"example.stage","display_name":"Stage","description":"An explicit native scope.",
        "requires":[],"provides":[],"pipeline":{"nodes":[{"id":"child","type_used":"example.node","display_name":"Call","description":"An explicit call instance."}]}}]})
    assert graph.rulesets is None
    assert graph.nodesets["example.stage"].graph.rulesets is None
