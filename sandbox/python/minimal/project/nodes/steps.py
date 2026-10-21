from __future__ import annotations

from vibeflow.targets.python.sdk import node
from base_lib.math_tools import add

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

@node(**{'node_type': 'vibeflow.node', 'id': 'example.start',
 'display_name': 'Start',
 'description': 'Starts the example workflow.',
 'version': '0.1.0',
 'flow_kind': 'terminal',
 'author': None,
 'tags': ['example'],
 'external': False,
 'contract': {'requires': [],
              'provides': [],
              'input_semantics': {},
              'output_semantics': {},
              'params_schema': {},
              'params_defaults': {},
              'examples': [{'inputs': {}, 'params': {}}]},
 'rulesets': ['vibeflow.process']})
class StartNode:

    def run_pure(self, inputs, params):
        return {}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.end',
 'display_name': 'End',
 'description': 'Ends after value.out is produced.',
 'version': '0.1.0',
 'flow_kind': 'terminal',
 'author': None,
 'tags': ['example'],
 'external': False,
 'contract': {'requires': [{'type': 'value.out',
                            'cardinality': 'exactly_one',
                            'display_name': 'value.out'}],
              'provides': [],
              'input_semantics': {'value.out': ['final numeric value']},
              'output_semantics': {},
              'params_schema': {},
              'params_defaults': {},
              'examples': [{'inputs': {'value.out': {'key': 'value.out',
                                                     'type': 'value.out',
                                                     'value': 2,
                                                     'source_node': 'example'}},
                            'params': {}}]},
 'rulesets': ['vibeflow.process']})
class EndNode:

    def run_pure(self, inputs, params):
        return {}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.seed',
 'display_name': 'Seed',
 'description': 'Produces the initial value for the example workflow.',
 'version': '0.1.0',
 'flow_kind': 'process',
 'author': None,
 'tags': ['example'],
 'external': False,
 'contract': {'requires': [],
              'provides': [{'key': 'value.in', 'type': 'value.in', 'display_name': 'value.in'}],
              'input_semantics': {},
              'output_semantics': {'value.in': ['initial numeric value']},
              'params_schema': {'value': {'type': 'number'}},
              'params_defaults': {'value': 1},
              'examples': [{'inputs': {}, 'params': {'value': 2}}]},
 'rulesets': ['vibeflow.process']})
class SeedNode:

    def run_pure(self, inputs, params):
        return {'value.in': params.get('value', 1)}

@node(**{'node_type': 'vibeflow.node', 'id': 'example.add',
 'display_name': 'Add',
 'description': 'Adds a configured delta using a pure base_lib helper.',
 'version': '0.1.0',
 'flow_kind': 'process',
 'author': None,
 'tags': ['example'],
 'external': False,
 'contract': {'requires': [{'type': 'value.in',
                            'cardinality': 'exactly_one',
                            'display_name': 'value.in'}],
              'provides': [{'key': 'value.out', 'type': 'value.out', 'display_name': 'value.out'}],
              'input_semantics': {'value.in': ['input numeric value']},
              'output_semantics': {'value.out': ['output numeric value']},
              'params_schema': {'delta': {'type': 'number'}},
              'params_defaults': {'delta': 1},
              'examples': [{'inputs': {'value.in': {'key': 'value.in',
                                                    'type': 'value.in',
                                                    'value': 2,
                                                    'source_node': 'example'}},
                            'params': {'delta': 3}}]},
 'base_libs':['base_lib.math_tools'],
 'rulesets': ['vibeflow.process']})
class AddNode:

    def run_pure(self, inputs, params):
        return {'value.out': add(VALUE(inputs, 'value.in'), params.get('delta', 1))}
