from vibeflow.targets.python.sdk import node
from plugins.addition.math_resource import calculate
from .node_support import number

@node(**{'node_type': 'vibeflow.node', 'id': 'addition.boundary', 'display_name': 'Boundary', 'description': 'Boundary', 'flow_kind': 'terminal', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [], 'provides': [], 'input_semantics': {}, 'output_semantics': {}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class Boundary:
    def run_pure(self, inputs, params):
        return {}

@node(**{'node_type': 'vibeflow.node', 'id': 'addition.add', 'display_name': 'Add', 'description': 'Add', 'flow_kind': 'process', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'addition.a', 'cardinality': 'exactly_one', 'display_name': 'addition.a'}], 'provides': [{'key': 'result', 'type': 'addition.result', 'display_name': 'result'}], 'input_semantics': {'addition.a': ['addition.a']}, 'output_semantics': {'result': ['addition.result']}, 'params_schema': {'b': {'type': 'number'}}, 'params_defaults': {'b': 3}}, 'base_libs': ['addition.math'], 'implementation_files': ['node_support.py']})
class Add:
    def run_pure(self, inputs, params):
        return {"result": calculate(number(inputs), params["b"])}
