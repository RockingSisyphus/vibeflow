"""Project themes use the same selection, overrides and records as Node rules."""

from dataclasses import replace
from tests.fixtures.support.project_rules import evaluate_standard_project_quality

import pytest

from vibeflow.core.findings import HealthFinding
from vibeflow.core.quality import FileQuality, ProjectQualityFacts, QualityPolicy, QualityThresholds
from vibeflow.core.rules import RuleCall, RuleContext, RuleDescriptor, RuleRecord, RuleRelation, RuleResult, RulesetDescriptor, compile_ruleset, execute_rule_plan
from vibeflow.builtin import project_quality_handlers, project_quality_resources, project_quality_rule_defaults
from vibeflow.builtin.project_quality import bound_project_quality_defaults


def facts(lines=10):
    return ProjectQualityFacts("/selected/scope", (FileQuality(
        path="selected.py", module="selected", lines=lines, bytes=100,
        function_count=0, class_count=0, public_api_count=0, branch_count=0,
        max_nesting_depth=0, imports=(), functions=()),))


def test_config_defaults_call_parameters_and_local_override_have_one_precedence():
    policy = QualityPolicy(thresholds=replace(QualityThresholds(), max_file_lines=30))
    defaults = project_quality_rule_defaults(policy)
    assert defaults["vibeflow.quality.files"]["max_file_lines"] == 30
    selected = RulesetDescriptor("local", (RuleCall("source", "vibeflow.quality.files", params={"max_file_lines":20}),),
        (RuleRelation("$self", "source", "overrides", params={"max_file_lines":7}),))
    report = evaluate_standard_project_quality(facts(), policy, rulesets=(selected,))
    finding = next(item for item in report.findings if item.code == "QUALITY.FILE.MAX_LINES")
    assert finding.details["limit"] == 7
    assert finding.definition_id == "vibeflow.quality.files"
    assert report.thresholds.max_file_lines == 7
    call = report.rule_executions[0]["plan"]["calls"][0]
    assert call["params"]["max_file_lines"] == 7
    assert call["parameter_sources"]["max_file_lines"] == "override:$self"


def test_project_parameters_follow_native_binding_identity_and_alias():
    from functools import wraps
    native = project_quality_handlers()["vibeflow.quality.files"]
    @wraps(native, assigned=(), updated=())
    def alias(*args):
        return native(*args)
    def external(*args):
        return RuleResult()
    policy = QualityPolicy(thresholds=replace(QualityThresholds(), max_file_lines=3))
    rule = RuleDescriptor("domain.files", params_schema={"max_file_lines": {"type": "integer"}})
    configured = bound_project_quality_defaults({"domain.files": alias,
        "vibeflow.quality.files": external}, policy, rules={rule.id:rule}, origins={})
    assert set(configured) == {"domain.files"}
    assert configured["domain.files"]["max_file_lines"] == 3


def test_workflow_depth_parameters_follow_native_binding_identity_and_alias():
    from functools import wraps
    from vibeflow.builtin.workflow import bound_workflow_depth_defaults
    from vibeflow.builtin.workflow_plan import nodesets as workflow_rule_checks
    @wraps(workflow_rule_checks, assigned=(), updated=())
    def alias(*args):
        return workflow_rule_checks(*args)
    def external(*args):
        return RuleResult()
    rule = RuleDescriptor("domain.workflow", params_schema={"nodeset_max_depth": {"type": "integer"}})
    configured = bound_workflow_depth_defaults({"domain.workflow": alias,
        "vibeflow.workflow": external, "vibeflow.graph.nodesets": external}, 7,
        rules={rule.id:rule}, origins={})
    assert configured == {"domain.workflow": {"nodeset_max_depth": 7}}


def test_project_configuration_preserves_external_native_defaults_and_narrow_schema():
    from vibeflow.core.descriptors.contributions import ResourceOrigin
    native = project_quality_handlers()["vibeflow.quality.files"]
    rule = RuleDescriptor("domain.files", params_schema={
        "max_file_lines": {"type": "integer"}, "warn_file_lines": {"type": "integer"}},
        params_defaults={"max_file_lines": 5})
    configured = bound_project_quality_defaults({rule.id:native},
        QualityPolicy(thresholds=QualityThresholds(max_file_lines=2, warn_file_lines=3)),
        rules={rule.id:rule}, origins={("rules", rule.id):ResourceOrigin("domain", "/domain/plugin.py", symbol="files")})
    assert configured == {rule.id: {"warn_file_lines": 3}}
    assert rule.params_defaults == {"max_file_lines": 5}


