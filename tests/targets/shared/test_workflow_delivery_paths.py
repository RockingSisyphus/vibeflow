"""Regression graphs compiled through Core, checked by the shared Target Rules."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from vibeflow.core.compiler import compile_core
from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.core.flow import EdgeSpec, GraphConfig, NodeSpec, PipelineInputSpec
from vibeflow.core.models import CoreCompileRequest, ImplementationFact, ImplementationFacts, TargetFeatureSet
from vibeflow.targets.shared.quality_support.workflow_rules.flow_data import append_data_contract_warnings
from vibeflow.targets.shared.quality_support.workflow_rules.joins import append_join_policy_health


def node(name, kind="process", *, supplies=False, consumes=False):
    return NodeSpec(name, "probe." + name, flow_kind=kind,
                    provides=(DataProvider(name + ".out", "value"),) if supplies else (),
                    requires=(DataRequirement("value", "exactly_one"),) if consumes else ())


def review(graph):
    facts = ImplementationFacts(tuple(ImplementationFact(n.type_used, flow_kind=n.flow_kind,
                                requires=n.requires, provides=n.provides) for n in graph.nodes))
    result = compile_core(CoreCompileRequest(graph, facts, TargetFeatureSet("probe", frozenset())))
    state = SimpleNamespace(errors=[], warnings=[])
    append_data_contract_warnings(result.workflow.graph, result.compiled_graph, state)
    append_join_policy_health(result.workflow.graph, result.compiled_graph, state)
    return {item.rule_id for item in (*state.errors, *state.warnings)}


def fork(*, direct=False, bypass=False, right_condition="choice == 'right'"):
    nodes = (node("start", "terminal"), node("route", "decision" if right_condition else "process", supplies=direct),
             node("left", supplies=True), node("middle"), node("right", supplies=True),
             node("join", consumes=True), node("end", "terminal"))
    edges = (EdgeSpec("start", "route", schedule=True),
             EdgeSpec("route", "join" if direct else "left", when="choice == 'left'", schedule=True),
             EdgeSpec("route", "middle", when=right_condition, schedule=True),
             EdgeSpec("middle", "right", schedule=True), EdgeSpec("right", "join", schedule=True),
             EdgeSpec("join", "end", schedule=True))
    if not direct:
        edges += (EdgeSpec("left", "join", schedule=True),)
    if bypass:
        edges += (EdgeSpec("start", "right", schedule=True),)
    return GraphConfig(nodes, edges)


@pytest.mark.parametrize("direct", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_indirect_exclusive_delivery_and_mixed_join_pass(direct, reverse):
    graph = fork(direct=direct)
    if reverse:
        graph = replace(graph, edges=tuple(reversed(graph.edges)))
    assert not review(graph) & {"GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS", "GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL"}


@pytest.mark.parametrize("direct", [False, True])
@pytest.mark.parametrize("change", ["bypass", "overlap", "unconditional", "different_key"])
def test_possible_double_delivery_remains_reported(direct, change):
    conditions = {"overlap": "choice == 'left'", "unconditional": "", "different_key": "other == 'right'"}
    codes = review(fork(direct=direct, bypass=change == "bypass",
                        right_condition=conditions.get(change, "choice == 'right'")))
    assert "GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS" in codes
    if direct:
        assert "GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL" in codes


def test_multiple_alternative_values_do_not_hide_overlapping_paths():
    graph = fork()
    graph = replace(graph, nodes=(*graph.nodes, node("other")),
                    edges=(*graph.edges, EdgeSpec("route", "other", when="choice == 'right'", schedule=True),
                           EdgeSpec("other", "left", schedule=True)))
    assert "GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS" in review(graph)


@pytest.mark.parametrize("control", [True, False])
def test_initial_input_uses_empty_start_schedule_edge(control):
    start, extra, join, end = node("start", "terminal"), node("extra", supplies=True), node("join", consumes=True), node("end", "terminal")
    extra = replace(extra, provides=(DataProvider("extra.out", "extra"),))
    join = replace(join, requires=(*join.requires, DataRequirement("extra", "exactly_one")))
    graph = GraphConfig((start, extra, join, end),
        (EdgeSpec("start", "extra", schedule=True, transfer=False),
         EdgeSpec("extra", "join", schedule=True), EdgeSpec("join", "end", schedule=True))
        + ((EdgeSpec("start", "join", schedule=True, transfer=False),) if control else ()),
        inputs=(PipelineInputSpec("seed", "value", required=True),))
    codes = review(graph)
    assert ("GRAPH.DATA.MISSING_DIRECT_PROVIDER" in codes) == (not control)
    assert ("GRAPH.DATA.RUNTIME_REQUIREMENT_UNREACHABLE" in codes) == (not control)
