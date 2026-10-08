from __future__ import annotations
from math import nan

class DynamicOutputKeyNode:

    def run_pure(self, inputs, params):
        key = 'bad.out'
        return {key: 1}

class MissingOutputNode:

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class ExtraOutputNode:

    def run_pure(self, inputs, params):
        return {'bad.out': 1, 'bad.extra': 2}

class MutateInputsNode:

    def run_pure(self, inputs, params):
        inputs['bad.in'] = 2
        return {'bad.out': 1}

class MutateNestedInputNode:

    def run_pure(self, inputs, params):
        items = inputs['bad.items']
        items.append(1)
        return {'bad.out': 1}

class UndeclaredParamNode:

    def run_pure(self, inputs, params):
        return {'bad.out': params.get('x', 1)}

class SetOutputNode:

    def run_pure(self, inputs, params):
        return {'bad.out': {1, 2}}

class NaNOutputNode:

    def run_pure(self, inputs, params):
        return {'bad.out': nan}
