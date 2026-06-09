from __future__ import annotations

from base_lib.deep_chain_a import step_a
from topology_kernel import NodeContract, NodeInfo


def _info(type_key):
    return NodeInfo(type_key=type_key, display_name="Bad", category="bad", description="Bad maintainability node.", version="0.1.0")


def _contract():
    return NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )


CACHE = {}


class GlobalStateNode:
    NODE_INFO = _info("bad.global_state")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class SetAttrNode:
    NODE_INFO = _info("bad.setattr")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        setattr(self, "x", 1)
        return {"bad.out": 1}


class MonkeyPatchNode:
    NODE_INFO = _info("bad.monkey_patch")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        GlobalStateNode.extra = 1
        return {"bad.out": 1}


class LongSourceNode:
    NODE_INFO = _info("bad.long_source")
    CONTRACT = _contract()

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
        return {"bad.out": value}


class WarnCallChainNode:
    NODE_INFO = _info("bad.warn_call_chain")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        return {"bad.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._c()

    def _c(self):
        return 1


class DeepCallChainNode:
    NODE_INFO = _info("bad.deep_call_chain")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        return {"bad.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._c()

    def _c(self):
        return self._d()

    def _d(self):
        return 1


class RecursiveNode:
    NODE_INFO = _info("bad.recursive")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        return {"bad.out": self._loop()}

    def _loop(self):
        return self._loop()


class IndirectRecursiveNode:
    NODE_INFO = _info("bad.indirect_recursive")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        return {"bad.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._a()


class DeepBaseLibNode:
    NODE_INFO = _info("bad.deep_base_lib")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        return {"bad.out": step_a(1)}
