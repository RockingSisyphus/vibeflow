from __future__ import annotations

from topology_kernel import NodeContract, NodeInfo


def _info(type_key):
    return NodeInfo(type_key=type_key, display_name="Bad", category="bad", description="Bad signature node.", version="0.1.0")


def _contract():
    return NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )


class MissingRunPureNode:
    NODE_INFO = _info("bad.missing_run_pure")
    CONTRACT = _contract()


class ContextRunNode:
    NODE_INFO = _info("bad.context_run")
    CONTRACT = _contract()

    def run(self, context):
        return context

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class TooManyParamsNode:
    NODE_INFO = _info("bad.too_many_params")
    CONTRACT = _contract()

    def run_pure(self, inputs, params, extra):
        return {"bad.out": 1}


class VarArgsNode:
    NODE_INFO = _info("bad.varargs")
    CONTRACT = _contract()

    def run_pure(self, inputs, params, *args):
        return {"bad.out": 1}


class PublicHelperNode:
    NODE_INFO = _info("bad.public_helper")
    CONTRACT = _contract()

    def helper(self):
        return 1

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class InitWithClientNode:
    NODE_INFO = _info("bad.init_client")
    CONTRACT = _contract()

    def __init__(self, client):
        self.client = client

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class ResourceFieldNode:
    NODE_INFO = _info("bad.resource_field")
    CONTRACT = _contract()

    def __init__(self):
        self.session = None

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class AsyncRunPureNode:
    NODE_INFO = _info("bad.async_run_pure")
    CONTRACT = _contract()

    async def run_pure(self, inputs, params):
        return {"bad.out": 1}


class GeneratorRunPureNode:
    NODE_INFO = _info("bad.generator_run_pure")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        yield {"bad.out": 1}
