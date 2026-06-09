from tests.unit.strict_support import *


def test_compiler_merges_duplicate_explicit_and_data_edges_with_loop_limits() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "edges": [
                    {"from": "add", "to": "copy", "max_executions": 2},
                    {"from": "copy", "to": "add", "loop": "counter_loop"},
                ],
                "loops": [
                    {
                        "name": "counter_loop",
                        "edges": [["copy", "add"]],
                        "nodes": ["add", "copy"],
                        "max_iterations": 3,
                    }
                ],
            }
        }
    )

    compiled = GraphCompiler().compile(graph)

    assert [edge.pair for edge in compiled.effective_edges] == [("add", "copy"), ("copy", "add")]
    assert compiled.edge_execution_limits == {("add", "copy"): 4, ("copy", "add"): 3}
    assert [(edge.source, edge.target, edge.loop) for edge in compiled.loop_edges] == [("copy", "add", "counter_loop")]


def test_compiler_rejects_loop_that_references_missing_edge_between_known_nodes() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.copy"]},
                ],
                "loops": [
                    {
                        "name": "missing_edge_loop",
                        "edges": [["copy", "seed"]],
                        "max_iterations": 2,
                    }
                ],
            }
        }
    )

    with pytest.raises(GraphCompileError, match="references missing edge copy->seed"):
        GraphCompiler().compile(graph)
