"""Public JSON conversions preserve values and isolate mutable containers."""
import json
from types import MappingProxyType

import pytest

from vibeflow.core.descriptors import DescriptorModelError, freeze_json, freeze_mapping, thaw_json


def test_nested_settings_are_read_only_and_exported_copies_are_independent():
    original = {"labels": {"phase": "prepare"}, "stages": [{"name": "train"}], "empty": {}}
    frozen = freeze_mapping(original)
    with pytest.raises(TypeError):
        frozen["labels"]["phase"] = "changed"
    with pytest.raises(TypeError):
        frozen["stages"][0]["name"] = "changed"
    with pytest.raises(TypeError):
        frozen["empty"]["new"] = True
    with pytest.raises(AttributeError):
        frozen["stages"].append({"name": "changed"})

    exported = thaw_json(frozen)
    assert json.loads(json.dumps(exported)) == original
    original["labels"]["phase"] = "changed at source"
    exported["labels"]["phase"] = "changed in export"
    exported["stages"][0]["name"] = "changed in export"
    assert frozen["labels"]["phase"] == "prepare"
    assert frozen["stages"][0]["name"] == "train"
    assert thaw_json(frozen)["labels"]["phase"] == "prepare"


@pytest.mark.parametrize("value", [None, True, 3, 1.5, "text", [], {}, {"values": [None, False, 0, {"x": []}]}])
def test_json_values_round_trip(value):
    assert json.loads(json.dumps(thaw_json(freeze_json(value)))) == value


def test_thaw_handles_read_only_objects_inside_an_ordinary_list():
    assert thaw_json([MappingProxyType({"phase": "prepare"})]) == [{"phase": "prepare"}]


@pytest.mark.parametrize("value,location", [
    ({"nested": {1: "value"}}, "settings.nested"),
    ({"nested": [object()]}, "settings.nested[0]"),
    ({"nested": float("nan")}, "settings.nested"),
    ({"nested": float("inf")}, "settings.nested"),
])
def test_invalid_json_retains_the_error_type_and_field_path(value, location):
    with pytest.raises(DescriptorModelError) as caught:
        freeze_json(value, field_name="settings")
    assert location in str(caught.value)


def test_optional_object_settings_and_object_requirement():
    assert thaw_json(freeze_mapping(None)) == {}
    with pytest.raises(DescriptorModelError, match="must be an object"):
        freeze_mapping([1])
