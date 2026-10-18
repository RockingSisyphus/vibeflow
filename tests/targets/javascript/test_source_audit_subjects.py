"""Declaration source auditing does not create executable call paths."""
import pytest

from vibeflow.core.flow import GraphConfig, NodeSpec, NodesetSpec
from vibeflow.targets.javascript.quality.rules import node_type_calls, source_node_calls


@pytest.mark.parametrize("status", ["planned", "implemented"])
def test_nodeset_declaration_owners_cover_sources_without_activating_planned_calls(status):
    body = NodesetSpec("example.body", "Body", "Source audit fixture", (), (),
        GraphConfig(nodes=(NodeSpec("worker", "example.worker"),
                          NodeSpec("future", "example.future", status="planned"))))
    graph = GraphConfig(nodes=(NodeSpec("body", "example.body", status=status),),
        nodesets={"example.body":body})
    calls = node_type_calls(graph)
    sources = source_node_calls(graph)
    assert "example.future" not in sources
    if status == "planned":
        assert calls == {}
        assert sources == {"example.worker":[]}
    else:
        assert sources == calls
        assert sources["example.worker"] == [("body", "worker")]
