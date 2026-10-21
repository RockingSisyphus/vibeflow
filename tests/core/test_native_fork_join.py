"""Graph completion and separate fork/join duties have no task exceptions."""
from dataclasses import replace
import pytest
from vibeflow.core.flow import GraphConfig,NodeCallSpec,EdgeSpec
from vibeflow.core.models import ImplementationFact,ImplementationFacts,CoreCompileRequest
from vibeflow.core.compiler import compile_core,GraphCompileError
from tests.fixtures.support.declarations import native_registry
from vibeflow.core.descriptors import NodeDescriptor,NodeContractDescriptor
from vibeflow.targets.python.quality.workflow.validation import validate_graph_health


def _graph(extra_edges=(),extra_nodes=()):
    graph=GraphConfig(nodes=(NodeCallSpec("start","boundary"),NodeCallSpec("left","work"),NodeCallSpec("right","work"),
        NodeCallSpec("collect","work",join_policy="all"),NodeCallSpec("end","boundary"),*extra_nodes),
        edges=tuple(EdgeSpec(a,b,schedule=True) for a,b in [("start","left"),("start","right"),("left","collect"),("right","collect"),("collect","end"),*extra_edges]))
    return graph


def _compile(graph):
    facts=ImplementationFacts((ImplementationFact("boundary",flow_kind="terminal"),ImplementationFact("work",flow_kind="process")),strict=True)
    return compile_core(CoreCompileRequest(graph=graph,implementation_facts=facts))


def test_all_branches_with_explicit_collector_are_valid():
    _compile(_graph())


def test_path_bypassing_collector_cannot_qualify_as_a_joined_fanout():
    result=_compile(_graph((("left","early_end"),),(NodeCallSpec("early_end","boundary"),)))
    assert "GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT" in {finding.rule_id for finding in result.findings}


def test_collector_cannot_also_dispatch_next_parallel_stage():
    graph=_graph((("collect","next_left"),("collect","next_right"),("next_left","next_join"),("next_right","next_join"),("next_join","end")),
        (NodeCallSpec("next_left","work"),NodeCallSpec("next_right","work"),NodeCallSpec("next_join","work",join_policy="all")))
    graph=replace(graph,edges=tuple(edge for edge in graph.edges if edge.pair!=("collect","end")))
    from types import SimpleNamespace
    from vibeflow.targets.shared.quality_support.workflow_rules.joins import append_join_policy_health
    state = SimpleNamespace(errors=[], warnings=[])
    append_join_policy_health(graph, _compile(graph).compiled_graph, state)
    assert any(finding.rule_id == "GRAPH.JOIN.FORK_CONFLICT" and finding.severity == "error"
        for finding in state.errors)


def test_unconnected_worker_still_reports_cannot_reach_end():
    class Empty:
        def run_pure(self,inputs,params):return {}
    registry=native_registry()
    for key,kind in (("boundary","terminal"),("work","process")):
        registry.register(NodeDescriptor(key,key,key,"1",kind,contract=NodeContractDescriptor(),rulesets=(), node_type="vibeflow.node"),Empty)
    graph=GraphConfig(nodes=(NodeCallSpec("start","boundary"),NodeCallSpec("worker","work"),NodeCallSpec("end","boundary")),
        edges=(EdgeSpec("start","worker"),EdgeSpec("start","end",schedule=False)))
    health=validate_graph_health(graph,registry=registry)
    assert "GRAPH.FLOW.CANNOT_REACH_END" in {item.rule_id for item in health.errors}


def test_later_all_marker_cannot_hide_an_implicit_early_merge():
    graph=_graph((("collect","marker"),("marker","end")),(NodeCallSpec("marker","work",join_policy="all"),))
    graph=replace(graph,nodes=tuple(replace(node,join_policy="safe_any") if node.id=="collect" else node for node in graph.nodes),
        edges=tuple(edge for edge in graph.edges if edge.pair!=("collect","end")))
    assert "GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT" in {finding.rule_id for finding in _compile(graph).findings}
