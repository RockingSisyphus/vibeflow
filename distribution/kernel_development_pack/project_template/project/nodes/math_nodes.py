from __future__ import annotations
from base_lib.math_tools import add
from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo

def REQ(data_type: str, cardinality: str='exactly_one') -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality)

def PROV(key: str, data_type: str | None=None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key)

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class StartNode:
    NODE_INFO = NodeInfo(type_key='demo.start', display_name='Start', category='demo', description='Terminal start node for the demo workflow.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(examples=({'inputs': {}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class EndNode:
    NODE_INFO = NodeInfo(type_key='demo.end', display_name='End', category='demo', description='Terminal end node after value.out is produced.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(requires=(REQ('value.out'),), input_semantics={'value.out': ('final numeric value',)}, examples=({'inputs': {'value.out': {'key': 'value.out', 'type': 'value.out', 'value': 5, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class SeedNode:
    NODE_INFO = NodeInfo(type_key='demo.seed', display_name='Seed', category='demo', description='Provide an initial numeric value.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(provides=(PROV('value.in'),), output_semantics={'value.in': ('initial numeric value',)}, params_schema={'value': {'type': 'number'}}, output_schema={'value.in': {'type': 'number'}}, examples=({'inputs': {}, 'params': {'value': 2}},))

    def run_pure(self, inputs, params):
        return {'value.in': params['value']}

class AddNode:
    NODE_INFO = NodeInfo(type_key='demo.add', display_name='Add', category='demo', description='Add a configured delta.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('value.in'),), provides=(PROV('value.out'),), input_semantics={'value.in': ('input numeric value',)}, output_semantics={'value.out': ('output numeric value',)}, params_schema={'delta': {'type': 'number'}}, output_schema={'value.out': {'type': 'number'}}, examples=({'inputs': {'value.in': {'key': 'value.in', 'type': 'value.in', 'value': 2, 'source_node': 'example'}}, 'params': {'delta': 3}},))

    def run_pure(self, inputs, params):
        return {'value.out': add(VALUE(inputs, 'value.in'), params['delta'])}
