"""Route trusted bootstrap to the Application owning the selected root."""
from importlib import import_module


_APPLICATIONS = {
    "python": "vibeflow.tooling.application.python.plugin_definitions",
    "javascript": "vibeflow.tooling.application.javascript.plugin_definitions",
}


def load_plugin_definition(source, *, owner, workspace, node_command):
    application = import_module(_APPLICATIONS[owner.project_target])
    return application.load_plugin_definition(source, owner=owner, workspace=workspace, node_command=node_command)


def attach_plugin_definitions(catalog, definitions):
    from vibeflow.targets.shared.bindings import attach_native_bindings
    attach_native_bindings(catalog, (value for values in definitions.values() for value in values))
    for target, values in definitions.items():
        application = import_module(_APPLICATIONS[target])
        attach = getattr(application, "attach_definitions", None)
        if attach is not None:
            attach(catalog, values)


def normalize_contributions(contribution, bindings, *, owner, workspace):
    application = import_module(_APPLICATIONS[owner.project_target])
    normalize = getattr(application, "normalize_contributions", None)
    return normalize(contribution, bindings, owner=owner, workspace=workspace) if normalize else contribution


def load_builtin_definition(target):
    application = import_module(_APPLICATIONS["python" if target == "project" else target])
    return application.load_builtin_definition(project_only=target == "project")