def test_standard_configuration_requires_actual_declaration_factory_and_callable():
    from vibeflow.core.descriptors.contributions import ResourceOrigin
    from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins
    from vibeflow.targets.shared.bindings import native_binding
    catalog = load_builtin_plugins("project").catalogs
    rules = {rule.id:rule for rule in catalog.rules}
    handlers = {rule.id:native_binding(catalog, "rule", rule.id) for rule in catalog.rules}
    policy = QualityPolicy(thresholds=QualityThresholds(max_file_lines=3))
    configured = bound_project_quality_defaults(handlers, policy, rules=rules, origins=catalog.origins)
    assert configured["vibeflow.quality.files"]["max_file_lines"] == 3
    origins = {**catalog.origins, ("rules", "vibeflow.quality.files"):
        ResourceOrigin("vibeflow.core", "/external/plugin.py", symbol="project_quality_resources")}
    configured = bound_project_quality_defaults(handlers, policy, rules=rules, origins=origins)
    assert "vibeflow.quality.files" not in configured


@pytest.mark.parametrize("topic", [False, True])
def test_depth_configuration_preserves_external_defaults_and_requires_declared_field(topic):
    from vibeflow.builtin.workflow import bound_workflow_depth_defaults, workflow_topic_handlers
    from vibeflow.builtin.workflow_plan import nodesets as workflow_rule_checks
    native = workflow_topic_handlers()["vibeflow.graph.nodesets"] if topic else workflow_rule_checks
    owned = RuleDescriptor("domain.depth", params_schema={"nodeset_max_depth": {"type": "integer"}},
        params_defaults={"nodeset_max_depth": 2})
    omitted = RuleDescriptor("domain.no_depth", params_schema={"nodeset_warn_width": {"type": "integer"}})
    configured = bound_workflow_depth_defaults({owned.id:native, omitted.id:native}, 7,
        rules={owned.id:owned, omitted.id:omitted}, origins={})
    assert configured == {}


def test_handler_does_not_consult_a_second_policy_fact():
    resources, _ = project_quality_resources(QualityPolicy(thresholds=replace(QualityThresholds(),max_file_lines=3)))
    plan = compile_ruleset(RulesetDescriptor("files",(RuleCall("custom_name","vibeflow.quality.files"),)),
        rules={item.id:item for item in resources})
    result = execute_rule_plan(plan,RuleContext(facts={"project_facts":facts(),
        "quality_policy":QualityPolicy(thresholds=replace(QualityThresholds(),max_file_lines=1000))}),handlers=project_quality_handlers())
    assert result.status == "FAIL"
    assert next(item for item in result.findings if item.code == "QUALITY.FILE.MAX_LINES").details["limit"] == 3


@pytest.mark.parametrize("direct", [False, True])
def test_explicit_descriptor_defaults_win_over_numeric_configuration(direct):
    resources, _ = project_quality_resources()
    original = next(item for item in resources if item.id == "vibeflow.quality.files")
    explicit = replace(original, params_defaults={**original.params_defaults, "max_file_lines": 5})
    policy = QualityPolicy(thresholds=replace(QualityThresholds(), max_file_lines=2))
    report = evaluate_standard_project_quality(facts(4), policy, rulesets=(explicit,) if direct else (explicit.id,),
        rules=None if direct else (explicit,))
    assert not any(item.code == "QUALITY.FILE.MAX_LINES" for item in report.findings)
    assert report.thresholds.max_file_lines == 5


def test_typed_report_records_do_not_depend_on_local_call_or_output_names():
    provider = RuleDescriptor("custom.graph",outputs={"renamed_output":"vibeflow.module_graph.v1"})
    selected = RulesetDescriptor("scope",(RuleCall("not_dependencies","custom.graph"),))
    def check(context, inputs, params):
        assert [item.path for item in context.require("project_facts").files] == ["selected.py"]
        return RuleResult({"renamed_output":RuleRecord("vibeflow.module_graph.v1",{"selected":[]})})
    report = evaluate_standard_project_quality(facts(), rulesets=(selected,), rules=(provider,),handlers={provider.id:check})
    payload = report.to_dict()
    assert report.status == "PASS"
    assert payload["dependency_graph"] == {"selected":[]}
    assert payload["record_availability"]["dependency_graph"] == "available"
    assert payload["record_availability"]["directory_graph"] == "not_selected"
    assert payload["directory_graph"] is None
    assert payload["longest_dependency_chain"] is None


def test_unrelated_rule_parameters_are_not_treated_as_quality_thresholds():
    rule = RuleDescriptor("domain.labels", params_schema={"max_file_lines":{"type":"object"}},
        params_defaults={"max_file_lines":{"label":"a domain parameter"}})
    report = evaluate_standard_project_quality(facts(), rulesets=(rule,), handlers={rule.id:lambda *args:RuleResult()})
    assert report.status == "PASS"
    assert report.thresholds == QualityThresholds()


