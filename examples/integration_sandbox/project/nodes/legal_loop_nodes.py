from __future__ import annotations
from base_lib.good_math import is_done
from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo

def REQ(data_type: str, cardinality: str='exactly_one') -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality)

def PROV(key: str, data_type: str | None=None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key)

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class IncrementNode:
    NODE_INFO = NodeInfo(type_key='sandbox.increment', display_name='Increment', category='sandbox', description='Increments value.in by one.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('value.in'),), provides=(PROV('value.next'),), input_semantics={'value.in': ('current value',)}, output_semantics={'value.next': ('next value',)}, output_schema={'value.next': {'type': 'number'}}, examples=({'inputs': {'value.in': {'key': 'value.in', 'type': 'value.in', 'value': 1, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {'value.next': VALUE(inputs, 'value.in') + 1}

class CopyBackNode:
    NODE_INFO = NodeInfo(type_key='sandbox.copy_back', display_name='Copy Back', category='sandbox', description='Copies value.next back to value.in for the next loop iteration.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('value.next'), REQ('loop.done')), provides=(PROV('value.in.copy', 'value.in'),), input_semantics={'value.next': ('next value',), 'loop.done': ('whether the loop should stop',)}, output_semantics={'value.in.copy': ('loop current value for the next iteration',)}, output_schema={'value.in.copy': {'type': 'number'}}, examples=({'inputs': {'value.next': {'key': 'value.next', 'type': 'value.next', 'value': 2, 'source_node': 'example'}, 'loop.done': {'key': 'loop.done', 'type': 'loop.done', 'value': False, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {'value.in.copy': VALUE(inputs, 'value.next')}

class DoneCheckNode:
    NODE_INFO = NodeInfo(type_key='sandbox.done_check', display_name='Done Check', category='sandbox', description='Checks whether the loop reached its target.', version='0.1.0', flow_kind='decision')
    CONTRACT = NodeContract(requires=(REQ('value.next'),), provides=(PROV('loop.done'),), input_semantics={'value.next': ('next value',)}, output_semantics={'loop.done': ('whether the loop should stop',)}, params_schema={'target': {'type': 'number'}}, output_schema={'loop.done': {'type': 'boolean'}}, examples=({'inputs': {'value.next': {'key': 'value.next', 'type': 'value.next', 'value': 3, 'source_node': 'example'}}, 'params': {'target': 3}},))

    def run_pure(self, inputs, params):
        return {'loop.done': is_done(VALUE(inputs, 'value.next'), params.get('target', 3))}
