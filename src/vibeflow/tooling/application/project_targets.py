"""Dispatch project preparation to the selected Target's Application adapter."""
from importlib import import_module

_ADAPTERS = {
    "python":"vibeflow.tooling.application.python.project.preparation",
    "javascript":"vibeflow.tooling.application.javascript.preparation",
}


def preparation_adapter(target):
    return import_module(_ADAPTERS[target])
