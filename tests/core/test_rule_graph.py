"""Rule relation semantics are independent of business workflow topology."""

import asyncio
import json

import pytest

from vibeflow.core import Finding
from vibeflow.core.rules import (
    RuleCall, RuleContext, RuleDescriptor, RuleGraphError, RuleRecord, RuleRelation,
    RuleResult, RulesetDescriptor, compile_ruleset, execute_rule_plan, execute_rule_plan_async,
)


def rules():
    return {item.id: item for item in (
        RuleDescriptor("discover", outputs={"symbols": "symbols.v1"}),
        RuleDescriptor("check", inputs={"symbols": "symbols.v1"}),
        RuleDescriptor("size", params_schema={"limit": {"type": "integer"}}, params_defaults={"limit": 10}, scope="source"),
        RuleDescriptor("replacement", outputs={"symbols": "symbols.v1"}),
    )}


def test_typed_dependency_runs_with_findings_and_readonly_records():
    descriptor = RulesetDescriptor("model", (RuleCall("owner", "check"), RuleCall("symbols", "discover")),
        (RuleRelation("owner", "symbols", "requires", bindings={"symbols": "symbols"}),))
    plan = compile_ruleset(descriptor, rules=rules())
    calls = []

    def discover(context, inputs, params):
        with pytest.raises(TypeError):
            context.facts["nested"]["x"] = 2
        return RuleResult({"symbols": RuleRecord("symbols.v1", ["Model"])},
                          (Finding("DOMAIN.WARNING", "warning", "file", "model.py", "still available"),))

    def check(context, inputs, params):
        calls.append(inputs["symbols"].value)
        return RuleResult()

    result = execute_rule_plan(plan, RuleContext(facts={"nested": {"x": 1}}), handlers={"discover": discover, "check": check})
    assert plan.order == ("symbols", "owner")
    assert calls == [("Model",)]
    assert result.status == "CONCERNS"


def test_provider_failure_is_unavailable_not_fake_empty_input():
    descriptor = RulesetDescriptor("model", (RuleCall("owner", "check"), RuleCall("symbols", "discover")),
        (RuleRelation("owner", "symbols", "requires", bindings={"symbols": "symbols"}),))
    called = []
    result = execute_rule_plan(compile_ruleset(descriptor, rules=rules()), RuleContext(),
                              handlers={"discover": lambda *args: RuleResult(), "check": lambda *args: called.append(True)})
    assert not called
    assert result.results["symbols"].state == "failed"
    assert result.results["owner"].state == "unavailable"
    assert result.status == "ERROR"


def test_mixed_relation_cycle_is_valid_but_dependency_cycle_is_not():
    descriptor = RulesetDescriptor("mixed", (RuleCall("a", "size"), RuleCall("b", "size")),
        (RuleRelation("a", "b", "requires"), RuleRelation("b", "a", "overrides", params={"limit": 30})))
    plan = compile_ruleset(descriptor, rules=rules())
    assert plan.order == ("b", "a")
    assert plan.invocations[1].params["limit"] == 30
    cyclic = RulesetDescriptor("bad", descriptor.calls,
        (RuleRelation("a", "b", "requires"), RuleRelation("b", "a", "requires")))
    with pytest.raises(RuleGraphError, match="RULE.REQUIRES.CYCLE"):
        compile_ruleset(cyclic, rules=rules())


def test_unordered_override_conflict_is_not_resolved_by_load_order():
    descriptor = RulesetDescriptor("conflict", tuple(RuleCall(key, "size") for key in ("base", "a", "b")),
        (RuleRelation("a", "base", "overrides", params={"limit": 20}),
         RuleRelation("b", "base", "overrides", params={"limit": 30})))
    with pytest.raises(RuleGraphError, match="RULE.OVERRIDE.CONFLICT"):
        compile_ruleset(descriptor, rules=rules())
    ordered = RulesetDescriptor("ordered", descriptor.calls,
                               (*descriptor.relations, RuleRelation("a", "b", "overrides")))
    plan = compile_ruleset(ordered, rules=rules())
    base = next(item for item in plan.invocations if item.id == "base")
    assert base.params["limit"] == 20
    assert base.parameter_sources["limit"] == "override:a"


