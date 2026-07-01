from __future__ import annotations

from topology_kernel import NodeContract, NodeInfo


class StartNode:
    NODE_INFO = NodeInfo("test.start", "Start", "test", "Starts a test flow.", "0.1.0", "terminal")
    CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}, "outputs": {}},))

    def run_pure(self, inputs, params):
        return {}


class ValueInputNode:
    NODE_INFO = NodeInfo("test.value_input", "Value Input", "test", "Reads value.in.", "0.1.0", "io")
    CONTRACT = NodeContract(
        requires=("value.in",),
        input_semantics={"value.in": ("input value",)},
        examples=({"inputs": {"value.in": 1}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class OutEndNode:
    NODE_INFO = NodeInfo("test.out_end", "Out End", "test", "Ends after value.out.", "0.1.0", "terminal")
    CONTRACT = NodeContract(
        requires=("value.out",),
        input_semantics={"value.out": ("output value",)},
        examples=({"inputs": {"value.out": 1}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class InEndNode:
    NODE_INFO = NodeInfo("test.in_end", "In End", "test", "Ends after value.in.", "0.1.0", "terminal")
    CONTRACT = NodeContract(
        requires=("value.in",),
        input_semantics={"value.in": ("input value",)},
        examples=({"inputs": {"value.in": 1}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class SeedNode:
    NODE_INFO = NodeInfo("test.seed", "Seed", "test", "Produces a seed value.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=("value.in",),
        output_semantics={"value.in": ("seed value",)},
        params_schema={"value": {"type": "number"}},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {}, "params": {"value": 4}, "outputs": {"value.in": 4}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": params.get("value", 1)}


class AddNode:
    NODE_INFO = NodeInfo("test.add", "Add", "test", "Adds delta to input.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.out",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"value.out": ("output value",)},
        params_schema={"delta": {"type": "number"}},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {"value.in": 4}, "params": {"delta": 3}, "outputs": {"value.out": 7}},),
    )

    def run_pure(self, inputs, params):
        return {"value.out": inputs["value.in"] + params.get("delta", 1)}


class CopyNode:
    NODE_INFO = NodeInfo("test.copy", "Copy", "test", "Copies a value.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("value.in",),
        input_semantics={"value.out": ("output value",)},
        output_semantics={"value.in": ("input value",)},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {"value.out": 7}, "params": {}, "outputs": {"value.in": 7}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": inputs["value.out"]}


class RouteNode:
    NODE_INFO = NodeInfo("test.route", "Route", "test", "Routes the next step.", "0.1.0", "decision")
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("flow.route",),
        input_semantics={"value.out": ("output value",)},
        output_semantics={"flow.route": ("branch route",)},
        output_schema={"flow.route": {"type": "string", "enum": ["again", "done"]}},
        examples=({"inputs": {"value.out": 1}, "params": {}, "outputs": {"flow.route": "done"}},),
    )

    def run_pure(self, inputs, params):
        return {"flow.route": "done"}


class NanOutputNode:
    NODE_INFO = NodeInfo("test.nan_output", "NaN Output", "test", "Returns a runtime-invalid JSON value.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"value.out": float("nan")}


class EffectRequestNode:
    NODE_INFO = NodeInfo("test.effect_request", "Effect Request", "test", "Emits a structured effect request.", "0.1.0", "data_store")
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("effects.request",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"effects.request": ("structured effect request",)},
        output_schema={"effects.request": {"type": "object"}},
    )

    def run_pure(self, inputs, params):
        return {"effects.request": {"value": inputs["value.in"]}}


class SetOutputNode:
    NODE_INFO = NodeInfo(
        type_key="test.set_output",
        display_name="Set Output",
        category="test",
        description="Returns a non-json output.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "array"}},
    )

    def run_pure(self, inputs, params):
        return {"value.out": {1, 2}}


class OpaqueOutputNode:
    NODE_INFO = NodeInfo(
        type_key="test.opaque_output",
        display_name="Opaque Output",
        category="test",
        description="Returns an explicitly opaque output.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"snapshot": "opaque"}},
    )

    def run_pure(self, inputs, params):
        return {"value.out": {1, 2}}


class MutatingInputNode:
    NODE_INFO = NodeInfo(
        type_key="test.mutating_input",
        display_name="Mutating Input",
        category="test",
        description="Mutates its input.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.out",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "array"}},
    )

    def run_pure(self, inputs, params):
        inputs["value.in"].append(3)
        return {"value.out": inputs["value.in"]}


class DuplicateOneNode:
    NODE_INFO = NodeInfo("test.duplicate_one", "Duplicate One", "test", "Duplicates output.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=("dup.one",),
        output_semantics={"dup.one": ("duplicate value",)},
        output_schema={"dup.one": {"type": "number"}},
        examples=({"inputs": {}, "params": {}, "outputs": {"dup.one": 1}},),
    )

    def run_pure(self, inputs, params):
        return {"dup.one": 1}


class DuplicateTwoNode:
    NODE_INFO = NodeInfo("test.duplicate_two", "Duplicate Two", "test", "Duplicates output.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=("dup.two",),
        output_semantics={"dup.two": ("duplicate value",)},
        output_schema={"dup.two": {"type": "number"}},
        examples=({"inputs": {}, "params": {}, "outputs": {"dup.two": 1}},),
    )

    def run_pure(self, inputs, params):
        return {"dup.two": 1}


__all__ = (
    "AddNode",
    "CopyNode",
    "DuplicateOneNode",
    "DuplicateTwoNode",
    "EffectRequestNode",
    "InEndNode",
    "MutatingInputNode",
    "NanOutputNode",
    "OpaqueOutputNode",
    "OutEndNode",
    "RouteNode",
    "SeedNode",
    "SetOutputNode",
    "StartNode",
    "ValueInputNode",
)
