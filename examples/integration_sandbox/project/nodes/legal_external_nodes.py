from __future__ import annotations

from vibeflow import NodeContract, NodeInfo


class EffectRequestNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.effect_request",
        display_name="Effect Request",
        category="sandbox",
        description="Expresses an external effect request as data.",
        version="0.1.0",
        flow_kind="data_store",
    )
    CONTRACT = NodeContract(
        provides=("effects.request",),
        output_semantics={"effects.request": ("structured request for an external effect",)},
        params_schema={"value": {"type": "number"}},
        output_schema={"effects.request": {"type": "object"}},
        examples=({"inputs": {}, "params": {"value": 5}, "outputs": {"effects.request": {"value": 5}}},),
    )

    def run_pure(self, inputs, params):
        return {"effects.request": {"value": params.get("value", 1)}}


class IoResultAddNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.io_result_add",
        display_name="IO Result Add",
        category="sandbox",
        description="Adds a configured delta to an external IO result.",
        version="0.1.0",
        flow_kind="io",
    )
    CONTRACT = NodeContract(
        requires=("io.result",),
        provides=("value.final",),
        input_semantics={"io.result": ("external numeric result",)},
        output_semantics={"value.final": ("final numeric value",)},
        params_schema={"delta": {"type": "number"}},
        output_schema={"value.final": {"type": "number"}},
        examples=({"inputs": {"io.result": 7}, "params": {"delta": 1}, "outputs": {"value.final": 8}},),
    )

    def run_pure(self, inputs, params):
        return {"value.final": inputs["io.result"] + params.get("delta", 1)}


class IoResultInputNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.io_result_input",
        display_name="IO Result Input",
        category="sandbox",
        description="Converts an external IO result into value.in for a downstream nodeset.",
        version="0.1.0",
        flow_kind="io",
    )
    CONTRACT = NodeContract(
        requires=("io.result",),
        provides=("value.in",),
        input_semantics={"io.result": ("external numeric result",)},
        output_semantics={"value.in": ("numeric input for downstream flow",)},
        params_schema={"delta": {"type": "number"}},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {"io.result": 7}, "params": {"delta": 1}, "outputs": {"value.in": 8}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": inputs["io.result"] + params.get("delta", 1)}
