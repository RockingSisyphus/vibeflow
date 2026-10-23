"""Copy into nodes/nodes.py; protocol resources live in the separate Plugin."""
from vibeflow.targets.python.sdk import node

@node(**{'node_type': 'vibeflow.node', 'id': 'example.invokesync', 'display_name': 'InvokeSync', 'description': 'Call a bound synchronous workflow and return its outputs.', 'flow_kind': 'workflow-io', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['invoke_sync'], 'actions': [{'operation': 'invoke_sync'}]}}], 'contract': {'requires': [{'type': 'example.payload', 'cardinality': 'optional_one', 'display_name': 'inputs'}], 'provides': [{'key': 'result', 'type': 'example.result', 'display_name': 'result'}], 'input_semantics': {'example.payload': ['Target workflow inputs']}, 'output_semantics': {'result': ['Operation result']}, 'params_schema': {'workflow': {'type': 'object', 'required': True, 'properties': {'root': {'type': 'string'}, 'path': {'type': 'string'}, 'entry': {'type': 'string'}}}}, 'params_defaults': {}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['invoke_sync']}]})
class InvokeSync:
    def run_pure(self, inputs, params, context):
        api = context.capabilities['vibeflow.workflow']
        payload = (inputs.get("example.payload") or {}).get("value", {})
        return {"result": api["invoke_sync"]({"workflow": params["workflow"], "inputs": payload})}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.call', 'display_name': 'Call', 'description': 'Ordinary SDK Call operation.', 'flow_kind': 'workflow-io', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['call'], 'actions': [{'operation': 'call', 'wait': False}]}}], 'contract': {'requires': [{'type': 'example.payload', 'cardinality': 'optional_one', 'display_name': 'inputs'}], 'provides': [{'key': 'instance', 'type': 'example.instance', 'display_name': 'instance'}], 'input_semantics': {'example.payload': ['Target workflow inputs']}, 'output_semantics': {'instance': ['Operation instance']}, 'params_schema': {'allow_background': {'type': 'boolean'}, 'workflow': {'type': 'object', 'required': True, 'properties': {'root': {'type': 'string'}, 'path': {'type': 'string'}, 'entry': {'type': 'string'}}}, 'launch': {'type': 'object', 'required': True, 'properties': {'command': {'type': 'array', 'items': {'type': 'string'}}, 'cwd': {'type': 'string'}, 'env': {'type': 'object'}, 'kind': {'type': 'string', 'enum': ['process', 'in_process'], 'required': True}}}}, 'params_defaults': {'allow_background': False}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['call']}]})
class Call:
    async def run_pure(self, inputs, params, context):
        api = context.capabilities['vibeflow.workflow']
        payload = (inputs.get("example.payload") or {}).get("value", {})
        return {"instance": (await api["call"]({"workflow": params["workflow"], "launch": params["launch"], "inputs": payload}))["id"]}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.callandwait', 'display_name': 'CallAndWait', 'description': 'Ordinary SDK CallAndWait operation.', 'flow_kind': 'workflow-io', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['call', 'wait'], 'actions': [{'operation': 'call', 'wait': True}, {'operation': 'wait'}]}}], 'contract': {'requires': [{'type': 'example.payload', 'cardinality': 'optional_one', 'display_name': 'inputs'}], 'provides': [{'key': 'instance', 'type': 'example.instance', 'display_name': 'instance'}, {'key': 'result', 'type': 'example.result', 'display_name': 'result'}], 'input_semantics': {'example.payload': ['Target workflow inputs']}, 'output_semantics': {'instance': ['Operation instance'], 'result': ['Operation result']}, 'params_schema': {'allow_background': {'type': 'boolean'}, 'workflow': {'type': 'object', 'required': True, 'properties': {'root': {'type': 'string'}, 'path': {'type': 'string'}, 'entry': {'type': 'string'}}}, 'launch': {'type': 'object', 'required': True, 'properties': {'command': {'type': 'array', 'items': {'type': 'string'}}, 'cwd': {'type': 'string'}, 'env': {'type': 'object'}, 'kind': {'type': 'string', 'enum': ['process', 'in_process'], 'required': True}}}}, 'params_defaults': {'allow_background': False}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['call', 'wait']}]})
class CallAndWait:
    async def run_pure(self, inputs, params, context):
        api = context.capabilities['vibeflow.workflow']
        payload = (inputs.get("example.payload") or {}).get("value", {})
        identity = (await api["call"]({"workflow": params["workflow"], "launch": params["launch"], "inputs": payload}))["id"]
        return {"instance": identity, "result": await api["wait"]({"id": identity})}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.wait', 'display_name': 'Wait', 'description': 'Ordinary SDK Wait operation.', 'flow_kind': 'workflow-io', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['wait'], 'actions': [{'operation': 'wait'}]}}], 'contract': {'requires': [{'type': 'example.instance', 'cardinality': 'exactly_one', 'display_name': 'instance'}], 'provides': [{'key': 'result', 'type': 'example.result', 'display_name': 'result'}], 'input_semantics': {'example.instance': ['Application instance']}, 'output_semantics': {'result': ['Operation result']}, 'params_schema': {}, 'params_defaults': {}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['wait']}]})
