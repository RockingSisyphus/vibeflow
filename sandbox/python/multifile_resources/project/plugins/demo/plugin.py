from vibeflow.targets.python.sdk import Plugin, data_schema
from .plugin_support import Runtime

number = data_schema(type_key="number", schema={"type":"number"})

def create_runtime(context):
    return Runtime()

plugin = Plugin(id="demo", resources=[number], runtime=create_runtime, rulesets=["vibeflow.plugin"], declaration_rulesets=["vibeflow.plugin_declaration"], implementation_files=["plugin_support.py"], presentation={"fill":"#ecd4ff","shape":"cloud","icon":"P"})
