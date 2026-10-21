from vibeflow.targets.python.sdk import node
from base_lib.arithmetic import affine, subtract

@node(**{'node_type': 'vibeflow.node', 'id': 'math.companion', 'display_name': 'Companion', 'description': 'Companion in the composite formula.', 'version': '1.0.0', 'flow_kind': 'process', 'contract': {'requires': [{'type': 'math.x', 'cardinality': 'exactly_one', 'display_name': 'math.x'}], 'provides': [{'key': 'companion', 'type': 'math.companion', 'display_name': 'companion'}], 'params_schema': {}, 'params_defaults': {}, 'input_semantics': {'math.x': ['math.x']}, 'output_semantics': {'companion': ['math.companion']}}, 'rulesets': ['math.process'], 'tags': ['comprehensive-math'], 'base_libs': ['math.helpers']})
class Companion:
    def run_pure(self, inputs, params):
        return {"companion": affine(inputs["math.x"]["value"], 2, 0) + 1}
