"""Read-only declarations produce isolated native JSON configuration."""

import json
from types import MappingProxyType

import pytest

from vibeflow.core.config.node import NodeConfigError, merge_node_config, normalize_node_config_spec
from vibeflow.core.descriptors.models import NodeContractDescriptor


@pytest.mark.parametrize("schema_type,value", [
    ("array", []), ("array", ["a"]), ("object", {}), ("object", {"a": 1}),
    ("array", [{"a": [1, {"b": []}]}]), ("object", {"a": [{"b": []}]}),
    ("string", "a"), ("integer", 1), ("boolean", True), ("number", 1.5), ("null", None),
])
def test_readonly_defaults_and_overrides_become_native_json(schema_type, value):
    contract = NodeContractDescriptor(params_schema={"value": {"type": schema_type}}, params_defaults={"value": value})
    spec = normalize_node_config_spec(contract.params_schema, contract.params_defaults)
    expected = json.loads(json.dumps(value))
    assert merge_node_config(spec, None) == {"value": expected}
    assert merge_node_config(spec, contract.params_defaults) == {"value": expected}
    assert json.dumps(spec.to_dict())
    if isinstance(value, (list, dict)):
        assert type(spec.defaults["value"]) is type(value)
    with pytest.raises(TypeError):
        contract.params_defaults["value"] = value


def test_nested_defaults_overrides_and_export_have_independent_storage():
    original = {"a": [{"b": []}]}
    spec = normalize_node_config_spec({"value": {"type": "object"}}, {"value": original})
    overrides = {"value": {"a": [{"b": ["override"]}]}}
    first = merge_node_config(spec, None)
    second = merge_node_config(spec, None)
    explicit = merge_node_config(spec, overrides)
    exported = spec.to_dict()
    first["value"]["a"][0]["b"].append("first")
    explicit["value"]["a"][0]["b"].append("explicit")
    exported["defaults"]["value"]["a"][0]["b"].append("export")
    original["a"][0]["b"].append("source")
    assert second["value"] == {"a": [{"b": []}]}
    assert spec.defaults["value"] == {"a": [{"b": []}]}
    assert overrides["value"] == {"a": [{"b": ["override"]}]}


def test_nested_readonly_schema_is_exportable_and_isolated():
    schema = MappingProxyType({"value": MappingProxyType({"type": "object", "properties":
        MappingProxyType({"a": MappingProxyType({"type": "array"})})})})
    spec = normalize_node_config_spec(schema, {"value": {"a": []}})
    export = spec.to_dict()
    json.dumps(export)
    export["schema"]["value"]["properties"]["a"]["type"] = "string"
    assert spec.schema["value"]["properties"]["a"]["type"] == "array"


@pytest.mark.parametrize("invalid", [object(), {"a"}, float("nan"), float("inf")])
def test_invalid_json_defaults_and_overrides_remain_rejected(invalid):
    with pytest.raises(NodeConfigError, match="defaults.value.*JSON snapshot safe"):
        normalize_node_config_spec({"value": {"type": "any"}}, {"value": invalid})
    spec = normalize_node_config_spec({"value": {"type": "any"}}, {"value": None})
    with pytest.raises(NodeConfigError, match="value.*JSON snapshot safe"):
        merge_node_config(spec, {"value": invalid})


def test_cyclic_json_is_reported_as_a_configuration_error():
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(NodeConfigError, match="JSON snapshot safe"):
        normalize_node_config_spec({"value": {"type": "array"}}, {"value": cyclic})


@pytest.mark.parametrize("schema_type,value", [("array", {}), ("object", []), ("integer", True)])
def test_type_mismatches_remain_rejected(schema_type, value):
    with pytest.raises(NodeConfigError, match="must match schema type"):
        normalize_node_config_spec({"value": {"type": schema_type}}, {"value": value})
