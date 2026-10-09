"""Context derivation reuses owned snapshots without trusting raw proxies."""

from dataclasses import replace
from types import MappingProxyType

import pytest

from tests.fixtures.python.context_reuse.probe import observe
from vibeflow.core.rules import RuleContext, RuleCall, RuleDescriptor, RuleResult, RulesetDescriptor, compile_ruleset, execute_rule_plan


def test_sandbox_derivation_traversal_bound_and_readonly_controls():
    result = observe()
    assert result["matched"], result


def test_derived_contexts_isolate_new_mutable_inputs_and_keep_existing_snapshot():
    original = {"values": [1]}
    base = RuleContext(facts=original)
    subjects = []
    for index in range(100):
        raw = {"values": [index]}
        derived = replace(base, subject=raw)
        raw["values"].append("changed")
        assert derived.facts is base.facts
        subjects.append(derived.subject)
    assert [item["values"] for item in subjects] == [(index,) for index in range(100)]
    original["values"].append(2)
    refreshed = replace(base, facts=original)
    assert refreshed.facts["values"] == (1, 2)
    assert base.facts["values"] == (1,)
    assert RuleContext(facts=base.facts).facts is not base.facts


@pytest.mark.parametrize("field", ["facts", "subject", "scope"])
def test_unknown_mapping_proxies_are_recursively_frozen(field):
    base = RuleContext(facts={"shared": [1]})
    backing = {"values": [{"items": [2]}]}
    derived = replace(base, **{field:MappingProxyType(backing)})
    backing["values"][0]["items"].append(3)
    snapshot = getattr(derived, field)
    assert snapshot["values"][0]["items"] == (2,)
    with pytest.raises(TypeError):
        snapshot["values"][0]["items"][0] = 4


def test_rule_engine_reuses_analysis_and_keeps_call_source_boundaries():
    rules = [RuleDescriptor("call"), RuleDescriptor("source",scope="source")]
    ruleset = RulesetDescriptor("all", calls=tuple(RuleCall(item.id,rule_id=item.id) for item in rules))
    plan = compile_ruleset("all",rules={item.id:item for item in rules},rulesets={ruleset.id:ruleset})
    base = RuleContext(facts={"analysis":{"values":[1]},"call":{"id":"n"}},
        subject={"owner":"wf","call_id":"n"},scope={"workflow":"wf"})
    seen = {}
    def check(context, inputs, params):
        seen["source" if "call" not in context.facts else "call"] = context
        return RuleResult()
    result = execute_rule_plan(plan,base,handlers={"call":check,"source":check})
    assert result.status == "PASS"
    assert seen["call"].subject["rule_call_id"] == "call"
    assert "call_id" not in seen["source"].subject
    assert "workflow" not in seen["source"].scope
    assert seen["call"].facts is base.facts
    assert seen["source"].facts["analysis"] is base.facts["analysis"]
