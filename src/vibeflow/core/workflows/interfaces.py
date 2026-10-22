"""Public, pure Capability contracts. Plugins explicitly contribute these resources."""
from vibeflow.core.descriptors import CapabilityDescriptor, CapabilityOperationDescriptor


PORT_CAPABILITY_ID = "vibeflow.port"
PORT_SCHEMA_TYPES = {
    "vibeflow.port.receive.request": {
        "type": "object",
        "required": ["port"],
        "properties": {"port": {"type": "string"}},
        "additionalProperties": False,
    },
    "vibeflow.port.receive.result": {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {}},
        "additionalProperties": False,
    },
    "vibeflow.port.send.request": {
        "type": "object",
        "required": ["port", "value"],
        "properties": {
            "port": {"type": "string"},
            "value": {},
        },
        "additionalProperties": False,
    },
    "vibeflow.port.send.result": {"type": "null"},
}


def port_capability_descriptor(
    operations: set[str],
) -> CapabilityDescriptor:
    available = {
        "receive": CapabilityOperationDescriptor(
            input_type="vibeflow.port.receive.request",
            output_type="vibeflow.port.receive.result",
            completion="suspend",
        ),
        "send": CapabilityOperationDescriptor(
            input_type="vibeflow.port.send.request",
            output_type="vibeflow.port.send.result",
            completion="immediate",
        ),
    }
    return CapabilityDescriptor(
        id=PORT_CAPABILITY_ID,
        targets=("python", "browser", "node"),
        operations={
            name: available[name]
            for name in sorted(operations)
        },
        display_name="VibeFlow Port",
        description="Host-provided receive/send queue boundary.",
    )


WORKFLOW_CAPABILITY_ID = "vibeflow.workflow"
_ID = {"type": "string", "minLength": 1}
_TIMEOUT = {"type": "number", "minimum": 0}
WORKFLOW_REFERENCE_SCHEMA = {"type":"object", "required":["path"],
    "properties":{"root":{"type":"string"}, "path":_ID, "entry":_ID}, "additionalProperties":False}
WORKFLOW_LAUNCH_SCHEMA = {"type":"object", "required":["command"],
    "properties":{"command":{"type":"array","items":{"type":"string"},"minItems":1},
        "cwd":{"type":"string"}, "env":{"type":"object","additionalProperties":{"type":"string"}}}, "additionalProperties":False}
_REQUESTS = {
    "self": ({}, []),
    "call": ({"workflow": WORKFLOW_REFERENCE_SCHEMA, "launch":WORKFLOW_LAUNCH_SCHEMA,
              "inputs": {"type": "object"}, "timeout": _TIMEOUT}, ["workflow", "launch"]),
    "wait": ({"id": _ID, "timeout": _TIMEOUT}, ["id"]),
    "send": ({"id": _ID, "port": _ID, "payload": {}}, ["id", "payload"]),
    "receive": ({"port": _ID, "timeout": _TIMEOUT}, []),
    "kill": ({"id": _ID, "workflow":WORKFLOW_REFERENCE_SCHEMA, "timeout": _TIMEOUT}, ["id", "workflow"]),
}
WORKFLOW_SCHEMA_TYPES = {
    f"vibeflow.workflow.{name}.request": {"type": "object", "properties": fields,
        "required": required, "additionalProperties": False}
    for name, (fields, required) in _REQUESTS.items()
}
_IDENTITY = {"type": "object", "properties": {"id": _ID}, "required": ["id"], "additionalProperties": False}
_STATUS = {"type": "object", "properties": {"id": _ID,
    "state": {"enum": ["starting", "running", "stopping", "succeeded", "failed", "cancelled"]},
    "outputs": {}, "error": {}, "pid": {"type": ["number", "null"]},
    "workflow": {"type": ["object", "string", "null"]}, "entry": {"type": ["string", "null"]}},
    "required": ["id", "state"], "additionalProperties": False}
WORKFLOW_SCHEMA_TYPES.update({
    "vibeflow.workflow.self.result": _IDENTITY,
    "vibeflow.workflow.call.result": _IDENTITY,
    "vibeflow.workflow.wait.result": _STATUS,
    "vibeflow.workflow.kill.result": _STATUS,
    "vibeflow.workflow.send.result": {"type": "null"},
    "vibeflow.workflow.receive.result": {"type": "object", "properties": {
        "sender": _ID, "port": _ID, "payload": {}}, "required": ["sender", "port", "payload"], "additionalProperties": False},
})


def workflow_capability_descriptor():
    return CapabilityDescriptor(id=WORKFLOW_CAPABILITY_ID, targets=("python", "node", "browser"),
        operations={name: CapabilityOperationDescriptor(
            input_type=f"vibeflow.workflow.{name}.request", output_type=f"vibeflow.workflow.{name}.result",
            completion="immediate" if name in {"self", "send"} else "suspend") for name in _REQUESTS},
        display_name="Workflow coordination", description="Independent workflow instances and local JSON messages.")
