from __future__ import annotations
from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo

def REQ(data_type: str, cardinality: str='exactly_one') -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality)

def PROV(key: str, data_type: str | None=None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key)

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class EffectRequestNode:
    NODE_INFO = NodeInfo(type_key='sandbox.effect_request', display_name='Effect Request', category='sandbox', description='Expresses an external effect request as data.', version='0.1.0', flow_kind='data_store')
    CONTRACT = NodeContract(provides=(PROV('effects.request'),), output_semantics={'effects.request': ('structured request for an external effect',)}, params_schema={'value': {'type': 'number'}}, output_schema={'effects.request': {'type': 'object'}}, examples=({'inputs': {}, 'params': {'value': 5}},))

    def run_pure(self, inputs, params):
        return {'effects.request': {'value': params.get('value', 1)}}

class IoResultAddNode:
    NODE_INFO = NodeInfo(type_key='sandbox.io_result_add', display_name='IO Result Add', category='sandbox', description='Adds a configured delta to an external IO result.', version='0.1.0', flow_kind='io')
    CONTRACT = NodeContract(requires=(REQ('io.result'),), provides=(PROV('value.final'),), input_semantics={'io.result': ('external numeric result',)}, output_semantics={'value.final': ('final numeric value',)}, params_schema={'delta': {'type': 'number'}}, output_schema={'value.final': {'type': 'number'}}, examples=({'inputs': {'io.result': {'key': 'io.result', 'type': 'io.result', 'value': 7, 'source_node': 'example'}}, 'params': {'delta': 1}},))

    def run_pure(self, inputs, params):
        return {'value.final': VALUE(inputs, 'io.result') + params.get('delta', 1)}

class IoResultInputNode:
    NODE_INFO = NodeInfo(type_key='sandbox.io_result_input', display_name='IO Result Input', category='sandbox', description='Converts an external IO result into value.in for a downstream nodeset.', version='0.1.0', flow_kind='io')
    CONTRACT = NodeContract(requires=(REQ('io.result'),), provides=(PROV('value.in'),), input_semantics={'io.result': ('external numeric result',)}, output_semantics={'value.in': ('numeric input for downstream flow',)}, params_schema={'delta': {'type': 'number'}}, output_schema={'value.in': {'type': 'number'}}, examples=({'inputs': {'io.result': {'key': 'io.result', 'type': 'io.result', 'value': 7, 'source_node': 'example'}}, 'params': {'delta': 1}},))

    def run_pure(self, inputs, params):
        return {'value.in': VALUE(inputs, 'io.result') + params.get('delta', 1)}
