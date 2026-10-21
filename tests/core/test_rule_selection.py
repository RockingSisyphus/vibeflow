"""Observable selection precedence and disjoint graph coverage."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from vibeflow.core.flow import GraphConfig, LoopSpec, NodeCallSpec, NodesetTypeSpec
from vibeflow.core.rules import RuleCall, RuleDescriptor, RulesetDescriptor, compile_ruleset, RuleGraphError
from vibeflow.core.rules.planning import graph_rule_tasks, scoped_graph
from vibeflow.core.rules.selection import resolve_node_selection, selection_data


def definition(key, graph):
    return NodesetTypeSpec(key, key, key, (), (), graph)


def test_node_replacement_and_explicit_empty_are_per_call():
    descriptor = SimpleNamespace(id="test.node", rulesets=("static",))
    assert resolve_node_selection(descriptor, NodeCallSpec("a", "test.node")).references == ("static",)
    selected = resolve_node_selection(descriptor, NodeCallSpec("b", "test.node", rulesets=("dynamic",)))
    assert selected.references == ("dynamic",) and selected.replaced == ("static",)
    assert resolve_node_selection(descriptor, NodeCallSpec("c", "test.node", rulesets=())).references == ()
    assert descriptor.rulesets == ("static",)


def test_direct_rule_reference_and_single_plan_scope():
    rule = RuleDescriptor("test.rule", params_schema={"count": {"type": "integer"}}, params_defaults={"count": 1})
    graph = GraphConfig((), rulesets=({"rule_id": rule.id, "params": {"count": 10}},))
    assert selection_data(graph.rulesets) == [{"rule_id": rule.id, "params": {"count": 10}}]
    plan = compile_ruleset(graph.rulesets[0], rules={rule.id: rule}, rulesets={})
    assert plan.invocations[0].params["count"] == 10
    inner = RulesetDescriptor("inner", calls=(RuleCall("rule", rule_id=rule.id),), graph_scope="current_graph")
    outer = RulesetDescriptor("outer", calls=(RuleCall("nested", ruleset_id=inner.id),), graph_scope="effective_subtree")
    with pytest.raises(RuleGraphError, match="GRAPH_SCOPE.CONFLICT"):
        compile_ruleset(outer.id, rules={rule.id: rule}, rulesets={inner.id: inner, outer.id: outer})
    plan = compile_ruleset(outer.id, rules={rule.id: rule}, rulesets={inner.id: replace(inner, graph_scope=None), outer.id: outer})
    assert plan.graph_scope == "effective_subtree"


@pytest.mark.parametrize("scope", ["current_graph", "effective_subtree"])
def test_repeated_calls_inheritance_and_explicit_boundary(scope):
    selected = RulesetDescriptor("default", workflow_default=True, graph_scope=scope)
    child = definition("child", GraphConfig((NodeCallSpec("leaf", "node"),)))
    override = definition("override", GraphConfig((NodeCallSpec("inner", "child"),), nodeset_types={"child": child}, rulesets=()))
    graph = GraphConfig((NodeCallSpec("first", "child"), NodeCallSpec("second", "child"), NodeCallSpec("boundary", "override")),
        nodeset_types={"child": child, "override": override})
    tasks = graph_rule_tasks(graph, {selected.id: selected})
    assert [task.subject.call_path for task in tasks] == ([(), ("first",), ("second",)] if scope == "current_graph" else [()])
    root = tasks[0]
    assert root.boundaries == (("boundary",),)
    covered = [subject.call_path for task in tasks for subject in task.subjects]
    assert covered == [(), ("first",), ("second",)]
    assert all(not value.graph.nodes for value in scoped_graph(root).nodeset_types.values())
    assert len(child.graph.nodes) == 1


def test_same_explicit_selection_starts_a_new_subtree_and_unused_is_independent():
    rule = RulesetDescriptor("default", workflow_default=True, graph_scope="effective_subtree")
    child = definition("child", GraphConfig((NodeCallSpec("leaf", "node"),), rulesets=(rule.id,)))
    unused = definition("unused", GraphConfig((NodeCallSpec("unused_leaf", "node"),)))
    graph = GraphConfig((NodeCallSpec("call", "child"),), nodeset_types={"child": child, "unused": unused})
    tasks = graph_rule_tasks(graph, {rule.id: rule})
    assert len(tasks) == 3
    assert tasks[0].boundaries == (("call",),)
    assert tasks[1].selection.source == "dynamic"
    assert tasks[2].subject.declaration_only and tasks[2].selection.source == "static"


def test_current_graph_retains_inherited_nodeset_external_contract():
    rule = RulesetDescriptor("default",workflow_default=True)
    inner = definition("inner",GraphConfig((NodeCallSpec("leaf","node"),)))
    outer = definition("outer",GraphConfig((NodeCallSpec("middle","inner"),)))
    root = GraphConfig((NodeCallSpec("outer","outer"),),nodeset_types={"outer":outer,"inner":inner})
    task = next(item for item in graph_rule_tasks(root,{rule.id:rule}) if item.subject.call_path == ("outer",))
    assert set(scoped_graph(task).nodeset_types) == {"inner"}
    assert scoped_graph(task).nodeset_types["inner"].graph.nodes == ()


def test_scoped_graph_preserves_first_reference_order_with_repeated_calls_and_loops():
    rule = RulesetDescriptor("default", workflow_default=True)
    definitions = {key: definition(key, GraphConfig((NodeCallSpec("leaf", "node"),)))
                   for key in ("alpha", "beta", "gamma")}
    graph = GraphConfig((NodeCallSpec("first", "gamma"),
        NodeCallSpec("loop", "vibeflow.loop.while", loop=LoopSpec(body="beta")),
        NodeCallSpec("again", "gamma"), NodeCallSpec("last", "alpha"), NodeCallSpec("plain", "node")),
        nodeset_types=definitions)
    task = graph_rule_tasks(graph, {rule.id: rule})[0]
    scoped = scoped_graph(task)
    assert tuple(scoped.nodeset_types) == ("gamma", "beta", "alpha")
    assert all(not value.graph.nodes for value in scoped.nodeset_types.values())
    assert all(value.graph.nodes for value in graph.nodeset_types.values())