def test_shared_ruleset_overrides_are_local_and_same_effective_calls_are_deduplicated():
    base = RulesetDescriptor("base", (RuleCall("size", "size"),))
    parent = RulesetDescriptor("parent", (RuleCall("left", ruleset_id="base"), RuleCall("right", ruleset_id="base")),
                              (RuleRelation("$self", "left/size", "overrides", params={"limit": 50}),))
    plan = compile_ruleset(parent, rules=rules(), rulesets={"base": base})
    assert {item.id: item.params["limit"] for item in plan.invocations} == {"left/size": 50, "right/size": 10}
    same = RulesetDescriptor("same", parent.calls)
    executed = []
    result = execute_rule_plan(compile_ruleset(same, rules=rules(), rulesets={"base": base}), RuleContext(subject={"source_identity": {"file": "size.py", "symbol": "Size"}}),
                              handlers={"size": lambda *args: executed.append(1) or RuleResult()})
    assert executed == [1]
    assert result.aliases == {"right/size": "left/size"}


def test_call_scoped_rule_executes_each_instance_and_source_scope_requires_identity():
    descriptor = RulesetDescriptor("calls", (RuleCall("left", "call-check"), RuleCall("right", "call-check")))
    resources = {"call-check": RuleDescriptor("call-check")}
    calls = []
    result = execute_rule_plan(compile_ruleset(descriptor, rules=resources), RuleContext(subject={"source_identity": "same.py:Node"}),
        handlers={"call-check": lambda context, *_: calls.append(context.subject["rule_call_id"]) or RuleResult()})
    assert calls == ["left", "right"]
    assert result.executed == ("left", "right")
    assert result.aliases == {}
    source_calls = []
    source = RulesetDescriptor("source", (RuleCall("left", "size"), RuleCall("right", "size")))
    result = execute_rule_plan(compile_ruleset(source, rules=rules()), RuleContext(),
        handlers={"size": lambda *_: source_calls.append(True) or RuleResult()})
    assert len(source_calls) == 2
    assert result.aliases == {}


def test_source_context_exposes_all_source_calls_and_no_current_call_identity():
    descriptor = RulesetDescriptor("context", (RuleCall("source", "size"), RuleCall("call", "call-check")))
    resources = {**rules(), "call-check": RuleDescriptor("call-check")}
    context = RuleContext(facts={"call": {"params": {"size": 3}}, "source": "node.py"},
        subject={"owner": "workflow", "call_id": "first", "call_path": ["first"], "call_paths": [["first"]],
                 "call_spec": {"params": {"size": 3}}, "source_call_paths": [["first"], ["second"]]},
        scope={"workflow": "first-workflow", "workflows": ["first-workflow", "second-workflow"]})
    observed = {}
    def handler(current, *_):
        observed["source" if "rule_call_id" not in current.subject else "call"] = current
        return RuleResult()
    result = execute_rule_plan(compile_ruleset(descriptor, rules=resources), context,
                               handlers={"size": handler, "call-check": handler})
    assert result.status == "PASS"
    source = observed["source"]
    assert "call" not in source.facts
    assert not {"owner", "call_id", "call_spec", "call_path", "rule_call_id"} & source.subject.keys()
    assert "call_paths" not in source.subject and "source_call_paths" not in source.subject
    assert "workflow" not in source.scope
    assert source.scope["workflows"] == ("first-workflow", "second-workflow")
    call = observed["call"]
    assert call.facts["call"]["params"]["size"] == 3
    assert call.subject["call_id"] == "first"
    assert call.subject["rule_call_id"] == "call"
    assert call.scope["workflow"] == "first-workflow"


