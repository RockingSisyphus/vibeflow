"""Python Application adapter for fixed plugin bootstrap."""
from vibeflow.targets.python.sdk.loading import load_plugin


def load_plugin_definition(source, *, owner, workspace, node_command):
    return load_plugin(source, root=owner.path,
        source_roots=tuple(root.path for root in workspace.roots if root.project_target == "python"))
