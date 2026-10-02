from __future__ import annotations

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class SemanticAddPairNode:

    def run_pure(self, inputs, params):
        return {'calc.sum': VALUE(inputs, 'calc.a') + VALUE(inputs, 'calc.b')}

class SemanticScaleNode:

    def run_pure(self, inputs, params):
        return {'calc.scaled': VALUE(inputs, 'calc.sum') * params.get('factor', 1)}

class SemanticUseScaledNode:

    def run_pure(self, inputs, params):
        return {'calc.branch': VALUE(inputs, 'calc.scaled')}

class SemanticCompareGtNode:

    def run_pure(self, inputs, params):
        return {'route.branch': 'left' if VALUE(inputs, 'calc.c') > VALUE(inputs, 'calc.d') else 'right'}

class SemanticLeftAdjustNode:

    def run_pure(self, inputs, params):
        return {'calc.left_branch': VALUE(inputs, 'calc.scaled') + params.get('bonus', 0)}

class SemanticRightAdjustNode:

    def run_pure(self, inputs, params):
        return {'calc.right_branch': VALUE(inputs, 'calc.scaled') - params.get('penalty', 0)}

class SemanticLeftKeyAdjustNode:

    def run_pure(self, inputs, params):
        return {'calc.left_branch': VALUE(inputs, 'calc.scaled') + params.get('bonus', 0)}

class SemanticRightKeyAdjustNode:

    def run_pure(self, inputs, params):
        return {'calc.right_branch': VALUE(inputs, 'calc.scaled') - params.get('penalty', 0)}

class SemanticBranchTypeConsumerNode:

    def run_pure(self, inputs, params):
        envelope = inputs['branch_result']
        value = envelope['value']
        source_key = envelope['key']
        source_bonus = 100 if source_key == 'calc.left_branch' else 200
        return {'branch.final': value + source_bonus}

class SemanticBranchFinalEndNode:

    def run_pure(self, inputs, params):
        return {}

class SemanticJoinPassthroughNode:

    def run_pure(self, inputs, params):
        return {'value.out': VALUE(inputs, 'value.in')}

class SemanticValueEndNode:

    def run_pure(self, inputs, params):
        return {}

class SemanticInactiveRouteNode:

    def run_pure(self, inputs, params):
        return {'flow.route': False}

class SemanticConditionalValueNode:

    def run_pure(self, inputs, params):
        return {'value.alt': params.get('value', 7), 'flow.use_alt': True}

class SemanticLeftValueNode:

    def run_pure(self, inputs, params):
        return {'value.left': params.get('value', 1)}

class SemanticRightValueNode:

    def run_pure(self, inputs, params):
        return {'value.right': params.get('value', 2)}

class SemanticOtherValueNode:

    def run_pure(self, inputs, params):
        return {'other.in': params.get('value', 5)}

class SemanticTwoInputJoinNode:

    def run_pure(self, inputs, params):
        return {'value.out': VALUE(inputs, 'value.in') + VALUE(inputs, 'other.in')}

class SemanticFinalizeNode:

    def run_pure(self, inputs, params):
        return {'calc.final': VALUE(inputs, 'calc.branch') + params.get('offset', 0)}

class SemanticIncrementUntilNode:

    def run_pure(self, inputs, params):
        return {'loop.next': VALUE(inputs, 'loop.current') + params.get('step', 1)}

class SemanticLoopDoneNode:

    def run_pure(self, inputs, params):
        return {'loop.done': VALUE(inputs, 'loop.next') >= params.get('target', 0)}

class SemanticLoopDoneValueNode:

    def run_pure(self, inputs, params):
        return {'loop.done': VALUE(inputs, 'loop.next') >= params.get('target', 0)}

class SemanticNestedLoopSeedNode:

    def run_pure(self, inputs, params):
        return {'outer.current': params.get('outer_start', 0), 'total.current': params.get('total_start', 0)}

class SemanticInnerLoopInitNode:

    def run_pure(self, inputs, params):
        return {'outer.inner.seed': VALUE(inputs, 'outer.current'), 'total.inner.seed': VALUE(inputs, 'total.current'), 'inner.current.seed': params.get('inner_start', 0)}

class SemanticInnerAccumulateNode:

    def run_pure(self, inputs, params):
        outer = VALUE(inputs, 'outer.inner')
        inner = VALUE(inputs, 'inner.current')
        total = VALUE(inputs, 'total.inner')
        step = params.get('inner_step', 1)
        next_inner = inner + step
        return {'outer.inner.next': outer, 'inner.current.next': next_inner, 'total.inner.next': total + outer + inner + 1, 'inner.done': next_inner >= params.get('inner_limit', 1)}

class SemanticOuterAdvanceNode:

    def run_pure(self, inputs, params):
        outer = VALUE(inputs, 'outer.inner')
        next_outer = outer + params.get('outer_step', 1)
        return {'outer.current.next': next_outer, 'total.current.next': VALUE(inputs, 'total.inner'), 'outer.done': next_outer >= params.get('outer_limit', 1)}

class SemanticCopyNextNode:

    def run_pure(self, inputs, params):
        return {'loop.current.copy': VALUE(inputs, 'loop.next')}

class SemanticScaledEndNode:

    def run_pure(self, inputs, params):
        return {}

class SemanticFinalEndNode:

    def run_pure(self, inputs, params):
        return {}

class SemanticLeftBranchEndNode:

    def run_pure(self, inputs, params):
        return {}

class SemanticRightBranchEndNode:

    def run_pure(self, inputs, params):
        return {}

class SemanticLoopEndNode:

    def run_pure(self, inputs, params):
        return {}

class SemanticSlowAsyncValueNode:

    def run_pure(self, inputs, params):
        return {'async.value': params.get('value', 42)}

class SemanticAsyncValueEndNode:

    def run_pure(self, inputs, params):
        return {}
