"""Native Node implementations with their authoritative SDK declarations."""

from vibeflow.targets.python.sdk import node

from vibeflow.targets.python.sdk import node

from vibeflow.targets.python.sdk import node

from domain_helpers.arithmetic import scale


@node(**{'type_key': 'example.boundary',
 'display_name': 'Boundary',
 'description': 'A native start or end boundary.',
 'version': '0.15.0',
 'flow_kind': 'terminal',
 'contract': {},
 'rulesets': ['vibeflow.io'],
 'tags': ['flowchart']})
class Boundary:
    def run_pure(self, inputs, params):
        return {}


@node(**{'type_key': 'example.model',
 'display_name': 'ModelBlock',
 'description': 'One model_block block in the example workflow.',
 'version': '0.15.0',
 'flow_kind': 'process',
 'contract': {'requires': [{'type': 'example.input',
                            'cardinality': 'exactly_one',
                            'display_name': 'Input'}],
              'provides': [{'key': 'feature',
                            'type': 'example.feature',
                            'display_name': 'Feature'}],
              'input_semantics': {'example.input': ['Input value for this '
                                                    'functional block.']},
              'output_semantics': {'feature': ['Scaled model output.']},
              'params_schema': {'gain': {'type': 'number'}},
              'params_defaults': {'gain': 2},
              'examples': [{'inputs': {'example.input': {'value': 3}},
                            'params': {'gain': 2}}]},
 'rulesets': ['example.model_domain'],
 'presentation': {'fill': '#cceeff', 'shape': 'rect'},
 'tags': ['model_block']})
class ModelBlock:
    def model_forward(self, value, gain):
        return scale(value, gain)

    def run_pure(self, inputs, params):
        value = inputs["example.input"]["value"]
        return {"feature": self.model_forward(value, params["gain"])}


@node(**{'type_key': 'example.transform',
 'display_name': 'DataTransform',
 'description': 'One data_transform block in the example workflow.',
 'version': '0.15.0',
 'flow_kind': 'process',
 'contract': {'requires': [{'type': 'example.feature',
                            'cardinality': 'exactly_one',
                            'display_name': 'Feature'}],
              'provides': [{'key': 'result',
                            'type': 'example.output',
                            'display_name': 'Result'}],
              'input_semantics': {'example.feature': ['Model result to '
                                                      'transform.']},
              'output_semantics': {'result': ['Model result plus an offset.']},
              'params_schema': {'offset': {'type': 'number'}},
              'params_defaults': {'offset': 1},
              'examples': [{'inputs': {'example.feature': {'value': 6}},
                            'params': {'offset': 1}}]},
 'rulesets': ['example.data_domain'],
 'presentation': {'fill': '#dff7df', 'shape': 'rounded'},
 'tags': ['data_transform']})
class DataTransform:
    def run_pure(self, inputs, params):
        value = inputs["example.feature"]["value"]
        return {"result": value + params["offset"]}
