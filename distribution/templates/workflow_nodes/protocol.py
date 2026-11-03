"""Plain business data contracts for the example workflow nodes."""
from vibeflow.targets.python.sdk import Plugin, data_schema
plugin = Plugin(id="example.workflow.protocol", resources=[
    data_schema(type_key="example." + name, schema={"type": "string"} if name == "instance" else {})
    for name in ("instance", "payload", "message", "result")])
