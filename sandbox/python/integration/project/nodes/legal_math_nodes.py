from __future__ import annotations
from base_lib.good_chain_a import add_three
from base_lib.good_math import add, multiply
from base_lib.sandbox_arithmetic import add as resource_add
from base_lib.sandbox_arithmetic import divide as resource_divide
from base_lib.sandbox_arithmetic import multiply as resource_multiply
from base_lib.sandbox_arithmetic import subtract as resource_subtract

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class StartNode:

    def run_pure(self, inputs, params):
        return {}

class ValueInputNode:

    def run_pure(self, inputs, params):
        return {'value.in.input': VALUE(inputs, 'value.in')}

class IoInputNode:

    def run_pure(self, inputs, params):
        return {'io.result.input': VALUE(inputs, 'io.result')}

class FinalValueEndNode:

    def run_pure(self, inputs, params):
        return {}

class ReviewJoinEndNode:

    def run_pure(self, inputs, params):
        return {}

class OutValueEndNode:

    def run_pure(self, inputs, params):
        return {}

class NextValueEndNode:

    def run_pure(self, inputs, params):
        return {}

class ConstantNode:

    def run_pure(self, inputs, params):
        return {'value.in': params.get('value', 1)}

class AddNode:

    def run_pure(self, inputs, params):
        return {'value.out': add(VALUE(inputs, 'value.in'), params.get('delta', 1))}

class MultiplyNode:

    def run_pure(self, inputs, params):
        return {'value.final': multiply(VALUE(inputs, 'value.out'), params.get('factor', 2))}

class BranchLeftNode:

    def run_pure(self, inputs, params):
        return {'branch.left': params.get('value', 1)}

class BranchRightNode:

    def run_pure(self, inputs, params):
        return {'branch.right': params.get('value', 1)}

class SumPairNode:

    def run_pure(self, inputs, params):
        return {'value.in': VALUE(inputs, 'branch.left') + VALUE(inputs, 'branch.right')}

class AddThreeNode:

    def run_pure(self, inputs, params):
        return {'value.out': add_three(VALUE(inputs, 'value.in'))}

class AddOutNode:

    def run_pure(self, inputs, params):
        return {'value.final': add(VALUE(inputs, 'value.out'), params.get('delta', 1))}

class AddFinalToDeadNode:

    def run_pure(self, inputs, params):
        return {'value.dead': add(VALUE(inputs, 'value.final'), params.get('delta', 1))}


class ResourceScaleNode:

    def run_pure(self, inputs, params):
        return {'calc.scaled': VALUE(inputs, 'calc.resource') * params.get('factor', 1)}
