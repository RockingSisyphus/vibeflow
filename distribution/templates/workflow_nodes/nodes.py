"""Copyable ordinary declarations; explicitly contribute resources in a Plugin."""
from vibeflow.targets.python.sdk import node, capability, data_schema
from vibeflow.core.workflows.interfaces import (workflow_capability_descriptor, WORKFLOW_SCHEMA_TYPES, port_capability_descriptor, PORT_SCHEMA_TYPES)

@node(**{'type_key': 'example.self', 'display_name': 'Self', 'description': 'Ordinary SDK Self operation.', 'flow_kind': 'process', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['self'], 'actions': [{'operation': 'self'}]}}], 'contract': {'requires': [], 'provides': [{'key': 'instance', 'type': 'example.instance', 'display_name': 'instance'}], 'input_semantics': {}, 'output_semantics': {'instance': ['Operation instance']}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['self']}], 'presentation': {'shape': 'circle', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class Self:
    def run_pure(self, inputs, params, context):
        api=context.capabilities['vibeflow.workflow']
        return {"instance": api["self"]()["id"]}

@node(**{'type_key': 'example.call', 'display_name': 'Call', 'description': 'Ordinary SDK Call operation.', 'flow_kind': 'process', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['call'], 'actions': [{'operation': 'call', 'target': 'worker', 'wait': False}]}}], 'contract': {'requires': [], 'provides': [{'key': 'instance', 'type': 'example.instance', 'display_name': 'instance'}], 'input_semantics': {}, 'output_semantics': {'instance': ['Operation instance']}, 'params_schema': {'allow_background': {'type': 'boolean'}}, 'params_defaults': {'allow_background': False}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['call']}], 'presentation': {'shape': 'fr-rect', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class Call:
    def run_pure(self, inputs, params, context):
        api=context.capabilities['vibeflow.workflow']
        return {"instance": api["call"]({"target":"worker"})["id"]}

@node(**{'type_key': 'example.callandwait', 'display_name': 'CallAndWait', 'description': 'Ordinary SDK CallAndWait operation.', 'flow_kind': 'process', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['call', 'wait'], 'actions': [{'operation': 'call', 'target': 'worker', 'wait': True}, {'operation': 'wait'}]}}], 'contract': {'requires': [], 'provides': [{'key': 'instance', 'type': 'example.instance', 'display_name': 'instance'}, {'key': 'result', 'type': 'example.result', 'display_name': 'result'}], 'input_semantics': {}, 'output_semantics': {'instance': ['Operation instance'], 'result': ['Operation result']}, 'params_schema': {'allow_background': {'type': 'boolean'}}, 'params_defaults': {'allow_background': False}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['call', 'wait']}], 'presentation': {'shape': 'fr-rect', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class CallAndWait:
    def run_pure(self, inputs, params, context):
        api=context.capabilities['vibeflow.workflow']
        identity=api["call"]({"target":"worker"})["id"]
        return {"instance":identity,"result":api["wait"]({"id":identity})}

@node(**{'type_key': 'example.wait', 'display_name': 'Wait', 'description': 'Ordinary SDK Wait operation.', 'flow_kind': 'process', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['wait'], 'actions': [{'operation': 'wait'}]}}], 'contract': {'requires': [{'type': 'example.instance', 'cardinality': 'exactly_one', 'display_name': 'instance'}], 'provides': [{'key': 'result', 'type': 'example.result', 'display_name': 'result'}], 'input_semantics': {'example.instance': ['Application instance']}, 'output_semantics': {'result': ['Operation result']}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['wait']}], 'presentation': {'shape': 'hex', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class Wait:
    def run_pure(self, inputs, params, context):
        api=context.capabilities['vibeflow.workflow']
        return {"result":api["wait"]({"id":inputs["example.instance"]["value"]})}

@node(**{'type_key': 'example.send', 'display_name': 'Send', 'description': 'Ordinary SDK Send operation.', 'flow_kind': 'process', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['send'], 'actions': [{'operation': 'send'}]}}], 'contract': {'requires': [{'type': 'example.instance', 'cardinality': 'exactly_one', 'display_name': 'instance'}, {'type': 'example.payload', 'cardinality': 'exactly_one', 'display_name': 'payload'}], 'provides': [], 'input_semantics': {'example.instance': ['Application instance'], 'example.payload': ['Application payload']}, 'output_semantics': {}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['send']}], 'presentation': {'shape': 'lean-r', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class Send:
    def run_pure(self, inputs, params, context):
        api=context.capabilities['vibeflow.workflow']
        api["send"]({"id":inputs["example.instance"]["value"],"payload":inputs["example.payload"]["value"]})
        return {}

@node(**{'type_key': 'example.receive', 'display_name': 'Receive', 'description': 'Ordinary SDK Receive operation.', 'flow_kind': 'process', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['receive'], 'actions': [{'operation': 'receive'}]}}], 'contract': {'requires': [], 'provides': [{'key': 'message', 'type': 'example.message', 'display_name': 'message'}], 'input_semantics': {}, 'output_semantics': {'message': ['Operation message']}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['receive']}], 'presentation': {'shape': 'lean-r', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class Receive:
    def run_pure(self, inputs, params, context):
        api=context.capabilities['vibeflow.workflow']
        return {"message":api["receive"]()}

@node(**{'type_key': 'example.kill', 'display_name': 'Kill', 'description': 'Ordinary SDK Kill operation.', 'flow_kind': 'process', 'rulesets': ['vibeflow.process', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.workflow', 'operations': ['kill'], 'actions': [{'operation': 'kill'}]}}], 'contract': {'requires': [{'type': 'example.instance', 'cardinality': 'exactly_one', 'display_name': 'instance'}], 'provides': [{'key': 'result', 'type': 'example.result', 'display_name': 'result'}], 'input_semantics': {'example.instance': ['Application instance']}, 'output_semantics': {'result': ['Operation result']}}, 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['kill']}], 'presentation': {'shape': 'diamond', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class Kill:
    def run_pure(self, inputs, params, context):
        api=context.capabilities['vibeflow.workflow']
        return {"result":api["kill"]({"id":inputs["example.instance"]["value"]})}

@node(**{'type_key': 'example.portreceive', 'display_name': 'PortReceive', 'description': 'Ordinary SDK PortReceive operation.', 'flow_kind': 'io', 'rulesets': ['vibeflow.io', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.port', 'operations': ['receive'], 'actions': [{'operation': 'receive'}]}}], 'contract': {'requires': [], 'provides': [{'key': 'payload', 'type': 'example.payload', 'display_name': 'payload'}], 'input_semantics': {}, 'output_semantics': {'payload': ['Operation payload']}}, 'capabilities': [{'id': 'vibeflow.port', 'operations': ['receive']}], 'presentation': {'shape': 'lean-r', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class PortReceive:
    def run_pure(self, inputs, params, context):
        api=context.capabilities['vibeflow.port']
        return {"payload":api["receive"]({"port":"default"})["value"]}

@node(**{'type_key': 'example.portsend', 'display_name': 'PortSend', 'description': 'Ordinary SDK PortSend operation.', 'flow_kind': 'io', 'rulesets': ['vibeflow.io', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.port', 'operations': ['send'], 'actions': [{'operation': 'send'}]}}], 'contract': {'requires': [{'type': 'example.payload', 'cardinality': 'exactly_one', 'display_name': 'payload'}], 'provides': [], 'input_semantics': {'example.payload': ['Application payload']}, 'output_semantics': {}}, 'capabilities': [{'id': 'vibeflow.port', 'operations': ['send']}], 'presentation': {'shape': 'lean-r', 'fill': '#f4e8c1', 'stroke': '#a72c2c', 'text': '#191919'}})
class PortSend:
    def run_pure(self, inputs, params, context):
        api=context.capabilities['vibeflow.port']
        api["send"]({"port":"default","value":inputs["example.payload"]["value"]})
        return {}

_workflow=workflow_capability_descriptor().to_dict()
_workflow.pop("kind")
_port=port_capability_descriptor({"receive","send"}).to_dict()
_port.pop("kind")
resources=[Self,Call,CallAndWait,Wait,Send,Receive,Kill,PortReceive,PortSend,capability(**_workflow),capability(**_port),
    *[data_schema(type_key=key,schema=value) for key,value in {**WORKFLOW_SCHEMA_TYPES,**PORT_SCHEMA_TYPES}.items()],
    *[data_schema(type_key="example."+key,schema={"type":"string"} if key=="instance" else {}) for key in ("instance","payload","message","result")]]
