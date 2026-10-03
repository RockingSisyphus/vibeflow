"""JavaScript Application adapter for fixed plugin bootstrap."""
from vibeflow.targets.javascript.sdk.loading import load_plugin


def attach_definitions(catalog, definitions):
    from vibeflow.targets.javascript.sdk.loading import attach_catalog
    attach_catalog(catalog, definitions)


def load_plugin_definition(source, *, owner, workspace, node_command):
    return load_plugin(source, root=owner.path, project_config=owner.project_config, node_command=node_command)
