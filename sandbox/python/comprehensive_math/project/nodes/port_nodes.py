"""Ordinary SDK port nodes with explicit application contracts."""
from vibeflow.targets.python.sdk import node, capability, data_schema

@node(**{'node_type': 'vibeflow.node', 'id': 'math.port_receive_0', 'flow_kind': 'io', 'rulesets': ['vibeflow.io', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.port', 'operations': ['receive']}}], 'display_name': 'Port receive', 'description': 'Receive through the host-provided port Capability.', 'contract': {'requires': [], 'provides': [{'key': 'x', 'type': 'math.x', 'display_name': 'x'}], 'input_semantics': {}, 'output_semantics': {'x': ['Value received from the host.']}, 'params_schema': {'port': {'type': 'string'}}, 'params_defaults': {'port': 'default'}}, 'capabilities': [{'id': 'vibeflow.port', 'operations': ['receive']}]})
class Port0:
    async def run_pure(self, inputs, params, context):
        received = await context.capabilities["vibeflow.port"]["receive"]({"port": params["port"]})
        return {'x': received["value"]}

@node(**{'node_type': 'vibeflow.node', 'id': 'math.port_send_1', 'flow_kind': 'io', 'rulesets': ['vibeflow.io', {'rule_id': 'vibeflow.capability.allow', 'params': {'capability': 'vibeflow.port', 'operations': ['send']}}], 'display_name': 'Port send', 'description': 'Send through the host-provided port Capability.', 'contract': {'requires': [{'type': 'math.result', 'cardinality': 'exactly_one', 'display_name': 'math.result'}], 'provides': [], 'input_semantics': {'math.result': ['Value to send to the host.']}, 'output_semantics': {}, 'params_schema': {'port': {'type': 'string'}}, 'params_defaults': {'port': 'default'}}, 'capabilities': [{'id': 'vibeflow.port', 'operations': ['send']}]})
class Port1:
    def run_pure(self, inputs, params, context):
        context.capabilities["vibeflow.port"]["send"]({"port": params["port"], "value": inputs['math.result']["value"]})
        return {}
