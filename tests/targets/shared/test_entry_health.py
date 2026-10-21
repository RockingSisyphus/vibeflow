"""Entry-specific contracts must not hide nodes outside every entry."""
from types import SimpleNamespace

import pytest

from vibeflow.core.flow import GraphConfig, NodeCallSpec, NodeMetadata, EdgeSpec
from vibeflow.core.models import CoreCompileRequest, ImplementationFact, ImplementationFacts
from vibeflow.core.compiler import compile_core
from vibeflow.core.workflows.entries import EntrySpec
from vibeflow.targets.shared.rule_support.graph import _flow


@pytest.mark.parametrize("kind", ["terminal", "process"])
def test_declared_entries_do_not_hide_unreachable_nodes(kind):
    graph = GraphConfig(tuple(NodeCallSpec(key, node_type, metadata=NodeMetadata(key, key)) for key, node_type
        in [("start", "terminal"), ("end", "terminal"), ("orphan", kind)]), (EdgeSpec("start", "end"),),
        entries={"main": EntrySpec("start")})
    facts = ImplementationFacts(tuple(ImplementationFact(name, flow_kind=name) for name in ("terminal", "process")))
    compilation = compile_core(CoreCompileRequest(graph, facts))
    values = {"graph": compilation.workflow.graph, "compiled": compilation.compiled_graph}
    context = SimpleNamespace(facts={}, require=values.__getitem__)
    findings = _flow(context, {}, {}).findings
    codes = {item.rule_id for item in findings if item.object_id == "orphan"}
    assert "GRAPH.FLOW.UNREACHABLE_FROM_START" in codes
    assert "GRAPH.FLOW.ORPHAN_NODE" in codes
    if kind == "process":
        assert "GRAPH.FLOW.CANNOT_REACH_END" in codes
