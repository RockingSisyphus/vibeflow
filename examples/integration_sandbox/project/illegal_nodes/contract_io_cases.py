from __future__ import annotations

from math import nan

from vibeflow import NodeContract, NodeInfo


def _info(type_key):
    return NodeInfo(type_key=type_key, display_name="Bad", category="bad", description="Bad contract I/O node.", version="0.1.0", flow_kind="process")


class DynamicOutputKeyNode:
    NODE_INFO = _info("bad.dynamic_output")
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        key = "bad.out"
        return {key: 1}


class MissingOutputNode:
    NODE_INFO = _info("bad.missing_output")
    CONTRACT = NodeContract(
        provides=("bad.out", "bad.extra"),
        output_semantics={"bad.out": ("bad output",), "bad.extra": ("extra output",)},
        output_schema={"bad.out": {"type": "number"}, "bad.extra": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class ExtraOutputNode:
    NODE_INFO = _info("bad.extra_output")
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": 1, "bad.extra": 2}


class MutateInputsNode:
    NODE_INFO = _info("bad.mutate_inputs")
    CONTRACT = NodeContract(
        requires=("bad.in",),
        provides=("bad.out",),
        input_semantics={"bad.in": ("bad input",)},
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        inputs["bad.in"] = 2
        return {"bad.out": 1}


class MutateNestedInputNode:
    NODE_INFO = _info("bad.mutate_nested")
    CONTRACT = NodeContract(
        requires=("bad.items",),
        provides=("bad.out",),
        input_semantics={"bad.items": ("bad input list",)},
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        items = inputs["bad.items"]
        items.append(1)
        return {"bad.out": 1}


class UndeclaredParamNode:
    NODE_INFO = _info("bad.undeclared_param")
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": params.get("x", 1)}


class SetOutputNode:
    NODE_INFO = _info("bad.set_output")
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "array"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": {1, 2}}


class NaNOutputNode:
    NODE_INFO = _info("bad.nan_output")
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": nan}
