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
    for target, values in definitions.items():
        application = import_module(_APPLICATIONS[target])
        attach = getattr(application, "attach_definitions", None)
        if attach is not None:
            attach(catalog, values)
