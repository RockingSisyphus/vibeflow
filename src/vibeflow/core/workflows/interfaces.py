"""Fixed workflow request and result schemas."""
from .coordination import STATES

_ID = {"type": "string", "minLength": 1}
_TIMEOUT = {"type": "number", "minimum": 0}
WORKFLOW_REFERENCE_SCHEMA = {"type":"object", "required":["path"],
    "properties":{"root":{"type":"string"}, "path":_ID, "entry":_ID}, "additionalProperties":False}
WORKFLOW_LAUNCH_SCHEMA = {"oneOf":[
    {"type":"object", "required":["kind","command"],
     "properties":{"kind":{"const":"process"}, "command":{"type":"array","items":{"type":"string"},"minItems":1},
        "cwd":{"type":"string"}, "env":{"type":"object","additionalProperties":{"type":"string"}}}, "additionalProperties":False},
    {"type":"object", "required":["kind"], "properties":{"kind":{"const":"in_process"}}, "additionalProperties":False}]}
_REQUESTS = {
    "invoke_sync": ({"workflow": WORKFLOW_REFERENCE_SCHEMA, "inputs":{"type":"object"}}, ["workflow"]),
    "call": ({"workflow": WORKFLOW_REFERENCE_SCHEMA, "launch":WORKFLOW_LAUNCH_SCHEMA,
              "inputs": {"type": "object"}, "timeout": _TIMEOUT}, ["workflow", "launch"]),
    "wait": ({"id": _ID, "timeout": _TIMEOUT}, ["id"]),
    "send": ({"id": _ID, "port": _ID, "payload": {}}, ["id", "payload"]),
    "receive": ({"port": _ID, "timeout": _TIMEOUT}, []),
    "kill": ({"id": _ID, "workflow":WORKFLOW_REFERENCE_SCHEMA, "timeout": _TIMEOUT}, ["id", "workflow"]),
}
WORKFLOW_OPERATIONS = frozenset(_REQUESTS)
WORKFLOW_SCHEMA_TYPES = {
    f"vibeflow.workflow.{name}.request": {"type": "object", "properties": fields,
        "required": required, "additionalProperties": False}
    for name, (fields, required) in _REQUESTS.items()
}
_IDENTITY = {"type": "object", "properties": {"id": _ID}, "required": ["id"], "additionalProperties": False}
_STATUS = {"type": "object", "properties": {"id": _ID,
    "state": {"enum": list(STATES)},
    "outputs": {}, "error": {}, "pid": {"type": ["number", "null"]},
    "workflow": {"type": ["object", "string", "null"]}, "entry": {"type": ["string", "null"]}},
    "required": ["id", "state"], "additionalProperties": False}
WORKFLOW_SCHEMA_TYPES.update({
    "vibeflow.workflow.invoke_sync.result": {"type":"object"},
    "vibeflow.workflow.call.result": _IDENTITY,
    "vibeflow.workflow.wait.result": _STATUS,
    "vibeflow.workflow.kill.result": _STATUS,
    "vibeflow.workflow.send.result": {"type": "null"},
    "vibeflow.workflow.receive.result": {"type": "object", "properties": {
        "sender": _ID, "port": _ID, "payload": {}}, "required": ["sender", "port", "payload"], "additionalProperties": False},
})
