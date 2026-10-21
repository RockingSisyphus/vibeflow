"""Declaration source auditing does not create executable call paths."""
import pytest

from vibeflow.core.flow import GraphConfig, NodeCallSpec, NodesetTypeSpec
from vibeflow.targets.javascript.quality.rules import node_definition_calls, source_node_calls


@pytest.mark.parametrize("status", ["planned", "implemented"])
def test_nodeset_declaration_owners_cover_sources_without_activating_planned_calls(status):
    body = NodesetTypeSpec("example.body", "Body", "Source audit fixture", (), (),
        GraphConfig(nodes=(NodeCallSpec("worker", "example.worker"),
                          NodeCallSpec("future", "example.future", status="planned"))))
    graph = GraphConfig(nodes=(NodeCallSpec("body", "example.body", status=status),),
        nodeset_types={"example.body":body})
    calls = node_definition_calls(graph)
    sources = source_node_calls(graph)
    assert "example.future" not in sources
    if status == "planned":
        assert calls == {}
        assert sources == {"example.worker":[]}
    else:
        assert sources == calls
        assert sources["example.worker"] == [("body", "worker")]
