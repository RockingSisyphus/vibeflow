"""Nodeset expansion is validated display metadata, independent of graph health."""

from dataclasses import replace

import pytest

from vibeflow.core.config.graph import parse_graph_config_data
from vibeflow.core.flow import GraphConfig, GraphConfigError, NodeCallSpec, NodesetTypeSpec
from vibeflow.targets.shared.quality_support.nodeset_types import nodeset_quality_findings


def node(identifier, kind):
    return {"id": identifier, "definition_id": kind, "display_name": identifier, "description": identifier}


def definition(key="test.group", **options):
    return {"type_key": key, "display_name": key, "description": key, "requires": [], "provides": [],
            "pipeline": {"nodes": [node("inside", "test.leaf")]}, **options}


def graph_config(**options):
    return {"nodeset_types": [definition(**options)], "pipeline": {"nodes": [node("group", "test.group")]}}


@pytest.mark.parametrize("options,expected", [({}, True), ({"expand": True}, True), ({"expand": False}, False)])
def test_nodeset_expand_default_and_boolean_values(options, expected):
    graph = parse_graph_config_data(graph_config(**options))
    assert graph.nodeset_types["test.group"].expand is expected
    assert graph.nodeset_types["test.group"].graph.nodes[0].id == "inside"


@pytest.mark.parametrize("invalid", [None, 0, 1, -1, 1.0, "false", "true", [], {}])
def test_config_does_not_coerce_invalid_expand_values(invalid):
    with pytest.raises(GraphConfigError, match=r"nodeset_types\[0\]\.expand must be a boolean"):
        parse_graph_config_data(graph_config(expand=invalid))


@pytest.mark.parametrize("invalid", [None, 0, 1, -1, 1.0, "false", "true", [], {}])
def test_direct_nodeset_constructor_does_not_coerce_expand(invalid):
    with pytest.raises(ValueError, match="nodeset expand must be a boolean"):
        NodesetTypeSpec("test.group", "Group", "Group", (), (), GraphConfig((NodeCallSpec("inside", "test.leaf"),)), expand=invalid)


def test_expand_is_owned_by_the_definition_and_shared_by_nodeset_and_loop_calls():
    config = graph_config(expand=False)
    config["nodeset_types"].append(definition("test.other", expand=True))
    config["pipeline"]["nodes"] += [node("second", "test.group"), node("other", "test.other"),
        {**node("loop", "vibeflow.loop.while"), "requires": [], "provides": [],
         "loop": {"body": "test.group", "max_iterations": 1, "stop_after": 1}}]
    graph = parse_graph_config_data(config)
    assert graph.nodeset_types["test.group"].expand is False
    assert graph.nodeset_types["test.other"].expand is True
    assert graph.nodes[-1].loop.body == "test.group"
    assert graph.nodeset_types["test.group"].graph.nodes[0].id == "inside"
    assert not hasattr(graph.nodes[0], "expand")


def test_expand_on_a_node_call_is_rejected_but_a_business_parameter_is_legal():
    config = graph_config()
    config["pipeline"]["nodes"][0]["expand"] = False
    with pytest.raises(GraphConfigError, match=r"pipeline.nodes\[0\]\.expand belongs on the Nodeset definition"):
        parse_graph_config_data(config)
    del config["pipeline"]["nodes"][0]["expand"]
    config["pipeline"]["nodes"][0]["config"] = {"expand": False}
    assert parse_graph_config_data(config).nodes[0].params == {"expand": False}


def test_collapsed_definition_does_not_hide_nested_depth_or_width_findings():
    config = graph_config()
    config["nodeset_types"][0]["pipeline"]["nodes"] = [node("child", "test.child")]
    config["nodeset_types"].append(definition("test.child"))
    config["nodeset_types"][1]["pipeline"]["nodes"].append(node("second", "test.leaf"))
    expanded = parse_graph_config_data(config)
    collapsed = replace(expanded, nodeset_types={key: replace(item, expand=False) for key, item in expanded.nodeset_types.items()})
    before = nodeset_quality_findings(expanded, max_depth=1, warn_width=1)
    after = nodeset_quality_findings(collapsed, max_depth=1, warn_width=1)
    assert after == before
    assert {item.rule_id for item in after} >= {"NODESET.NESTING.DEPTH_EXCEEDED", "NODESET.SMELL.TOO_WIDE"}