def test_replacement_checker_and_nested_ruleset_keep_the_original_scope():
    replacement = RuleDescriptor("domain.source")
    selected = RulesetDescriptor("domain",(RuleCall("native",ruleset_id="vibeflow.quality.project"),),
        (RuleRelation("$self","native/files","overrides",replace_rule=replacement.id),))
    def check(context, inputs, params):
        source = context.require("project_facts").files[0]
        return RuleResult(findings=(HealthFinding(rule_id="DOMAIN.SCOPED",severity="warning",
            object_type="file",object_id=source.path,message=context.require("project_facts").root),))
    report = evaluate_standard_project_quality(facts(501),rulesets=(selected,),rules=(replacement,),handlers={replacement.id:check})
    finding = next(item for item in report.findings if item.code == "DOMAIN.SCOPED")
    assert finding.definition_id == replacement.id
    assert finding.message == "/selected/scope"
    assert not any(item.code == "QUALITY.FILE.MAX_LINES" for item in report.findings)
    assert report.record_availability["dependency_graph"] == "available"
    assert report.checked_rulesets == ("domain",)


def test_completed_provider_with_error_findings_still_supplies_structure_facts():
    original = project_quality_handlers()["vibeflow.quality.dependencies"]
    def check(context,inputs,params):
        value = original(context,inputs,params)
        return replace(value,findings=(HealthFinding(rule_id="DOMAIN.FAIL",severity="error",
            object_type="source",object_id="selected",message="facts still available"),))
    report = evaluate_standard_project_quality(facts(),handlers={"vibeflow.quality.dependencies":check})
    assert report.status == "FAIL"
    assert report.record_availability["structure_summary"] == "available"
    execution = report.rule_executions[0]
    assert execution["results"]["dependencies"]["state"] == "completed"
    assert execution["results"]["structure"]["state"] == "completed"


@pytest.mark.parametrize("state",["failed","unavailable"])
@pytest.mark.parametrize("warning",[False,True])
def test_selected_incomplete_rule_cannot_pass_even_without_error_diagnostics(state,warning):
    rule = RuleDescriptor("domain.missing",outputs={"graph":"vibeflow.module_graph.v1"})
    diagnostic = (HealthFinding(rule_id="DOMAIN.WARNING",severity="warning",object_type="source",
        object_id="selected",message="not an availability signal"),) if warning else ()
    report = evaluate_standard_project_quality(facts(),rulesets=(rule,),handlers={rule.id:lambda *args:RuleResult(state=state,findings=diagnostic)})
    assert report.status == "ERROR"
    assert any(item.code == "RULE.EXECUTION.UNAVAILABLE" for item in report.findings)
    assert report.to_dict()["dependency_graph"] is None
    assert report.record_availability["dependency_graph"] == "unavailable"


def test_empty_selection_reports_facts_without_claiming_analyzed_empty_graphs():
    report = evaluate_standard_project_quality(facts(501),rulesets=())
    assert report.status == "PASS"
    assert report.files[0].lines == 501
    assert report.checked_rulesets == ()
    assert not report.findings
    assert not report.rule_executions
    assert set(report.record_availability.values()) == {"not_selected"}
    assert report.to_dict()["dependency_graph"] is None


def test_missing_target_facts_are_unavailable_in_a_generic_rule_context():
    resources, _ = project_quality_resources()
    plan = compile_ruleset(RulesetDescriptor("files",(RuleCall("scope","vibeflow.quality.files"),)),rules={item.id:item for item in resources})
    result = execute_rule_plan(plan,RuleContext(facts={"source_context":object()}),handlers=project_quality_handlers())
    assert result.results["scope"].state == "unavailable"
    assert result.findings[0].code == "RULE.FACT.UNAVAILABLE"


def test_syntax_facts_cannot_be_discarded_by_direct_topic_selection():
    syntax = HealthFinding(rule_id="QUALITY.SYNTAX.PYTHON",severity="error",object_type="file",
        object_id="selected.py",message="invalid syntax",source_location={"path":"/selected/scope/selected.py","line":1})
    source = replace(facts(),findings=(syntax,))
    report = evaluate_standard_project_quality(source,rulesets=("vibeflow.quality.files",))
    assert report.status == "FAIL"
    assert any(item.code == syntax.code for item in report.findings)
    assert report.rule_executions[0]["results"]["check"]["state"] == "unavailable"


@pytest.mark.parametrize("values",[(7,),(7,11)])
def test_report_thresholds_use_executed_custom_rule_parameters(values):
    rule = RuleDescriptor("domain.threshold",params_schema={"max_file_lines":{"type":"integer"}},
        params_defaults={"max_file_lines":5})
    selection = RulesetDescriptor("domain.thresholds",tuple(
        RuleCall("check"+str(index),rule.id,params={"max_file_lines":value}) for index,value in enumerate(values)))
    policy = QualityPolicy(thresholds=replace(QualityThresholds(),max_file_lines=30))
    report = evaluate_standard_project_quality(facts(),policy,rulesets=(selection,),rules=(rule,),
        handlers={rule.id:lambda *args:RuleResult()})
    assert report.thresholds.max_file_lines == (values[0] if len(set(values)) == 1 else 30)
    assert [item["params"]["max_file_lines"] for item in report.rule_executions[0]["plan"]["calls"]] == list(values)
