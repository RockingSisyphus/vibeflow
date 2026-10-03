"""Execution only; registration and audit selection live in the bundle."""

from vibeflow.targets.python.sdk import node

from vibeflow.targets.python.sdk import node

@node(**{'type_key': 'example.boundary',
 'display_name': 'Boundary',
 'description': 'An executable Node in the typed Rule graph example.',
 'version': '0.15.0',
 'flow_kind': 'terminal',
 'contract': {},
 'rulesets': [],
 'tags': ['rule_graph']})
class Boundary:
    def run_pure(self, inputs, params):
        return {}

@node(**{'type_key': 'example.calculate',
 'display_name': 'Calculate',
 'description': 'An executable Node in the typed Rule graph example.',
 'version': '0.15.0',
 'flow_kind': 'process',
 'contract': {'requires': [{'type': 'example.input',
                            'cardinality': 'exactly_one',
                            'display_name': 'Input'}],
              'provides': [{'key': 'result',
                            'type': 'example.output',
                            'display_name': 'Result'}],
              'input_semantics': {'example.input': ['The number to '
                                                    'calculate.']},
              'output_semantics': {'result': ['Twice the number plus one.']}},
 'rulesets': ['example.rule_graph'],
 'tags': ['rule_graph']})
class Calculate:
    def run_pure(self, inputs, params):
        return {"result": inputs["example.input"]["value"] * 2 + 1}
