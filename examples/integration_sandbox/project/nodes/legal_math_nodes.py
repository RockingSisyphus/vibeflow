from __future__ import annotations

from base_lib.good_chain_a import add_three
from base_lib.good_math import add, multiply
from topology_kernel import NodeContract, NodeInfo


class ConstantNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.constant",
        display_name="Constant",
        category="sandbox",
        description="Produces a configured numeric value.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        provides=("value.in",),
        output_semantics={"value.in": ("configured numeric value",)},
        params_schema={"value": {"type": "number"}},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {}, "params": {"value": 2}, "outputs": {"value.in": 2}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": params.get("value", 1)}


class AddNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.add",
        display_name="Add",
        category="sandbox",
        description="Adds a configured delta to value.in.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.out",),
        input_semantics={"value.in": ("input numeric value",)},
        output_semantics={"value.out": ("output numeric value",)},
        params_schema={"delta": {"type": "number"}},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {"value.in": 2}, "params": {"delta": 3}, "outputs": {"value.out": 5}},),
    )

    def run_pure(self, inputs, params):
        return {"value.out": add(inputs["value.in"], params.get("delta", 1))}


class MultiplyNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.multiply",
        display_name="Multiply",
        category="sandbox",
        description="Multiplies value.out by a configured factor.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("value.final",),
        input_semantics={"value.out": ("value to multiply",)},
        output_semantics={"value.final": ("final numeric value",)},
        params_schema={"factor": {"type": "number"}},
        output_schema={"value.final": {"type": "number"}},
        examples=({"inputs": {"value.out": 5}, "params": {"factor": 2}, "outputs": {"value.final": 10}},),
    )

    def run_pure(self, inputs, params):
        return {"value.final": multiply(inputs["value.out"], params.get("factor", 2))}


class BranchLeftNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.branch_left",
        display_name="Branch Left",
        category="sandbox",
        description="Produces the left value for a free branch.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        provides=("branch.left",),
        output_semantics={"branch.left": ("left branch value",)},
        params_schema={"value": {"type": "number"}},
        output_schema={"branch.left": {"type": "number"}},
        examples=({"inputs": {}, "params": {"value": 4}, "outputs": {"branch.left": 4}},),
    )

    def run_pure(self, inputs, params):
        return {"branch.left": params.get("value", 1)}


class BranchRightNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.branch_right",
        display_name="Branch Right",
        category="sandbox",
        description="Produces the right value for a free branch.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        provides=("branch.right",),
        output_semantics={"branch.right": ("right branch value",)},
        params_schema={"value": {"type": "number"}},
        output_schema={"branch.right": {"type": "number"}},
        examples=({"inputs": {}, "params": {"value": 6}, "outputs": {"branch.right": 6}},),
    )

    def run_pure(self, inputs, params):
        return {"branch.right": params.get("value", 1)}


class SumPairNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.sum_pair",
        display_name="Sum Pair",
        category="sandbox",
        description="Sums two free branch values.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        requires=("branch.left", "branch.right"),
        provides=("value.in",),
        input_semantics={"branch.left": ("left value",), "branch.right": ("right value",)},
        output_semantics={"value.in": ("summed value",)},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {"branch.left": 4, "branch.right": 6}, "params": {}, "outputs": {"value.in": 10}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": inputs["branch.left"] + inputs["branch.right"]}


class AddThreeNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.add_three",
        display_name="Add Three",
        category="sandbox",
        description="Adds three through a short legal base_lib dependency chain.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.out",),
        input_semantics={"value.in": ("input numeric value",)},
        output_semantics={"value.out": ("output numeric value",)},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {"value.in": 2}, "params": {}, "outputs": {"value.out": 5}},),
    )

    def run_pure(self, inputs, params):
        return {"value.out": add_three(inputs["value.in"])}


class AddOutNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.add_out",
        display_name="Add Out",
        category="sandbox",
        description="Adds a configured delta to value.out and produces value.final.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("value.final",),
        input_semantics={"value.out": ("input numeric value",)},
        output_semantics={"value.final": ("final numeric value",)},
        params_schema={"delta": {"type": "number"}},
        output_schema={"value.final": {"type": "number"}},
        examples=({"inputs": {"value.out": 2}, "params": {"delta": 1}, "outputs": {"value.final": 3}},),
    )

    def run_pure(self, inputs, params):
        return {"value.final": add(inputs["value.out"], params.get("delta", 1))}