class Wait:
    async def run_pure(self, inputs, params, context):
        api = context.capabilities['vibeflow.workflow']
        return {"result": await api["wait"]({"id": inputs["example.instance"]["value"]})}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.send', 'display_name': 'Send', 'description': 'Ordinary SDK Send operation.', 'flow_kind': 'workflow-io', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['send'], 'actions': [{'operation': 'send'}]}}], 'contract': {'requires': [{'type': 'example.instance', 'cardinality': 'exactly_one', 'display_name': 'instance'}, {'type': 'example.payload', 'cardinality': 'exactly_one', 'display_name': 'payload'}], 'provides': [], 'input_semantics': {'example.instance': ['Application instance'], 'example.payload': ['Application payload']}, 'output_semantics': {}, 'params_schema': {'expected_workflows': {'type': 'array', 'items': {'type': 'object', 'required': ['path'], 'properties': {'root': {'type': 'string'}, 'path': {'type': 'string'}, 'entry': {'type': 'string'}}}}}, 'params_defaults': {'expected_workflows': []}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['send']}]})
class Send:
    def run_pure(self, inputs, params, context):
        api = context.capabilities['vibeflow.workflow']
        api["send"]({"id": inputs["example.instance"]["value"], "payload": inputs["example.payload"]["value"]})
        return {}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.receive', 'display_name': 'Receive', 'description': 'Ordinary SDK Receive operation.', 'flow_kind': 'workflow-io', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['receive'], 'actions': [{'operation': 'receive'}]}}], 'contract': {'requires': [], 'provides': [{'key': 'message', 'type': 'example.message', 'display_name': 'message'}], 'input_semantics': {}, 'output_semantics': {'message': ['Operation message']}, 'params_schema': {'expected_workflows': {'type': 'array', 'items': {'type': 'object', 'required': ['path'], 'properties': {'root': {'type': 'string'}, 'path': {'type': 'string'}, 'entry': {'type': 'string'}}}}}, 'params_defaults': {'expected_workflows': []}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['receive']}]})
class Receive:
    async def run_pure(self, inputs, params, context):
        api = context.capabilities['vibeflow.workflow']
        return {"message": await api["receive"]()}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.kill', 'display_name': 'Kill', 'description': 'Ordinary SDK Kill operation.', 'flow_kind': 'workflow-io', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['kill'], 'actions': [{'operation': 'kill'}]}}], 'contract': {'requires': [{'type': 'example.instance', 'cardinality': 'exactly_one', 'display_name': 'instance'}], 'provides': [{'key': 'result', 'type': 'example.result', 'display_name': 'result'}], 'input_semantics': {'example.instance': ['Application instance']}, 'output_semantics': {'result': ['Operation result']}, 'params_schema': {'workflow': {'type': 'object', 'required': True, 'properties': {'root': {'type': 'string'}, 'path': {'type': 'string'}, 'entry': {'type': 'string'}}}}, 'params_defaults': {}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['kill']}]})
class Kill:
    async def run_pure(self, inputs, params, context):
        api = context.capabilities['vibeflow.workflow']
        return {"result": await api["kill"]({"id": inputs["example.instance"]["value"], "workflow": params["workflow"]})}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.portreceive', 'display_name': 'PortReceive', 'description': 'Ordinary SDK PortReceive operation.', 'flow_kind': 'io', 'rulesets': ['vibeflow.io', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.port', 'operations': ['receive'], 'actions': [{'operation': 'receive'}]}}], 'contract': {'requires': [], 'provides': [{'key': 'payload', 'type': 'example.payload', 'display_name': 'payload'}], 'input_semantics': {}, 'output_semantics': {'payload': ['Operation payload']}, 'params_defaults': {}}, 'capabilities': [{'id': 'vibeflow.port', 'operations': ['receive']}], 'presentation': {'shape': 'lean-r', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class PortReceive:
    async def run_pure(self, inputs, params, context):
        api = context.capabilities['vibeflow.port']
        return {"payload": (await api["receive"]({"port": "default"}))["value"]}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.portsend', 'display_name': 'PortSend', 'description': 'Ordinary SDK PortSend operation.', 'flow_kind': 'io', 'rulesets': ['vibeflow.io', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.port', 'operations': ['send'], 'actions': [{'operation': 'send'}]}}], 'contract': {'requires': [{'type': 'example.payload', 'cardinality': 'exactly_one', 'display_name': 'payload'}], 'provides': [], 'input_semantics': {'example.payload': ['Application payload']}, 'output_semantics': {}, 'params_defaults': {}}, 'capabilities': [{'id': 'vibeflow.port', 'operations': ['send']}], 'presentation': {'shape': 'lean-r', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class PortSend:
    def run_pure(self, inputs, params, context):
        api = context.capabilities['vibeflow.port']
        api["send"]({"port": "default", "value": inputs["example.payload"]["value"]})
        return {}
