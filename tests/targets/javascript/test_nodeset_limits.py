from __future__ import annotations

import pytest
from types import SimpleNamespace

from vibeflow.targets.javascript.build.nodeset_limits import (
    check_nodeset_depth,
    nodeset_width_warnings,
)
from vibeflow.targets.javascript.frontend.errors import ProjectBuildError
from vibeflow.targets.javascript.build.project_paths import javascript_options
from vibeflow.tooling.project.graph_config import parse_graph_config


def _node(node_id: str, type_key: str) -> dict[str, object]:
    return {
        "id": node_id,
        "type_used": type_key,
        "display_name": node_id,
        "description": f"Runs {type_key}.",
        "status": "planned",
        "flow_kind": "process",
        "requires": [],
        "provides": [],
    }


def _graph(depth: int, width: int = 1, *, use_chain: bool = True):
    nodesets = []
    for index in range(depth):
        child = f"example.depth.{index - 1}" if index else "example.placeholder"
        nodesets.append(
            {
                "type_key": f"example.depth.{index}",
                "display_name": f"Depth {index}",
                "description": "A planned nested workflow.",
                "status": "planned",
                "requires": [],
                "provides": [],
                "pipeline": {"nodes": [_node(f"step-{n}", child) for n in range(width if index == 0 else 1)]},
            }
        )
    return parse_graph_config(
        {
            "nodesets": nodesets,
            "pipeline": {"nodes": [
                _node("top", f"example.depth.{depth - 1}")
                if use_chain else _node("unrelated", "example.placeholder")
            ]},
        }
    )


def _mixed_graph(depth: int):
    nodesets = []
    for index in range(depth):
        child = f"example.depth.{index - 1}" if index else "example.future"
        call = _node("call", child)
        if index == 2:
            call["type_used"] = "vibeflow.loop.while"
            call["loop"] = {
                "body": child, "max_iterations": 10, "stop_after": 1,
                "outputs": [],
            }
        if index == 3:
            call["async"] = "detached"
        calls = [call]
        if index == depth - 1 and index > 0:
            calls.append(_node("branch", "example.depth.0"))
        nodesets.append({
            "type_key": f"example.depth.{index}",
            "display_name": f"Depth {index}",
            "description": "A planned mixed dependency group.",
            "status": "planned", "requires": [], "provides": [],
            "pipeline": {"nodes": calls},
        })
    return parse_graph_config({
        "nodesets": nodesets,
        "pipeline": {"nodes": [_node("top", f"example.depth.{depth - 1}")]},
    })


def test_javascript_nodeset_depth_rejects_five_planned_layers() -> None:
    check_nodeset_depth(_graph(4))
    with pytest.raises(ProjectBuildError) as captured:
        check_nodeset_depth(_graph(5))
    assert captured.value.code == "NODESET.NESTING.DEPTH_EXCEEDED"
    assert captured.value.diagnostics[0]["actual_depth"] == 5


def test_javascript_nodeset_depth_checks_unused_planned_definition() -> None:
    with pytest.raises(ProjectBuildError) as captured:
        check_nodeset_depth(_graph(5, use_chain=False))
    assert captured.value.code == "NODESET.NESTING.DEPTH_EXCEEDED"
    assert captured.value.diagnostics[0]["owner"] == "nodeset:example.depth.4"
    assert captured.value.diagnostics[0]["actual_depth"] == 5


def test_javascript_nodeset_mixed_loop_async_branch_depth() -> None:
    check_nodeset_depth(_mixed_graph(4))
    with pytest.raises(ProjectBuildError) as captured:
        check_nodeset_depth(_mixed_graph(5))
    details = captured.value.diagnostics[0]
    assert details["actual_depth"] == 5
    assert details["chain"] == tuple(f"example.depth.{index}" for index in range(4, -1, -1))
    assert [item["kind"] for item in details["calls"]] == [
        "nodeset", "nodeset", "nodeset", "loop_body", "nodeset",
    ]


@pytest.mark.parametrize(
    ("targets", "cycle"),
    [
        ({"example.a": "example.a"}, ("example.a", "example.a")),
        ({"example.a": "example.b", "example.b": "example.a"},
         ("example.a", "example.b", "example.a")),
    ],
)
def test_javascript_nodeset_recursion_uses_shared_rule(targets, cycle) -> None:
    graph = parse_graph_config({
        "nodesets": [{
            "type_key": owner,
            "display_name": owner,
            "description": "A planned recursive group.",
            "status": "planned",
            "requires": [], "provides": [],
            "pipeline": {"nodes": [_node("call", target)]},
        } for owner, target in targets.items()],
        "pipeline": {"nodes": [_node("unrelated", "example.future")]},
    })
    with pytest.raises(ProjectBuildError) as captured:
        check_nodeset_depth(graph)
    assert captured.value.code == "NODESET.RECURSION"
    assert captured.value.diagnostics[0]["cycle"] == cycle


def test_javascript_nodeset_width_warning_includes_planned_body() -> None:
    assert nodeset_width_warnings(_graph(1, width=10)) == ()
    warnings = nodeset_width_warnings(_graph(1, width=11))
    assert warnings[0]["rule_id"] == "NODESET.SMELL.TOO_WIDE"
    assert warnings[0]["details"] == {"node_count": 11, "limit": 10}


def test_javascript_nodeset_depth_override_is_explicit_and_validated() -> None:
    root = SimpleNamespace(project_config={"javascript": {"nodeset_max_depth": 5}})
    check_nodeset_depth(_graph(5), max_depth=javascript_options(root)["nodeset_max_depth"])
    root.project_config["javascript"]["nodeset_max_depth"] = True
    with pytest.raises(ProjectBuildError, match="positive integer"):
        javascript_options(root)
