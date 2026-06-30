from __future__ import annotations

from base_lib.good_math import is_done
from topology_kernel import NodeContract, NodeInfo


class IncrementNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.increment",
        display_name="Increment",
        category="sandbox",
        description="Increments value.in by one.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.next",),
        input_semantics={"value.in": ("current value",)},
        output_semantics={"value.next": ("next value",)},
        output_schema={"value.next": {"type": "number"}},
        examples=({"inputs": {"value.in": 1}, "params": {}, "outputs": {"value.next": 2}},),
    )

    def run_pure(self, inputs, params):
        return {"value.next": inputs["value.in"] + 1}


class CopyBackNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.copy_back",
        display_name="Copy Back",
        category="sandbox",
        description="Copies value.next back to value.in for the next loop iteration.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.next", "loop.done"),
        provides=("value.in",),
        input_semantics={"value.next": ("next value",), "loop.done": ("whether the loop should stop",)},
        output_semantics={"value.in": ("loop current value",)},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {"value.next": 2, "loop.done": False}, "params": {}, "outputs": {"value.in": 2}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": inputs["value.next"]}


class DoneCheckNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.done_check",
        display_name="Done Check",
        category="sandbox",
        description="Checks whether the loop reached its target.",
        version="0.1.0",
        flow_kind="decision",
    )
    CONTRACT = NodeContract(
        requires=("value.next",),
        provides=("loop.done",),
        input_semantics={"value.next": ("next value",)},
        output_semantics={"loop.done": ("whether the loop should stop",)},
        params_schema={"target": {"type": "number"}},
        output_schema={"loop.done": {"type": "boolean"}},
        examples=({"inputs": {"value.next": 3}, "params": {"target": 3}, "outputs": {"loop.done": True}},),
    )

    def run_pure(self, inputs, params):
        return {"loop.done": is_done(inputs["value.next"], params.get("target", 3))}
