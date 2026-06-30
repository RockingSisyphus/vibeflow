from __future__ import annotations

from base_lib.math_tools import add
from topology_kernel import NodeContract, NodeInfo


class StartNode:
    NODE_INFO = NodeInfo(
        type_key="example.start",
        display_name="Start",
        category="example",
        description="Starts the example workflow.",
        version="0.1.0",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}, "outputs": {}},))

    def run_pure(self, inputs, params):
        return {}


class EndNode:
    NODE_INFO = NodeInfo(
        type_key="example.end",
        display_name="End",
        category="example",
        description="Ends after value.out is produced.",
        version="0.1.0",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        input_semantics={"value.out": ("final numeric value",)},
        examples=({"inputs": {"value.out": 2}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class SeedNode:
    NODE_INFO = NodeInfo(
        type_key="example.seed",
        display_name="Seed",
        category="example",
        description="Produces the initial value for the example workflow.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("value.in",),
        output_semantics={"value.in": ("initial numeric value",)},
        params_schema={"value": {"type": "number"}},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {}, "params": {"value": 2}, "outputs": {"value.in": 2}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": params.get("value", 1)}


class AddNode:
    NODE_INFO = NodeInfo(
        type_key="example.add",
        display_name="Add",
        category="example",
        description="Adds a configured delta using a pure base_lib helper.",
        version="0.1.0",
        flow_kind="process",
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
