from __future__ import annotations
from base_lib.math_tools import add

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class StartNode:

    def run_pure(self, inputs, params):
        return {}

class EndNode:

    def run_pure(self, inputs, params):
        return {}

class SeedNode:

    def run_pure(self, inputs, params):
        return {'value.in': params.get('value', 1)}

class AddNode:

    def run_pure(self, inputs, params):
        return {'value.out': add(VALUE(inputs, 'value.in'), params.get('delta', 1))}
