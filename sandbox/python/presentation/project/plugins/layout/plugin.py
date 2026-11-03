from vibeflow.targets.python.sdk import Plugin
from .lifecycle import create_compiler, create_runtime
plugin = Plugin(id="layout.resources", resources=[],
    compiler=create_compiler, runtime=create_runtime, rulesets=["vibeflow.plugin"],
    declaration_rulesets=["vibeflow.plugin_declaration"],
    display_name="Layout lifecycle", description="Real compiler and runtime declarations.",
    presentation={"fill":"#d9e6ff", "shape":"hex"})
