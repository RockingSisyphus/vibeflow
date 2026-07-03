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
    NODE_INFO = NodeInfo(type_key='example.start', display_name='Start', category='example', description='Starts the example workflow.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(examples=({'inputs': {}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class EndNode:
    NODE_INFO = NodeInfo(type_key='example.end', display_name='End', category='example', description='Ends after value.out is produced.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(requires=(REQ('value.out'),), input_semantics={'value.out': ('final numeric value',)}, examples=({'inputs': {'value.out': {'key': 'value.out', 'type': 'value.out', 'value': 2, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class SeedNode:
    NODE_INFO = NodeInfo(type_key='example.seed', display_name='Seed', category='example', description='Produces the initial value for the example workflow.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(provides=(PROV('value.in'),), output_semantics={'value.in': ('initial numeric value',)}, params_schema={'value': {'type': 'number'}}, output_schema={'value.in': {'type': 'number'}}, examples=({'inputs': {}, 'params': {'value': 2}},))

    def run_pure(self, inputs, params):
        return {'value.in': params.get('value', 1)}

class AddNode:
    NODE_INFO = NodeInfo(type_key='example.add', display_name='Add', category='example', description='Adds a configured delta using a pure base_lib helper.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('value.in'),), provides=(PROV('value.out'),), input_semantics={'value.in': ('input numeric value',)}, output_semantics={'value.out': ('output numeric value',)}, params_schema={'delta': {'type': 'number'}}, output_schema={'value.out': {'type': 'number'}}, examples=({'inputs': {'value.in': {'key': 'value.in', 'type': 'value.in', 'value': 2, 'source_node': 'example'}}, 'params': {'delta': 3}},))

    def run_pure(self, inputs, params):
        return {'value.out': add(VALUE(inputs, 'value.in'), params.get('delta', 1))}
