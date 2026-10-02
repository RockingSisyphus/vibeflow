from __future__ import annotations
from base_lib.deep_chain_a import step_a
CACHE = {}

class GlobalStateNode:

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class SetAttrNode:

    def run_pure(self, inputs, params):
        setattr(self, 'x', 1)
        return {'bad.out': 1}

class MonkeyPatchNode:

    def run_pure(self, inputs, params):
        GlobalStateNode.extra = 1
        return {'bad.out': 1}

class LongSourceNode:

    def run_pure(self, inputs, params):
        value = 1
        value = value + 1
        value = value + 1
        value = value + 1
        value = value + 1
        value = value + 1
        value = value + 1
        value = value + 1
        value = value + 1
        value = value + 1
        value = value + 1
        return {'bad.out': value}

class WarnCallChainNode:

    def run_pure(self, inputs, params):
        return {'bad.out': self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._c()

    def _c(self):
        return 1

class DeepCallChainNode:

    def run_pure(self, inputs, params):
        return {'bad.out': self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._c()

    def _c(self):
        return self._d()

    def _d(self):
        return 1

class RecursiveNode:

    def run_pure(self, inputs, params):
        return {'bad.out': self._loop()}

    def _loop(self):
        return self._loop()

class IndirectRecursiveNode:

    def run_pure(self, inputs, params):
        return {'bad.out': self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._a()

class DeepBaseLibNode:

    def run_pure(self, inputs, params):
        return {'bad.out': step_a(1)}
