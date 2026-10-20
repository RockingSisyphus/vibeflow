"""Ordinary SDK port nodes with explicit application contracts."""
from vibeflow.targets.python.sdk import node, capability, data_schema

@node(**{'type_key': 'math.port_receive_0', 'flow_kind': 'io', 'rulesets': ['vibeflow.io', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.port', 'operations': ['receive']}}], 'display_name': 'Port receive', 'description': 'Receive through the host-provided port Capability.', 'contract': {'requires': [], 'provides': [{'key': 'x', 'type': 'math.x', 'display_name': 'x'}], 'input_semantics': {}, 'output_semantics': {'x': ['Value received from the host.']}, 'params_schema': {'port': {'type': 'string'}}, 'params_defaults': {'port': 'default'}}, 'capabilities': [{'id': 'vibeflow.port', 'operations': ['receive']}]})
class Port0:
    def run_pure(self, inputs, params, context):
        received = context.capabilities["vibeflow.port"]["receive"]({"port": params["port"]})
        return {'x': received["value"]}

@node(**{'type_key': 'math.port_send_1', 'flow_kind': 'io', 'rulesets': ['vibeflow.io', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.port', 'operations': ['send']}}], 'display_name': 'Port send', 'description': 'Send through the host-provided port Capability.', 'contract': {'requires': [{'type': 'math.result', 'cardinality': 'exactly_one', 'display_name': 'math.result'}], 'provides': [], 'input_semantics': {'math.result': ['Value to send to the host.']}, 'output_semantics': {}, 'params_schema': {'port': {'type': 'string'}}, 'params_defaults': {'port': 'default'}}, 'capabilities': [{'id': 'vibeflow.port', 'operations': ['send']}]})
class Port1:
    def run_pure(self, inputs, params, context):
        context.capabilities["vibeflow.port"]["send"]({"port": params["port"], "value": inputs['math.result']["value"]})
        return {}

portCapability = capability(**{'id': 'vibeflow.port', 'targets': ['python', 'browser', 'node'], 'display_name': 'VibeFlow Port', 'description': 'Host-provided receive/send queue boundary.', 'operations': {'receive': {'input_type': 'vibeflow.port.receive.request', 'output_type': 'vibeflow.port.receive.result', 'completion': 'suspend'}, 'send': {'input_type': 'vibeflow.port.send.request', 'output_type': 'vibeflow.port.send.result', 'completion': 'immediate'}}})
portSchema0 = data_schema(type_key='vibeflow.port.receive.request', schema={'type': 'object', 'required': ['port'], 'properties': {'port': {'type': 'string'}}, 'additionalProperties': False})
portSchema1 = data_schema(type_key='vibeflow.port.receive.result', schema={'type': 'object', 'required': ['value'], 'properties': {'value': {}}, 'additionalProperties': False})
portSchema2 = data_schema(type_key='vibeflow.port.send.request', schema={'type': 'object', 'required': ['port', 'value'], 'properties': {'port': {'type': 'string'}, 'value': {}}, 'additionalProperties': False})
portSchema3 = data_schema(type_key='vibeflow.port.send.result', schema={'type': 'null'})
