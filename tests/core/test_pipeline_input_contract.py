"""Canonical public inputs reject ambiguity before target execution."""

import pytest

from vibeflow.core.contracts import PipelineInputSpec, parse_pipeline_inputs
from vibeflow.block_compiler.model import PipelineInputSpec as PortableInput, PortablePlanError
from vibeflow.tooling.project.config_schema import collect_config_schema_findings


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_native_and_portable_input_models_reject_non_boolean(value):
    with pytest.raises(ValueError, match="explicitly true or false"):
        PipelineInputSpec("value", "value.v1", required=value)
    with pytest.raises(PortablePlanError, match="explicitly true or false"):
        PortableInput("value", "value.v1", required=value)


def test_input_constructor_requires_keyword_and_preserves_display_position():
    with pytest.raises(TypeError):
        PipelineInputSpec("value", "value.v1", "Value")
    with pytest.raises(TypeError):
        PipelineInputSpec("value", "value.v1", "Value", True)
    item = PipelineInputSpec("value", "value.v1", "Value", required=False)
    assert parse_pipeline_inputs([item.to_dict()], field="pipeline.inputs") == (item,)
    assert item.to_dict()["required"] is False


@pytest.mark.parametrize("value", [None, 0, 1, "true", "omitted"])
def test_schema_and_parser_report_the_same_input_field(value):
    item = {"key": "value", "type": "value.v1", "display_name": "Value"}
    if value != "omitted":
        item["required"] = value
    with pytest.raises(ValueError, match=r"pipeline.inputs\[0\].required must be explicitly"):
        parse_pipeline_inputs([item], field="pipeline.inputs")
    findings = collect_config_schema_findings({"pipeline": {"inputs": [item], "nodes": [
        {"id": "start", "type_used": "test.start", "display_name": "Start", "description": "Start."},
    ]}})
    assert len(findings) == 1
    assert findings[0].rule_id == "CONFIG.SCHEMA.PIPELINE_INPUTS"
    assert "pipeline.inputs[0].required" in findings[0].message
