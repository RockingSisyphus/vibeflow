"""Nodeset files and formal schema retain the expansion choice as a boolean."""

import json
from importlib.resources import files

import pytest

from tests.core.test_nodeset_expand import definition, graph_config, node
from vibeflow.core.config.graph import parse_graph_config_data
from vibeflow.targets.javascript.build.plugin_hooks import json_projection
from vibeflow.tooling.project.config_loader import load_config_document
from vibeflow.tooling.project.config_schema import collect_config_schema_findings


@pytest.mark.parametrize("invalid", [None, 0, 1, 1.0, "false", "true", [], {}])
def test_formal_schema_rejects_non_boolean_nodeset_expand(invalid):
    findings = collect_config_schema_findings(definition(expand=invalid))
    assert any(item.rule_id == "CONFIG.SCHEMA.NODESET_EXPAND" and item.object_id == "nodeset.expand" for item in findings)


@pytest.mark.parametrize("options", [{}, {"expand": True}, {"expand": False}])
def test_formal_schema_accepts_default_true_and_explicit_booleans(options):
    assert collect_config_schema_findings(definition(**options)) == ()


def test_published_nodeset_schema_declares_boolean_and_true_default():
    schema = json.loads(files("vibeflow.tooling.project").joinpath("schema/nodeset_type.schema.json").read_text())
    assert schema["properties"]["expand"]["type"] == "boolean"
    assert schema["properties"]["expand"]["default"] is True
    assert "expand" not in schema["required"]


def test_formal_schema_diagnoses_expand_on_the_call_not_on_business_params():
    config = graph_config()
    config["__vibeflow_expanded_nodesets__"] = True
    config["pipeline"]["nodes"][0]["expand"] = False
    findings = collect_config_schema_findings(config)
    assert any(item.rule_id == "CONFIG.SCHEMA.NODESET_EXPAND_LOCATION" and item.object_id == "pipeline.nodes[0].expand" for item in findings)
    del config["pipeline"]["nodes"][0]["expand"]
    config["pipeline"]["nodes"][0]["config"] = {"expand": False}
    assert collect_config_schema_findings(config) == ()


@pytest.mark.parametrize("call_kind", ["nodeset", "loop"])
def test_imported_definitions_and_finite_graph_wire_keep_expand_and_full_bodies(tmp_path, call_kind):
    inner = definition("test.inner", expand=False)
    outer = definition("test.outer", expand=False, nodeset_imports=["inner.jsonc"])
    outer["pipeline"]["nodes"] = [node("child", "test.inner")]
    for name, value in (("inner.jsonc", inner), ("outer.jsonc", outer)):
        (tmp_path / name).write_text(json.dumps(value))
    call = node("outer", "test.outer")
    if call_kind == "loop":
        call = {**node("loop", "vibeflow.loop.while"), "requires": [], "provides": [],
                "loop": {"body": "test.outer", "max_iterations": 1, "stop_after": 1}}
    config = {"nodeset_imports": ["outer.jsonc"], "pipeline": {"nodes": [call]}}
    path = tmp_path / "workflow.jsonc"
    path.write_text(json.dumps(config))
    document = load_config_document(path)
    assert collect_config_schema_findings(document.data) == ()
    graph = parse_graph_config_data(document.data)
    assert graph.nodeset_types["test.inner"].expand is False
    assert graph.nodeset_types["test.outer"].expand is False
    assert graph.nodeset_types["test.inner"].graph.nodes[0].id == "inside"
    assert graph.nodeset_types["test.outer"].graph.nodes[0].definition_id == "test.inner"
    wire = json_projection(graph)
    assert wire["nodeset_types"]["test.inner"]["expand"] is False
    assert wire["nodeset_types"]["test.outer"]["expand"] is False
    assert wire["nodeset_types"]["test.inner"]["graph"]["nodes"][0]["id"] == "inside"
    assert "test.inner" in wire["nodeset_types"]["test.outer"]["graph"]["nodeset_refs"]
    if call_kind == "loop":
        assert wire["nodes"][0]["loop"]["body"] == "test.outer"
    json.dumps(wire)  # Shared definitions stay finite, including a collapsed parent.
