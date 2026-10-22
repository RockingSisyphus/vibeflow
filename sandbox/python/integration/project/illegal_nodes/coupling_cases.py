from __future__ import annotations
from nodes.legal_math_nodes import ConstantNode

class DirectNodeCallNode:

    def run_pure(self, inputs, params):
        ConstantNode().run_pure({}, {'value': 1})
        return {'bad.out': 1}

class NodeInternalReadNode:

    def run_pure(self, inputs, params):
        return {'bad.out': len(ConstantNode._private)}