def test_checker_replacement_preserves_instance_and_validates_consumed_interface():
    descriptor = RulesetDescriptor("replace", (RuleCall("symbols", "discover"), RuleCall("owner", "check")),
        (RuleRelation("owner", "symbols", "requires", bindings={"symbols": "symbols"}),
         RuleRelation("$self", "symbols", "overrides", replace_rule="replacement")))
    plan = compile_ruleset(descriptor, rules=rules())
    assert plan.invocations[0].id == "symbols"
    assert plan.invocations[0].rule_id == "replacement"
    assert plan.invocations[1].inputs["symbols"] == ("symbols", "symbols")
    wrong = RulesetDescriptor("wrong", descriptor.calls,
        (RuleRelation("$self", "symbols", "overrides", replace_rule="size"),))
    with pytest.raises(RuleGraphError, match="RULE.REPLACEMENT.INTERFACE"):
        compile_ruleset(wrong, rules=rules())


def test_ruleset_cycle_and_explicit_entrypoint_boundaries():
    a = RulesetDescriptor("a", (RuleCall("b", ruleset_id="b"),))
    b = RulesetDescriptor("b", (RuleCall("a", ruleset_id="a"),))
    with pytest.raises(RuleGraphError, match="RULE.INCLUDES.CYCLE"):
        compile_ruleset(a, rules=rules(), rulesets={"a": a, "b": b})
    domain = RulesetDescriptor("domain", (RuleCall("size", "size"),))
    assert compile_ruleset(domain, rules=rules(), entrypoint="run").order == ()
    assert compile_ruleset(domain, rules=rules(), entrypoint="static").order == ("size",)


def test_wire_result_and_async_handlers_use_same_engine_contract():
    descriptor = RulesetDescriptor("async", (RuleCall("symbols", "discover"),))

    async def handler(*args):
        return {"records": {"symbols": {"type_id": "symbols.v1", "value": ["Model"]}}, "findings": []}

    result = asyncio.run(execute_rule_plan_async(compile_ruleset(descriptor, rules=rules()), RuleContext(), handlers={"discover": handler}))
    assert result.results["symbols"].records["symbols"].value == ("Model",)
    assert result.to_dict()["results"]["symbols"]["records"]["symbols"]["value"] == ["Model"]


def test_explicit_inclusion_membership_controls_local_overrides():
    base = RulesetDescriptor("base", (RuleCall("size", "size"),))
    descriptor = RulesetDescriptor("scope", (RuleCall("left", ruleset_id="base"), RuleCall("right", ruleset_id="base")),
        (RuleRelation("left", "right/size", "includes"),
         RuleRelation("left", "right", "overrides", params={"limit": 99})),
        entrypoints={"static": ("left",)})
    plan = compile_ruleset(descriptor, rules=rules(), rulesets={"base": base})
    assert plan.order == ("right/size",)
    assert plan.invocations[0].params["limit"] == 99


def test_unselected_override_does_not_change_active_check():
    descriptor = RulesetDescriptor("selected", (RuleCall("base", "size"), RuleCall("other", "size")),
        (RuleRelation("other", "base", "overrides", params={"limit": 99}),),
        entrypoints={"static": ("base",)})
    plan = compile_ruleset(descriptor, rules=rules())
    assert plan.order == ("base",)
    assert plan.invocations[0].params["limit"] == 10


def test_requires_provider_is_selected_and_replacement_inputs_still_need_bindings():
    descriptor = RulesetDescriptor("select", (RuleCall("owner", "check"), RuleCall("symbols", "discover")),
        (RuleRelation("owner", "symbols", "requires", bindings={"symbols": "symbols"}),),
        entrypoints={"static": ("owner",)})
    assert compile_ruleset(descriptor, rules=rules()).order == ("symbols", "owner")
    replacement = RuleDescriptor("new-discover", inputs={"extra": "extra.v1"}, outputs={"symbols": "symbols.v1"})
    resource_rules = {**rules(), replacement.id: replacement}
    bad = RulesetDescriptor("replace", descriptor.calls,
        (*descriptor.relations, RuleRelation("$self", "symbols", "overrides", replace_rule=replacement.id)))
    with pytest.raises(RuleGraphError, match="RULE.INPUT.UNBOUND"):
        compile_ruleset(bad, rules=resource_rules)


