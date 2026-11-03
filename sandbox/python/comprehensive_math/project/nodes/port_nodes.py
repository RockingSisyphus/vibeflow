"""Ordinary SDK port nodes with explicit application contracts."""
from vibeflow.targets.python.sdk import node

@node(**{'node_type': 'vibeflow.node', 'id': 'math.port_receive_0', 'flow_kind': 'io', 'rulesets': ['vibeflow.python_io'], 'display_name': 'Port receive', 'description': 'Receive through the application-owned queue.', 'contract': {'requires': [{'type': 'app.session', 'cardinality': 'exactly_one', 'display_name': 'Application session'}], 'provides': [{'key': 'x', 'type': 'math.x', 'display_name': 'x'}], 'input_semantics': {'app.session': ['Application-owned event queue or API instance.']}, 'output_semantics': {'x': ['Value received from the host.']}, 'params_schema': {'port': {'type': 'string'}}, 'params_defaults': {'port': 'default'}}})
class Port0:
    async def run_pure(self, inputs, params, context):
        received = await inputs["app.session"]["value"]['queue']["receive"]({"port": params["port"]})
        return {'x': received["value"]}

@node(**{'node_type': 'vibeflow.node', 'id': 'math.port_send_1', 'flow_kind': 'io', 'rulesets': ['vibeflow.python_io'], 'display_name': 'Port send', 'description': 'Send through the application-owned queue.', 'contract': {'requires': [{'type': 'math.result', 'cardinality': 'exactly_one', 'display_name': 'math.result'}, {'type': 'app.session', 'cardinality': 'exactly_one', 'display_name': 'Application session'}], 'provides': [], 'input_semantics': {'math.result': ['Value to send to the host.'], 'app.session': ['Application-owned event queue or API instance.']}, 'output_semantics': {}, 'params_schema': {'port': {'type': 'string'}}, 'params_defaults': {'port': 'default'}}})
class Port1:
    def run_pure(self, inputs, params, context):
        inputs["app.session"]["value"]['queue']["send"]({"port": params["port"], "value": inputs['math.result']["value"]})
        return {}
