"""Pure contribution assembly, freezing and conflict provenance."""

import pytest

from vibeflow.core.descriptors import ContributionBuilder, ResourceOrigin, ResourceOwner, compose_contributions
from vibeflow.core.descriptors.catalogs import DescriptorCatalogError
from vibeflow.targets.python.rules.plugin import builtin_plugin
from vibeflow.core.descriptors.models import DataSchemaDescriptor, DescriptorModelError
from vibeflow.core.descriptors.decode import decode_resource
from vibeflow.core.descriptors.contributions import RESOURCE_GROUPS


def test_contributions_are_fixed_and_config_is_read_only():
    builder = ContributionBuilder("example")
    builder.add(DataSchemaDescriptor(type_key="payload", schema={"type": "object"}))
    original = {"nested": {"value": [1]}}
    contribution = builder.finish(config=original)
    original["nested"]["value"].append(2)
    assert contribution.config["nested"]["value"] == (1,)
    with pytest.raises(TypeError):
        contribution.config["new"] = 1
    with pytest.raises(DescriptorModelError, match="frozen"):
        builder.add(DataSchemaDescriptor(type_key="other", schema={}))
    catalogs = compose_contributions((builtin_plugin().contributions(), contribution))
    assert catalogs.schemas.require("payload").schema["type"] == "object"
    assert catalogs.rules.require("vibeflow.no_side_effects")


def test_conflicts_preserve_both_plugin_locations():
    left, right = ContributionBuilder("left"), ContributionBuilder("right")
    descriptor = DataSchemaDescriptor(type_key="payload", schema={})
    left.add(descriptor, origin=ResourceOrigin(ResourceOwner("plugin", "left"), "left.py", 8, symbol="Payload"))
    right.add(descriptor, origin=ResourceOrigin(ResourceOwner("plugin", "right"), "right.ts", 12, symbol="payload"))
    with pytest.raises(DescriptorCatalogError) as captured:
        compose_contributions((left.finish(), right.finish()))
    assert captured.value.code == "DESCRIPTOR.DUPLICATE"
    origins = captured.value.details["origins"]
    assert origins["previous"] == {"owner": ResourceOwner("plugin", "left").to_dict(), "path": "left.py", "line": 8, "symbol": "Payload"}
    assert origins["current"]["owner"]["id"] == "right"


@pytest.mark.parametrize("data", [
    {"kind":"node_type", "id":"demo.shell", "presentation":{"shape":"hex"}},
    {"kind":"node", "id":"demo.node", "node_type":"demo.shell", "display_name":"Node", "description":"Node", "version":"1", "flow_kind":"process", "contract":{}, "rulesets":["demo.rules"]},
    {"kind":"rule", "id":"demo.check", "implementations":[{"language":"python", "source":{"kind":"file", "ref":"checks.py", "export":"check"}}]},
    {"kind":"ruleset", "id":"demo.rules", "calls":[{"id":"check", "rule_id":"demo.check"}], "entrypoints":{"static":["check"]}},
    {"kind":"data_schema", "type_key":"demo.payload", "schema":{"type":"number"}},
    {"kind":"base_lib", "id":"demo.lib", "display_name":"Lib", "description":"Lib", "implementations":[{"language":"python", "targets":["python"], "source":{"kind":"file", "ref":"lib.py"}}]},
    {"kind":"capability", "id":"demo.clock", "targets":["node"], "operations":{"now":{"input_type":"demo.payload", "output_type":"demo.payload"}}},
    {"kind":"plugin", "id":"demo.runtime", "type":"runtime", "targets":["python"], "implementations":[{"language":"python", "targets":["python"], "source":{"kind":"file", "ref":"runtime.py", "export":"create"}}]},
], ids=tuple(RESOURCE_GROUPS))
def test_every_resource_kind_uses_the_same_pure_collection_path(data):
    descriptor = decode_resource(data)
    builder = ContributionBuilder("demo", source="plugin.py")
    resources = ()
    if data["kind"] == "node":
        from vibeflow.core.descriptors.contributions import ResourceDeclaration
        resources = (ResourceDeclaration(descriptor, ResourceOrigin(ResourceOwner("root", "app"), "nodes/step.py", 9)),)
    else:
        builder.add(descriptor, origin=ResourceOrigin(ResourceOwner("plugin", "demo"), "plugin.py", 9))
    catalogs = compose_contributions((builtin_plugin().contributions(), builder.finish()), resources=resources)
    catalog = getattr(catalogs, RESOURCE_GROUPS[data["kind"]])
    assert catalog.require(descriptor.id) == descriptor
    assert catalogs.origins[(RESOURCE_GROUPS[data["kind"]], descriptor.id)].line == 9
    with pytest.raises(DescriptorCatalogError, match="read-only"):
        catalog.register(descriptor)


def test_wrong_descriptor_type_preserves_the_resource_error():
    class InvalidDescriptor:
        def to_dict(self):
            return {'node_type': 'vibeflow.node', "kind":"node"}
    with pytest.raises(DescriptorCatalogError) as captured:
        ContributionBuilder("demo").add(InvalidDescriptor())
    assert captured.value.code == "DESCRIPTOR.TYPE"
