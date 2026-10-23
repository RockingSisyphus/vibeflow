"""Data contracts for the cooperative formula's ordinary mathematical Nodes."""
from vibeflow.targets.python.sdk import Plugin, data_schema

resources = [data_schema(type_key="math." + name, schema=schema) for name, schema in {
    "x": {"type": "number"}, "y": {"type": "number"}, "case_id": {"type": "string"},
    "seed": {"type": "object"}, "local": {"type": "number"}, "checkpoint": {"type": "object"},
    "request": {"type": "object"}, "reply": {"type": "object"}, "shift": {"type": "object"},
    "square": {"type": "object"}, "answer": {"type": "object"},
}.items()]
plugin = Plugin(id="math.cooperation", resources=resources)