def test_rule_findings_serialize_nested_readonly_context_facts():
    descriptor = RulesetDescriptor("serialize", (RuleCall("size", "size"),))
    result = execute_rule_plan(compile_ruleset(descriptor, rules=rules()), RuleContext(facts={"metrics": {"values": [1, 2]}}),
        handlers={"size": lambda context, *_: RuleResult(findings=(
            Finding("DOMAIN.ERROR", "error", "node", "n", "bad", details=context.facts),))})
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["findings"][0]["details"] == {"metrics": {"values": [1, 2]}}


def test_diagnostic_code_and_rule_definition_identity_are_distinct():
    descriptor = RulesetDescriptor("diagnostic", (RuleCall("check", "size"),))
    result = execute_rule_plan(compile_ruleset(descriptor, rules=rules()), RuleContext(),
        handlers={"size": lambda *_: {"findings": [{"code": "MODEL.MULTIPLE_BLOCKS", "rule_id": "plugin.declared_rule",
            "file": "model.py", "line": 42, "message": "two independent model blocks"}]}})
    diagnostic = result.findings[0]
    assert diagnostic.code == "MODEL.MULTIPLE_BLOCKS"
    assert diagnostic.definition_id == "size"
    payload = diagnostic.to_dict()
    assert payload["code"] == "MODEL.MULTIPLE_BLOCKS"
    assert payload["definition_id"] == "size"
    assert payload["source_location"] == {"path": "model.py", "line": 42, "column": 1}


def test_source_cache_belongs_to_check_session_and_preserves_fact_identity():
    descriptor = RulesetDescriptor("session", (RuleCall("size", "size"),))
    plan = compile_ruleset(descriptor, rules=rules())
    cache, seen = {}, []
    handlers = {"size": lambda *_: seen.append(True) or RuleResult()}
    first_context = RuleContext(subject={"source_identity": {"path": "node.py", "symbol": "Node", "snapshot": "one", "contract": {"provides": ["first"]}}})
    first = execute_rule_plan(plan, first_context, handlers=handlers, source_cache=cache)
    second = execute_rule_plan(plan, first_context, handlers=handlers, source_cache=cache)
    assert first.executed == ("size",)
    assert second.executed == ()
    assert second.aliases == {"size": "session:session/size"}
    changed = RuleContext(subject={"source_identity": {"path": "node.py", "symbol": "Node", "snapshot": "one", "contract": {"provides": ["second"]}}})
    execute_rule_plan(plan, changed, handlers=handlers, source_cache=cache)
    assert len(seen) == 2
    execute_rule_plan(plan, first_context, handlers=handlers, source_cache={})
    assert len(seen) == 3


def test_cached_source_diagnostics_preserve_execution_status_without_duplicate_findings():
    plan = compile_ruleset(RulesetDescriptor("diagnostic-cache", (RuleCall("size", "size"),)), rules=rules())
    context = RuleContext(subject={"source_identity": "node.py:Node@version"})
    cache = {}
    handlers = {"size": lambda *_: {"findings": [{"code": "MODEL.BLOCK.COUNT", "message": "multiple blocks"}]}}
    first = execute_rule_plan(plan, context, handlers=handlers, source_cache=cache)
    cached = execute_rule_plan(plan, context, handlers=handlers, source_cache=cache)
    assert first.status == cached.status == "FAIL"
    assert cached.executed == ()
    assert cached.findings == ()
    assert cached.results["size"].findings[0].definition_id == "size"
    assert cached.aliases == {"size": "session:diagnostic-cache/size"}


