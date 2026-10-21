import pytest

from vibeflow.core.descriptors import ResourceOwner, ResourceOrigin, compose_contributions
from vibeflow.core.descriptors.contributions import ContributionBuilder, ResourceDeclaration
from vibeflow.core.descriptors.models import DataSchemaDescriptor, DescriptorModelError


def resource(identifier, owner):
    return ResourceDeclaration(DataSchemaDescriptor(identifier, {"type": "string"}),
                               ResourceOrigin(owner, "schema.py"))


def test_standalone_resources_have_real_owners_without_synthetic_plugins():
    project = ResourceOwner("project", "workspace", path="/workspace")
    root = ResourceOwner("root", "desktop", path="/workspace/desktop")
    catalogs = compose_contributions((), resources=(resource("shared", project), resource("local", root)))
    assert catalogs.schemas.available() == ("local", "shared")
    assert not catalogs.plugin_settings
    assert catalogs.origins[("schemas", "shared")].owner == project
    assert catalogs.origins[("schemas", "local")].owner == root
    assert catalogs.origins[("schemas", "local")].to_dict()["owner"]["kind"] == "root"


def test_plugin_resources_cannot_be_installed_as_standalone_resources():
    with pytest.raises(DescriptorModelError, match="complete plugin"):
        compose_contributions((), resources=(resource("owned", ResourceOwner("plugin", "p")),))
    with pytest.raises(DescriptorModelError, match="contributing plugin"):
        ContributionBuilder("p").add(resource("local", ResourceOwner("root", "r")).descriptor,
                                     origin=ResourceOrigin(ResourceOwner("root", "r"), "node.py"))
