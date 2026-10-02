from __future__ import annotations
from base_lib.good_math import is_done

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class IncrementNode:

    def run_pure(self, inputs, params):
        return {'value.next': VALUE(inputs, 'value.in') + 1}

class CopyBackNode:

    def run_pure(self, inputs, params):
        return {'value.in.copy': VALUE(inputs, 'value.next')}

class DoneCheckNode:

    def run_pure(self, inputs, params):
        return {'loop.done': is_done(VALUE(inputs, 'value.next'), params.get('target', 3))}

class DoneValueNode:

    def run_pure(self, inputs, params):
        return {'loop.done': is_done(VALUE(inputs, 'value.next'), params.get('target', 3))}