def test_rule_context_freezes_graph_compiled_and_result_dataclass_fields():
    from vibeflow.core.compiler import CompiledGraph
    from vibeflow.core.flow import GraphConfig, NodeCallSpec
    from vibeflow.core.findings import HealthFinding

    graph = GraphConfig(nodes=(NodeCallSpec("one", "example.one", params={"nested": {"values": [1]}}),))
    compiled = CompiledGraph(order=("one",), explicit_edges=(), data_edges=(), effective_edges=(),
                             providers={"value": "one"}, consumers={}, flow_kinds={"one": "process"})
    context = RuleContext(facts={"graph": graph, "compiled": compiled})
    with pytest.raises(TypeError):
        context.facts["graph"].nodes[0].params["nested"]["values"] = (2,)
    with pytest.raises(TypeError):
        context.facts["compiled"].providers["value"] = "other"
    assert context.facts["graph"] is not graph
    assert isinstance(context.facts["graph"], GraphConfig)
    assert isinstance(context.facts["compiled"], CompiledGraph)
    graph.nodes[0].params["nested"]["values"].append(2)
    compiled.providers["value"] = "changed original"
    assert context.facts["graph"].nodes[0].params["nested"]["values"] == (1,)
    assert context.facts["compiled"].providers["value"] == "one"
    details = {"nested": {"values": [1]}}
    result = RuleResult(findings=(HealthFinding(rule_id="TEST", details=details),))
    details["nested"]["values"].append(2)
    assert result.findings[0].details["nested"]["values"] == (1,)
    with pytest.raises(TypeError):
        result.findings[0].details["nested"]["values"] = ()


def test_readonly_preserves_cyclic_dataclass_fact_identity_without_shared_maps():
    from dataclasses import dataclass, field
    from vibeflow.core.rules.models import readonly

    @dataclass(frozen=True)
    class Fact:
        children: dict = field(default_factory=dict)

    fact = Fact()
    fact.children["self"] = fact
    frozen = readonly(fact)
    assert frozen.children["self"] is frozen
    with pytest.raises(TypeError):
        frozen.children["other"] = fact
    assert "other" not in fact.children


@pytest.mark.parametrize("entrypoints", [
    {"statci": []}, {"static": "check"}, {"static": {"check": True}},
    {"static": None}, {"static": [1]}, {"static": [""]}, {"run": [" "]},
])
def test_ruleset_rejects_invalid_entrypoint_names_and_values(entrypoints):
    with pytest.raises(ValueError, match="entrypoint"):
        RulesetDescriptor("invalid", entrypoints=entrypoints)


def test_explicit_empty_entrypoints_are_valid_and_unknown_compile_phase_fails():
    descriptor = RulesetDescriptor("empty", (RuleCall("size", "size"),),
                                   entrypoints={"import": [], "static": [], "run": []})
    for phase in ("import", "static", "run"):
        assert compile_ruleset(descriptor, rules=rules(), entrypoint=phase).order == ()
    with pytest.raises(RuleGraphError, match="RULE.ENTRYPOINT.INVALID"):
        compile_ruleset(descriptor, rules=rules(), entrypoint="statci")


def test_record_snapshots_frozen_dataclass_fields_and_keeps_query_services_in_facts():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Evidence:
        details: dict

    original = Evidence({"values": [1], "names": {"one"}})
    record = RuleRecord("evidence.v1", original)
    original.details["values"].append(2)
    assert isinstance(record.value, Evidence)
    assert record.value.details["values"] == (1,)
    assert record.value.details["names"] == frozenset({"one"})
    with pytest.raises(TypeError):
        record.value.details["values"] = ()

    class QueryService:
        pass

    service = QueryService()
    assert RuleContext(facts={"service": service}).facts["service"] is service
    with pytest.raises(ValueError, match="portable data"):
        RuleRecord("evidence.v1", {"nested": service})


