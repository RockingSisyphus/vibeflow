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

class SemanticJoinPassthroughNode:
    NODE_INFO = NodeInfo(type_key='semantic.join_passthrough', display_name='Semantic Join Passthrough', category='semantic', description='Consumes one value.in envelope and emits value.out without changing the selected branch value.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('value.in'),), provides=(PROV('value.out'),), input_semantics={'value.in': ('value selected by a safe join',)}, output_semantics={'value.out': ('selected value after the join',)}, output_schema={'value.out': {'type': 'number'}}, examples=({'inputs': {'value.in': {'key': 'value.left', 'type': 'value.in', 'value': 3, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {'value.out': VALUE(inputs, 'value.in')}

class SemanticValueEndNode:
    NODE_INFO = NodeInfo(type_key='semantic.value_end', display_name='Semantic Value End', category='semantic', description='Terminates a semantic join flow after value.out is available.', version='0.1.0', flow_kind='terminal')
    CONTRACT = NodeContract(requires=(REQ('value.out'),), input_semantics={'value.out': ('final value selected by a join',)}, examples=({'inputs': {'value.out': {'key': 'value.out', 'type': 'value.out', 'value': 3, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}

class SemanticInactiveRouteNode:
    NODE_INFO = NodeInfo(type_key='semantic.inactive_route', display_name='Semantic Inactive Route', category='semantic', description='Emits an inactive boolean route used to verify explicit any_active join behavior.', version='0.1.0', flow_kind='decision')
    CONTRACT = NodeContract(provides=(PROV('flow.route'),), output_semantics={'flow.route': ('false route condition',)}, output_schema={'flow.route': {'type': 'boolean'}}, examples=({'inputs': {}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {'flow.route': False}

class SemanticConditionalValueNode:
    NODE_INFO = NodeInfo(type_key='semantic.conditional_value', display_name='Semantic Conditional Value', category='semantic', description='Produces a value.in-compatible branch value plus an active route flag.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(provides=(PROV('value.alt', 'value.in'), PROV('flow.use_alt')), output_semantics={'value.alt': ('conditional value.in provider',), 'flow.use_alt': ('true route condition',)}, params_schema={'value': {'type': 'number'}}, output_schema={'value.alt': {'type': 'number'}, 'flow.use_alt': {'type': 'boolean'}}, examples=({'inputs': {}, 'params': {'value': 7}},))

    def run_pure(self, inputs, params):
        return {'value.alt': params.get('value', 7), 'flow.use_alt': True}

class SemanticLeftValueNode:
    NODE_INFO = NodeInfo(type_key='semantic.left_value', display_name='Semantic Left Value', category='semantic', description='Produces a left value.in-compatible provider for join conflict tests.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(provides=(PROV('value.left', 'value.in'),), output_semantics={'value.left': ('left value provider',)}, params_schema={'value': {'type': 'number'}}, output_schema={'value.left': {'type': 'number'}}, examples=({'inputs': {}, 'params': {'value': 1}},))

    def run_pure(self, inputs, params):
        return {'value.left': params.get('value', 1)}

class SemanticRightValueNode:
    NODE_INFO = NodeInfo(type_key='semantic.right_value', display_name='Semantic Right Value', category='semantic', description='Produces a right value.in-compatible provider for join conflict tests.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(provides=(PROV('value.right', 'value.in'),), output_semantics={'value.right': ('right value provider',)}, params_schema={'value': {'type': 'number'}}, output_schema={'value.right': {'type': 'number'}}, examples=({'inputs': {}, 'params': {'value': 2}},))

    def run_pure(self, inputs, params):
        return {'value.right': params.get('value', 2)}

class SemanticOtherValueNode:
    NODE_INFO = NodeInfo(type_key='semantic.other_value', display_name='Semantic Other Value', category='semantic', description='Produces other.in for explicit all-join tests.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(provides=(PROV('other.in'),), output_semantics={'other.in': ('secondary join input',)}, params_schema={'value': {'type': 'number'}}, output_schema={'other.in': {'type': 'number'}}, examples=({'inputs': {}, 'params': {'value': 5}},))

    def run_pure(self, inputs, params):
        return {'other.in': params.get('value', 5)}

class SemanticTwoInputJoinNode:
    NODE_INFO = NodeInfo(type_key='semantic.two_input_join', display_name='Semantic Two Input Join', category='semantic', description='Consumes value.in and other.in after an explicit all join.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('value.in'), REQ('other.in')), provides=(PROV('value.out'),), input_semantics={'value.in': ('primary join input',), 'other.in': ('secondary join input',)}, output_semantics={'value.out': ('sum of both join inputs',)}, output_schema={'value.out': {'type': 'number'}}, examples=({'inputs': {'value.in': {'key': 'value.left', 'type': 'value.in', 'value': 3, 'source_node': 'example'}, 'other.in': {'key': 'other.in', 'type': 'other.in', 'value': 5, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {'value.out': VALUE(inputs, 'value.in') + VALUE(inputs, 'other.in')}

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

class SemanticLoopDoneValueNode:
    NODE_INFO = NodeInfo(type_key='semantic.loop_done_value', display_name='Semantic Loop Done Value', category='semantic', description='Compares loop.next with target and emits loop.done as data for while-loop stop_when.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('loop.next'),), provides=(PROV('loop.done'),), input_semantics={'loop.next': ('candidate loop value after increment',)}, output_semantics={'loop.done': ('true when loop.next is greater than or equal to target',)}, params_schema={'target': {'type': 'number'}}, output_schema={'loop.done': {'type': 'boolean'}}, examples=({'inputs': {'loop.next': {'key': 'loop.next', 'type': 'loop.next', 'value': 5, 'source_node': 'example'}}, 'params': {'target': 7}},))

    def run_pure(self, inputs, params):
        return {'loop.done': VALUE(inputs, 'loop.next') >= params.get('target', 0)}

class SemanticNestedLoopSeedNode:
    NODE_INFO = NodeInfo(type_key='semantic.nested_loop_seed', display_name='Semantic Nested Loop Seed', category='semantic', description='Creates the initial outer counter and running total for nested while-loop sandbox fixtures.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(provides=(PROV('outer.current'), PROV('total.current')), output_semantics={'outer.current': ('initial outer loop counter',), 'total.current': ('initial nested-loop accumulator',)}, params_schema={'outer_start': {'type': 'number'}, 'total_start': {'type': 'number'}}, output_schema={'outer.current': {'type': 'number'}, 'total.current': {'type': 'number'}}, examples=({'inputs': {}, 'params': {'outer_start': 0, 'total_start': 0}},))

    def run_pure(self, inputs, params):
        return {'outer.current': params.get('outer_start', 0), 'total.current': params.get('total_start', 0)}

class SemanticInnerLoopInitNode:
    NODE_INFO = NodeInfo(type_key='semantic.inner_loop_init', display_name='Semantic Inner Loop Init', category='semantic', description='Passes outer state through and initializes the inner counter before a nested inner loop.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('outer.current'), REQ('total.current')), provides=(PROV('outer.inner.seed', 'outer.inner'), PROV('total.inner.seed', 'total.inner'), PROV('inner.current.seed', 'inner.current')), input_semantics={'outer.current': ('current outer loop counter',), 'total.current': ('running nested-loop total',)}, output_semantics={'outer.inner.seed': ('outer counter passed into the inner loop',), 'total.inner.seed': ('running total passed into the inner loop',), 'inner.current.seed': ('fresh inner loop counter',)}, params_schema={'inner_start': {'type': 'number'}}, output_schema={'outer.inner.seed': {'type': 'number'}, 'total.inner.seed': {'type': 'number'}, 'inner.current.seed': {'type': 'number'}}, examples=({'inputs': {'outer.current': {'key': 'outer.current', 'type': 'outer.current', 'value': 1, 'source_node': 'example'}, 'total.current': {'key': 'total.current', 'type': 'total.current', 'value': 3, 'source_node': 'example'}}, 'params': {'inner_start': 0}},))

    def run_pure(self, inputs, params):
        return {
            'outer.inner.seed': VALUE(inputs, 'outer.current'),
            'total.inner.seed': VALUE(inputs, 'total.current'),
            'inner.current.seed': params.get('inner_start', 0),
        }

class SemanticInnerAccumulateNode:
    NODE_INFO = NodeInfo(type_key='semantic.inner_accumulate', display_name='Semantic Inner Accumulate', category='semantic', description='Adds one nested outer/inner contribution, advances the inner counter, and emits a bool stop signal.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('outer.inner'), REQ('inner.current'), REQ('total.inner')), provides=(PROV('outer.inner.next', 'outer.inner'), PROV('inner.current.next', 'inner.current'), PROV('total.inner.next', 'total.inner'), PROV('inner.done')), input_semantics={'outer.inner': ('current outer loop counter inside the inner loop',), 'inner.current': ('current inner loop counter',), 'total.inner': ('running nested-loop total before this contribution',)}, output_semantics={'outer.inner.next': ('outer counter carried through unchanged',), 'inner.current.next': ('next inner loop counter',), 'total.inner.next': ('running total after adding outer + inner + 1',), 'inner.done': ('true when the next inner counter reaches the configured limit',)}, params_schema={'inner_step': {'type': 'number'}, 'inner_limit': {'type': 'number'}}, output_schema={'outer.inner.next': {'type': 'number'}, 'inner.current.next': {'type': 'number'}, 'total.inner.next': {'type': 'number'}, 'inner.done': {'type': 'boolean'}}, examples=({'inputs': {'outer.inner': {'key': 'outer.inner.seed', 'type': 'outer.inner', 'value': 1, 'source_node': 'example'}, 'inner.current': {'key': 'inner.current.seed', 'type': 'inner.current', 'value': 2, 'source_node': 'example'}, 'total.inner': {'key': 'total.inner.seed', 'type': 'total.inner', 'value': 5, 'source_node': 'example'}}, 'params': {'inner_step': 1, 'inner_limit': 3}},))

    def run_pure(self, inputs, params):
        outer = VALUE(inputs, 'outer.inner')
        inner = VALUE(inputs, 'inner.current')
        total = VALUE(inputs, 'total.inner')
        step = params.get('inner_step', 1)
        next_inner = inner + step
        return {
            'outer.inner.next': outer,
            'inner.current.next': next_inner,
            'total.inner.next': total + outer + inner + 1,
            'inner.done': next_inner >= params.get('inner_limit', 1),
        }

class SemanticOuterAdvanceNode:
    NODE_INFO = NodeInfo(type_key='semantic.outer_advance', display_name='Semantic Outer Advance', category='semantic', description='Passes the inner-loop total out, advances the outer counter, and emits the outer bool stop signal.', version='0.1.0', flow_kind='process')
    CONTRACT = NodeContract(requires=(REQ('outer.inner'), REQ('total.inner')), provides=(PROV('outer.current.next', 'outer.current'), PROV('total.current.next', 'total.current'), PROV('outer.done')), input_semantics={'outer.inner': ('outer loop counter before advance',), 'total.inner': ('running total after the inner loop',)}, output_semantics={'outer.current.next': ('next outer loop counter',), 'total.current.next': ('running total carried to the next outer iteration',), 'outer.done': ('true when the next outer counter reaches the configured limit',)}, params_schema={'outer_step': {'type': 'number'}, 'outer_limit': {'type': 'number'}}, output_schema={'outer.current.next': {'type': 'number'}, 'total.current.next': {'type': 'number'}, 'outer.done': {'type': 'boolean'}}, examples=({'inputs': {'outer.inner': {'key': 'outer.inner', 'type': 'outer.inner', 'value': 1, 'source_node': 'example'}, 'total.inner': {'key': 'total.inner', 'type': 'total.inner', 'value': 8, 'source_node': 'example'}}, 'params': {'outer_step': 1, 'outer_limit': 2}},))

    def run_pure(self, inputs, params):
        outer = VALUE(inputs, 'outer.inner')
        next_outer = outer + params.get('outer_step', 1)
        return {
            'outer.current.next': next_outer,
            'total.current.next': VALUE(inputs, 'total.inner'),
            'outer.done': next_outer >= params.get('outer_limit', 1),
        }

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
