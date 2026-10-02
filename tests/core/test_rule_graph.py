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
