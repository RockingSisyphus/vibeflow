"""Python Application adapter for fixed plugin bootstrap."""
from vibeflow.targets.python.sdk.loading import load_plugin


def load_plugin_definition(source, *, owner, workspace, node_command):
    return load_plugin(source, root=owner.path,
        source_roots=tuple(root.path for root in workspace.roots if root.project_target == "python"))


def normalize_contributions(contribution, bindings, *, owner, workspace):
    from vibeflow.targets.python.sdk.identity import normalize_contributions as normalize
    return normalize(contribution, bindings, root=owner.path,
        source_roots=tuple(root.path for root in workspace.roots if root.project_target == "python"))

def load_builtin_definition(*, project_only=False):
    from vibeflow.targets.python.rules.plugin import builtin_plugin, project_plugin
    return project_plugin() if project_only else builtin_plugin()
