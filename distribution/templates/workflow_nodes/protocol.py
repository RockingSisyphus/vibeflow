"""Copy into plugins/workflow_protocol/protocol.py and select this Plugin."""
from vibeflow.targets.python.sdk import Plugin, capability, data_schema
from vibeflow.core.workflows.interfaces import (workflow_capability_descriptor, WORKFLOW_SCHEMA_TYPES, port_capability_descriptor, PORT_SCHEMA_TYPES)

_workflow=workflow_capability_descriptor().to_dict()
_workflow.pop("kind")
_port=port_capability_descriptor({"receive","send"}).to_dict()
_port.pop("kind")
resources=[capability(**_workflow),capability(**_port),
    *[data_schema(type_key=key,schema=value) for key,value in {**WORKFLOW_SCHEMA_TYPES,**PORT_SCHEMA_TYPES}.items()],
    *[data_schema(type_key="example."+key,schema={"type":"string"} if key=="instance" else {}) for key in ("instance","payload","message","result")]]

plugin=Plugin(id="example.workflow.protocol",resources=resources)