def test_mutable_dataclass_or_opaque_outputs_fail_before_consumers_run():
    from dataclasses import dataclass

    @dataclass
    class MutableEvidence:
        value: int = 1

    descriptor = RulesetDescriptor("data", (RuleCall("owner", "check"), RuleCall("symbols", "discover")),
        (RuleRelation("owner", "symbols", "requires", bindings={"symbols": "symbols"}),))
    for value in (MutableEvidence(), object(), float("nan")):
        consumed = []
        result = execute_rule_plan(compile_ruleset(descriptor, rules=rules()), RuleContext(), handlers={
            "discover": lambda *args: RuleResult({"symbols": RuleRecord("symbols.v1", value)}),
            "check": lambda *args: consumed.append(True),
        })
        assert not consumed
        assert result.results["symbols"].state == "failed"
        assert result.results["owner"].state == "unavailable"
        assert any(finding.code == "RULE.EXECUTION" for finding in result.findings)


def test_builtin_planned_records_preserve_frozen_event_types():
    from vibeflow.core.flow import GraphConfig, NodeCallSpec
    from vibeflow.core.planned import PlannedBehavior
    from vibeflow.targets.shared.quality_support.workflow_rules.planned import PlannedImplementationCheck
    from vibeflow.targets.python.rules.graph import workflow_topic_resources, workflow_topic_handlers

    graph = GraphConfig(nodes=(NodeCallSpec("future", "example.future", status="planned",
        planned_behavior=PlannedBehavior("python_stub", "stubs/future.py")),))
    resources = {item.id:item for item in workflow_topic_resources()}
    plan = compile_ruleset(RulesetDescriptor("planned", (RuleCall("check", "vibeflow.graph.planned"),)), rules=resources)
    result = execute_rule_plan(plan, RuleContext(facts={"graph":graph}, scope={"level":"graph"}), handlers=workflow_topic_handlers()).results["check"]
    assert result.state == "completed"
    assert any(isinstance(event, PlannedImplementationCheck) for event in result.records["events"].value)
    json.dumps(result.to_dict())


@pytest.mark.parametrize("variant",["dataclass","set"])
def test_native_input_record_types_are_not_merged_by_their_json_projection(variant):
    from dataclasses import make_dataclass
    provider = RuleDescriptor("native.provider",scope="call",outputs={"data":"native.v1"})
    consumer = RuleDescriptor("native.consumer",scope="source",inputs={"data":"native.v1"})
    selection = RulesetDescriptor("native",calls=(RuleCall("provide",rule_id=provider.id),RuleCall("consume",rule_id=consumer.id)),
        relations=(RuleRelation("consume","provide","requires",bindings={"data":"data"}),))
    first = make_dataclass("Payload",[("value",int)],frozen=True)
    second = make_dataclass("Payload",[("value",int)],frozen=True)
    values = [first(1),second(1),{"value":1}] if variant == "dataclass" else [[1],frozenset({1})]
    pending, seen = iter(values), []
    def provide(*_):
        return RuleResult(records={"data":RuleRecord("native.v1",next(pending))})
    def consume(context,inputs,params):
        seen.append(type(inputs["data"].value))
        return RuleResult()
    plan = compile_ruleset(selection,rules={item.id:item for item in (provider,consumer)})
    context = RuleContext(subject={"source_identity":"unchanged source"})
    cache = {}
    results = [execute_rule_plan(plan,context,handlers={provider.id:provide,consumer.id:consume},source_cache=cache) for _ in values]
    wire = [result.results["provide"].records["data"].to_dict() for result in results]
    assert all(item == wire[0] for item in wire)
    assert len(seen) == len(values) and all(result.executed == ("provide","consume") for result in results)
    # The ordinary JSON input remains cacheable; native values never alias it.
    assert len(cache) == 1


def test_record_cache_eligibility_visits_shared_json_containers_once():
    from vibeflow.core.rules.fingerprint import cacheable_record_value
    shared = 1
    for _ in range(64):
        shared = (shared,shared)
    memo = {}
    assert cacheable_record_value(shared,memo)
    assert len(memo) == 64 and all(memo.values())
