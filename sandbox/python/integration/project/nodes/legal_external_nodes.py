from __future__ import annotations

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class EffectRequestNode:

    def run_pure(self, inputs, params):
        return {'effects.request': {'value': params.get('value', 1)}}

class IoResultAddNode:

    def run_pure(self, inputs, params):
        return {'value.final': VALUE(inputs, 'io.result') + params.get('delta', 1)}

class IoResultInputNode:

    def run_pure(self, inputs, params):
        return {'value.in': VALUE(inputs, 'io.result') + params.get('delta', 1)}
