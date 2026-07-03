from __future__ import annotations
from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo

def REQ(data_type: str, cardinality: str='exactly_one') -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality)

def PROV(key: str, data_type: str | None=None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key)

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class SemanticAddPairNode:
    NODE_INFO = NodeInfo(type_key='semantic.add_pair', display_name='Semantic Add Pair', category='semantic', description='Adds calc.a and calc.b into calc.sum for arithmetic acceptance flows.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('calc.a'), REQ('calc.b')), provides=(PROV('calc.sum'),), input_semantics={'calc.a': ('left numeric addend',), 'calc.b': ('right numeric addend',)}, output_semantics={'calc.sum': ('sum of calc.a and calc.b',)}, output_schema={'calc.sum': {'type': 'number'}}, examples=({'inputs': {'calc.a': {'key': 'calc.a', 'type': 'calc.a', 'value': 2, 'source_node': 'example'}, 'calc.b': {'key': 'calc.b', 'type': 'calc.b', 'value': 5, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {'calc.sum': VALUE(inputs, 'calc.a') + VALUE(inputs, 'calc.b')}

class SemanticScaleNode:
    NODE_INFO = NodeInfo(type_key='semantic.scale', display_name='Semantic Scale', category='semantic', description='Multiplies calc.sum by a configured factor into calc.scaled.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('calc.sum'),), provides=(PROV('calc.scaled'),), input_semantics={'calc.sum': ('numeric sum to multiply',)}, output_semantics={'calc.scaled': ('calc.sum multiplied by factor',)}, params_schema={'factor': {'type': 'number'}}, output_schema={'calc.scaled': {'type': 'number'}}, examples=({'inputs': {'calc.sum': {'key': 'calc.sum', 'type': 'calc.sum', 'value': 7, 'source_node': 'example'}}, 'params': {'factor': 3}},))

    def run_pure(self, inputs, params):
        return {'calc.scaled': VALUE(inputs, 'calc.sum') * params.get('factor', 1)}

class SemanticUseScaledNode:
    NODE_INFO = NodeInfo(type_key='semantic.use_scaled', display_name='Semantic Use Scaled', category='semantic', description='Promotes calc.scaled to calc.branch so finalization has one stable input key.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('calc.scaled'),), provides=(PROV('calc.branch'),), input_semantics={'calc.scaled': ('scaled arithmetic value',)}, output_semantics={'calc.branch': ('branch value copied from calc.scaled',)}, output_schema={'calc.branch': {'type': 'number'}}, examples=({'inputs': {'calc.scaled': {'key': 'calc.scaled', 'type': 'calc.scaled', 'value': 21, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {'calc.branch': VALUE(inputs, 'calc.scaled')}

class SemanticCompareGtNode:
    NODE_INFO = NodeInfo(type_key='semantic.compare_gt', display_name='Semantic Compare Greater Than', category='semantic', description='Compares calc.c and calc.d and emits route.branch for left or right branch selection.', version='0.1.0', flow_kind='decision')
    CONTRACT = NodeContract(requires=(REQ('calc.c'), REQ('calc.d')), provides=(PROV('route.branch'),), input_semantics={'calc.c': ('left comparison value',), 'calc.d': ('right comparison value',)}, output_semantics={'route.branch': ('left when calc.c > calc.d, otherwise right',)}, output_schema={'route.branch': {'type': 'string', 'enum': ['left', 'right']}}, examples=({'inputs': {'calc.c': {'key': 'calc.c', 'type': 'calc.c', 'value': 9, 'source_node': 'example'}, 'calc.d': {'key': 'calc.d', 'type': 'calc.d', 'value': 4, 'source_node': 'example'}}, 'params': {}}, {'inputs': {'calc.c': {'key': 'calc.c', 'type': 'calc.c', 'value': 1, 'source_node': 'example'}, 'calc.d': {'key': 'calc.d', 'type': 'calc.d', 'value': 4, 'source_node': 'example'}}, 'params': {}}))

    def run_pure(self, inputs, params):
        return {'route.branch': 'left' if VALUE(inputs, 'calc.c') > VALUE(inputs, 'calc.d') else 'right'}

class SemanticLeftAdjustNode:
    NODE_INFO = NodeInfo(type_key='semantic.left_adjust', display_name='Semantic Left Adjust', category='semantic', description='Adds a configured bonus to calc.scaled after the left decision branch is selected.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('calc.scaled'),), provides=(PROV('calc.left_branch'),), input_semantics={'calc.scaled': ('scaled arithmetic value selected for the left branch',)}, output_semantics={'calc.left_branch': ('left branch value after adding bonus',)}, params_schema={'bonus': {'type': 'number'}}, output_schema={'calc.left_branch': {'type': 'number'}}, examples=({'inputs': {'calc.scaled': {'key': 'calc.scaled', 'type': 'calc.scaled', 'value': 21, 'source_node': 'example'}}, 'params': {'bonus': 10}},))

    def run_pure(self, inputs, params):
        return {'calc.left_branch': VALUE(inputs, 'calc.scaled') + params.get('bonus', 0)}

class SemanticRightAdjustNode:
    NODE_INFO = NodeInfo(type_key='semantic.right_adjust', display_name='Semantic Right Adjust', category='semantic', description='Subtracts a configured penalty from calc.scaled after the right decision branch is selected.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('calc.scaled'),), provides=(PROV('calc.right_branch'),), input_semantics={'calc.scaled': ('scaled arithmetic value selected for the right branch',)}, output_semantics={'calc.right_branch': ('right branch value after subtracting penalty',)}, params_schema={'penalty': {'type': 'number'}}, output_schema={'calc.right_branch': {'type': 'number'}}, examples=({'inputs': {'calc.scaled': {'key': 'calc.scaled', 'type': 'calc.scaled', 'value': 21, 'source_node': 'example'}}, 'params': {'penalty': 6}},))

    def run_pure(self, inputs, params):
        return {'calc.right_branch': VALUE(inputs, 'calc.scaled') - params.get('penalty', 0)}

class SemanticBranchTypeConsumerNode:
    NODE_INFO = NodeInfo(type_key='semantic.branch_type_consumer', display_name='Semantic Branch Type Consumer', category='semantic', description='Consumes one branch_result envelope and uses its source key to produce a source-aware final value.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('branch_result'),), provides=(PROV('branch.final', 'final_result'),), input_semantics={'branch_result': ('one selected branch result envelope',)}, output_semantics={'branch.final': ('source-aware final branch value',)}, output_schema={'branch.final': {'type': 'number'}}, examples=({'inputs': {'branch_result': {'key': 'calc.left_branch', 'type': 'branch_result', 'value': 31, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        envelope = inputs['branch_result']
        value = envelope['value']
        source_key = envelope['key']
        source_bonus = 100 if source_key == 'calc.left_branch' else 200
        return {'branch.final': value + source_bonus}

class SemanticBranchFinalEndNode:
    NODE_INFO = NodeInfo(type_key='semantic.branch_final_end', display_name='Semantic Branch Final End', category='semantic', description='Terminates a strict key/type branch flow after final_result is available.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(requires=(REQ('final_result'),), input_semantics={'final_result': ('source-aware final branch result',)}, examples=({'inputs': {'final_result': {'key': 'branch.final', 'type': 'final_result', 'value': 131, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class SemanticFinalizeNode:
    NODE_INFO = NodeInfo(type_key='semantic.finalize', display_name='Semantic Finalize', category='semantic', description='Adds a configured offset to calc.branch into calc.final.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('calc.branch'),), provides=(PROV('calc.final'),), input_semantics={'calc.branch': ('branch or promoted scaled value to finalize',)}, output_semantics={'calc.final': ('calc.branch plus offset',)}, params_schema={'offset': {'type': 'number'}}, output_schema={'calc.final': {'type': 'number'}}, examples=({'inputs': {'calc.branch': {'key': 'calc.branch', 'type': 'calc.branch', 'value': 31, 'source_node': 'example'}}, 'params': {'offset': 1}},))

    def run_pure(self, inputs, params):
        return {'calc.final': VALUE(inputs, 'calc.branch') + params.get('offset', 0)}

class SemanticIncrementUntilNode:
    NODE_INFO = NodeInfo(type_key='semantic.increment_until', display_name='Semantic Increment Until', category='semantic', description='Adds a configured step to loop.current into loop.next.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('loop.current'),), provides=(PROV('loop.next'),), input_semantics={'loop.current': ('current loop value before increment',)}, output_semantics={'loop.next': ('loop.current plus step',)}, params_schema={'step': {'type': 'number'}}, output_schema={'loop.next': {'type': 'number'}}, examples=({'inputs': {'loop.current': {'key': 'loop.current', 'type': 'loop.current', 'value': 1, 'source_node': 'example'}}, 'params': {'step': 2}},))

    def run_pure(self, inputs, params):
        return {'loop.next': VALUE(inputs, 'loop.current') + params.get('step', 1)}

class SemanticLoopDoneNode:
    NODE_INFO = NodeInfo(type_key='semantic.loop_done', display_name='Semantic Loop Done', category='semantic', description='Compares loop.next with target and emits loop.done for loop routing.', version='0.1.0', flow_kind='decision')
    CONTRACT = NodeContract(requires=(REQ('loop.next'),), provides=(PROV('loop.done'),), input_semantics={'loop.next': ('candidate loop value after increment',)}, output_semantics={'loop.done': ('true when loop.next is greater than or equal to target',)}, params_schema={'target': {'type': 'number'}}, output_schema={'loop.done': {'type': 'boolean'}}, examples=({'inputs': {'loop.next': {'key': 'loop.next', 'type': 'loop.next', 'value': 5, 'source_node': 'example'}}, 'params': {'target': 7}}, {'inputs': {'loop.next': {'key': 'loop.next', 'type': 'loop.next', 'value': 7, 'source_node': 'example'}}, 'params': {'target': 7}}))

    def run_pure(self, inputs, params):
        return {'loop.done': VALUE(inputs, 'loop.next') >= params.get('target', 0)}

class SemanticCopyNextNode:
    NODE_INFO = NodeInfo(type_key='semantic.copy_next', display_name='Semantic Copy Next', category='semantic', description='Copies loop.next back into loop.current for the next loop iteration.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('loop.next'),), provides=(PROV('loop.current.copy', 'loop.current'),), input_semantics={'loop.next': ('latest loop value to reuse',)}, output_semantics={'loop.current.copy': ('next loop iteration input',)}, output_schema={'loop.current.copy': {'type': 'number'}}, examples=({'inputs': {'loop.next': {'key': 'loop.next', 'type': 'loop.next', 'value': 3, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {'loop.current.copy': VALUE(inputs, 'loop.next')}

class SemanticScaledEndNode:
    NODE_INFO = NodeInfo(type_key='semantic.scaled_end', display_name='Semantic Scaled End', category='semantic', description='Terminates a nested semantic flow after calc.scaled is available.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(requires=(REQ('calc.scaled'),), input_semantics={'calc.scaled': ('scaled arithmetic output',)}, examples=({'inputs': {'calc.scaled': {'key': 'calc.scaled', 'type': 'calc.scaled', 'value': 20, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class SemanticFinalEndNode:
    NODE_INFO = NodeInfo(type_key='semantic.final_end', display_name='Semantic Final End', category='semantic', description='Terminates a semantic flow after calc.final is available.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(requires=(REQ('calc.final'),), input_semantics={'calc.final': ('final arithmetic acceptance output',)}, examples=({'inputs': {'calc.final': {'key': 'calc.final', 'type': 'calc.final', 'value': 17, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class SemanticLeftBranchEndNode:
    NODE_INFO = NodeInfo(type_key='semantic.left_branch_end', display_name='Semantic Left Branch End', category='semantic', description='Terminates a semantic branch flow after calc.left_branch is available.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(requires=(REQ('calc.left_branch'),), input_semantics={'calc.left_branch': ('final left branch arithmetic output',)}, examples=({'inputs': {'calc.left_branch': {'key': 'calc.left_branch', 'type': 'calc.left_branch', 'value': 31, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class SemanticRightBranchEndNode:
    NODE_INFO = NodeInfo(type_key='semantic.right_branch_end', display_name='Semantic Right Branch End', category='semantic', description='Terminates a semantic branch flow after calc.right_branch is available.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(requires=(REQ('calc.right_branch'),), input_semantics={'calc.right_branch': ('final right branch arithmetic output',)}, examples=({'inputs': {'calc.right_branch': {'key': 'calc.right_branch', 'type': 'calc.right_branch', 'value': 15, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class SemanticLoopEndNode:
    NODE_INFO = NodeInfo(type_key='semantic.loop_end', display_name='Semantic Loop End', category='semantic', description='Terminates a semantic loop after loop.next reaches the target.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(requires=(REQ('loop.next'),), input_semantics={'loop.next': ('final loop value',)}, examples=({'inputs': {'loop.next': {'key': 'loop.next', 'type': 'loop.next', 'value': 7, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class SemanticSlowAsyncValueNode:
    NODE_INFO = NodeInfo(type_key='semantic.slow_async_value', display_name='Semantic Slow Async Value', category='semantic', description='Produces a value used to prove inactive result-key async consumers are not joined.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(provides=(PROV('async.value'),), output_semantics={'async.value': ('slow async value that should remain unconsumed',)}, output_schema={'async.value': {'type': 'number'}}, params_schema={'value': {'type': 'number'}}, examples=({'inputs': {}, 'params': {'value': 42}},))

    def run_pure(self, inputs, params):
        return {'async.value': params.get('value', 42)}

class SemanticAsyncValueEndNode:
    NODE_INFO = NodeInfo(type_key='semantic.async_value_end', display_name='Semantic Async Value End', category='semantic', description='Inactive terminal branch that would consume async.value if scheduled.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(requires=(REQ('async.value'),), input_semantics={'async.value': ('async result-key value',)}, examples=({'inputs': {'async.value': {'key': 'async.value', 'type': 'async.value', 'value': 99, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}
