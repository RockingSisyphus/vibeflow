from __future__ import annotations

import json

import pytest

from vibeflow.core.contracts import PipelineInputSpec, PipelineOutputSpec
from vibeflow.targets.python.project.compiler import GraphCompiler
from vibeflow.core import GraphConfigError
from vibeflow.core.descriptors import NodeCatalog, NodeContractDescriptor, NodeDescriptor
from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
from vibeflow.tooling.application.python.project.core import load_workspace_config
from vibeflow.tooling.project.graph_config import parse_graph_config


def _terminal_node() -> dict[str, object]:
    return {
        "id": "end",
        "type_used": "example.end",
        "display_name": "End",
        "description": "Ends the workflow.",
    }


def test_pipeline_interface_preserves_legacy_and_exposes_aot_fields() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [
                    {
                        "key": "request",
                        "type": "request.v1",
                        "display_name": "Request",
                        "required": True,
                    },
                    {
                        "key": "hint",
                        "type": "hint.v1",
                        "display_name": "Hint",
                        "required": False,
                    },
                ],
                "outputs": [
                    {
                        "type": "response.v1",
                        "cardinality": "exactly_one",
                        "display_name": "Response",
                        "as": "response",
                    }
                ],
                "nodes": [_terminal_node()],
            }
        }
    )

    assert graph.inputs == (
        PipelineInputSpec("request", "request.v1", "Request", True),
        PipelineInputSpec("hint", "hint.v1", "Hint", False),
    )
    assert graph.outputs == (
        PipelineOutputSpec("response.v1", "exactly_one", "Response", "response"),
    )
    assert graph.outputs[0].public_name == "response"


def test_pipeline_input_requiredness_is_legacy_optional_but_must_be_boolean() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "value", "type": "value.v1", "display_name": "Value"}],
                "nodes": [_terminal_node()],
            }
        }
    )
    assert graph.inputs[0].required is None

    with pytest.raises(GraphConfigError, match="required must be a boolean"):
        parse_graph_config(
            {
                "pipeline": {
                    "inputs": [
                        {
                            "key": "value",
                            "type": "value.v1",
                            "display_name": "Value",
                            "required": "yes",
                        }
                    ],
                    "nodes": [_terminal_node()],
                }
            }
        )


def test_pipeline_output_aliases_are_unique() -> None:
    with pytest.raises(GraphConfigError, match=r"pipeline\.outputs\.as contains duplicate"):
        parse_graph_config(
            {
                "pipeline": {
                    "outputs": [
                        {
                            "type": "left.v1",
                            "cardinality": "all",
                            "display_name": "Left",
                            "as": "items",
                        },
                        {
                            "type": "right.v1",
                            "cardinality": "all",
                            "display_name": "Right",
                            "as": "items",
                        },
                    ],
                    "nodes": [_terminal_node()],
                }
            }
        )


def test_graph_compiler_accepts_language_neutral_node_catalog() -> None:
    catalog = NodeCatalog(
        (
            NodeDescriptor(
                type_key="example.end",
                display_name="End",
                category="example",
                description="Ends the workflow.",
                version="1.0.0",
                flow_kind="terminal",
                contract=NodeContractDescriptor(),
            ),
        )
    )
    graph = parse_graph_config({"pipeline": {"nodes": [_terminal_node()]}})

    compiled = GraphCompiler().compile(graph, catalog=catalog)

    assert compiled.flow_kinds == {"end": "terminal"}


def test_workspace_project_config_accepts_descriptor_and_javascript_sections(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "javascript",
                "descriptors": {
                    "nodes": ["manifests/nodes"],
                    "base_lib": ["manifests/base_lib"],
                    "data_schemas": ["manifests/data"],
                    "capabilities": ["manifests/capabilities"],
                },
                "javascript": {
                    "package_root": ".",
                    "external_packages": ["example-package"],
                },
            }
        ),
        encoding="utf-8",
    )
    workspace_path = tmp_path / "vibeflow_config.jsonc"
    workspace_path.write_text(
        json.dumps({"roots": [{"id": "project", "path": "project"}]}),
        encoding="utf-8",
    )

    workspace = load_workspace_config(workspace_path)
    assert workspace.roots[0].project_config["javascript"]["package_root"] == "."


def test_workspace_project_config_rejects_invalid_javascript_shape(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "javascript",
                "javascript": {"package_root": ".", "external_packages": "bad"},
            }
        ),
        encoding="utf-8",
    )
    workspace_path = tmp_path / "vibeflow_config.jsonc"
    workspace_path.write_text(
        json.dumps({"roots": [{"id": "project", "path": "project"}]}),
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="external_packages"):
        load_workspace_config(workspace_path)
