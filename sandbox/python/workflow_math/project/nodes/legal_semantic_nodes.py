from base_lib.math_lib import add

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class SemanticAddPairNode:

    def run_pure(self, inputs, params):
        return {'calc.sum': add(VALUE(inputs, 'calc.a'), VALUE(inputs, 'calc.b'))}

class SemanticScaleNode:

    def run_pure(self, inputs, params):
        return {'calc.scaled': VALUE(inputs, 'calc.sum') * params.get('factor', 1)}

class SemanticUseScaledNode:

    def run_pure(self, inputs, params):
        return {'calc.branch': VALUE(inputs, 'calc.scaled')}

class SemanticFinalizeNode:

    def run_pure(self, inputs, params):
        return {'calc.final': VALUE(inputs, 'calc.branch') + params.get('offset', 0)}

class SemanticIncrementUntilNode:

    def run_pure(self, inputs, params):
        return {'loop.next': add(VALUE(inputs, 'loop.current'), params.get('step', 1))}

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
        return {'outer.inner.next': outer, 'inner.current.next': next_inner, 'total.inner.next': add(total, 1), 'inner.done': next_inner >= params.get('inner_limit', 1)}

class SemanticOuterAdvanceNode:

    def run_pure(self, inputs, params):
        outer = VALUE(inputs, 'outer.inner')
        next_outer = add(outer, params.get('outer_step', 1))
        return {'outer.current.next': next_outer, 'total.current.next': VALUE(inputs, 'total.inner'), 'outer.done': next_outer >= params.get('outer_limit', 1)}

class SemanticScaledEndNode:

    def run_pure(self, inputs, params):
        return {}

class SemanticFinalEndNode:

    def run_pure(self, inputs, params):
        return {}

class SemanticLoopEndNode:

    def run_pure(self, inputs, params):
        return {}

