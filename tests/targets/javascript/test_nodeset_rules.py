from __future__ import annotations

import pytest
from types import SimpleNamespace

from vibeflow.core.rules import RuleCall, RuleContext, RulesetDescriptor, compile_ruleset, execute_rule_plan
from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins
from vibeflow.targets.shared.bindings import native_binding
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


def _selected_findings(graph, *, max_depth=4, enabled=True):
    loaded = load_builtin_plugins("javascript")
    ruleset = RulesetDescriptor("fixture.nodesets", calls=(RuleCall("nodesets", rule_id="vibeflow.graph.nodesets",
        params={"nodeset_max_depth": max_depth}),) if enabled else (), entrypoints={"static": ("nodesets",) if enabled else ()})
    plan = compile_ruleset(ruleset.id, rules=loaded.catalogs.rules, rulesets={ruleset.id: ruleset}, entrypoint="static")
    result = execute_rule_plan(plan, RuleContext(facts={"graph": graph}, target="javascript"),
        handlers={"vibeflow.graph.nodesets": native_binding(loaded.catalogs, "rule", "vibeflow.graph.nodesets")})
    return result.findings


def _errors(graph, **kwargs):
    return tuple(item for item in _selected_findings(graph, **kwargs) if item.severity == "error")


def test_selected_nodeset_rule_checks_depth_and_empty_selection_removes_review():
    assert _errors(_graph(4)) == ()
    found = _errors(_graph(5))
    assert found[0].code == "NODESET.NESTING.DEPTH_EXCEEDED"
    assert found[0].details["actual_depth"] == 5
    assert _selected_findings(_graph(5), enabled=False) == ()


def test_selected_rule_checks_unused_planned_definition():
    found = _errors(_graph(5, use_chain=False))
    assert found[0].details["owner"] == "nodeset:example.depth.4"
    assert found[0].details["actual_depth"] == 5


def test_selected_rule_checks_mixed_loop_async_branch_depth():
    assert _errors(_mixed_graph(4)) == ()
    details = _errors(_mixed_graph(5))[0].details
    assert details["actual_depth"] == 5
    assert details["chain"] == tuple(f"example.depth.{index}" for index in range(4, -1, -1))
    assert [item["kind"] for item in details["calls"]] == ["nodeset", "nodeset", "nodeset", "loop_body", "nodeset"]


@pytest.mark.parametrize("targets,cycle", [
    ({"example.a": "example.a"}, ("example.a", "example.a")),
    ({"example.a": "example.b", "example.b": "example.a"}, ("example.a", "example.b", "example.a")),
])
def test_selected_nodeset_rule_reports_recursion(targets, cycle):
    graph = parse_graph_config({"nodesets": [{"type_key": owner, "display_name": owner,
        "description": "A planned recursive group.", "status": "planned", "requires": [], "provides": [],
        "pipeline": {"nodes": [_node("call", target)]}} for owner, target in targets.items()],
        "pipeline": {"nodes": [_node("unrelated", "example.future")]}})
    found = _errors(graph)
    assert found[0].code == "NODESET.RECURSION"
    assert found[0].details["cycle"] == cycle


def test_selected_rule_width_warning_includes_planned_body():
    assert _selected_findings(_graph(1, width=10)) == ()
    warning = _selected_findings(_graph(1, width=11))[0]
    assert warning.code == "NODESET.SMELL.TOO_WIDE"
    assert warning.details == {"node_count": 11, "limit": 10}


def test_selected_rule_depth_override_and_project_default_validation():
    root = SimpleNamespace(project_config={"javascript": {"nodeset_max_depth": 5}})
    assert _errors(_graph(5), max_depth=javascript_options(root)["nodeset_max_depth"]) == ()
    root.project_config["javascript"]["nodeset_max_depth"] = True
    with pytest.raises(ProjectBuildError, match="positive integer"):
        javascript_options(root)
