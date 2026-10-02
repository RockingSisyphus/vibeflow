from __future__ import annotations
from tests.fixtures.support.declarations import node_declaration, configured_declaration

from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.targets.python.project import NodeContract, NodeInfo


def REQ(data_type: str, cardinality: str = "exactly_one") -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality, display_name=data_type.replace(".", " ").title())


def PROV(key: str, data_type: str | None = None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key, display_name=key.replace(".", " ").title())


def ENV(key: str, data_type: str, value):
    return {"key": key, "type": data_type, "value": value, "source_node": "example"}


def V(inputs, data_type: str):
    return inputs[data_type]["value"]


StartNode_DECLARATION = node_declaration(NodeInfo("test.start", "Start", "test", "Starts a test flow.", "0.1.0", "terminal"), NodeContract(examples=({"inputs": {}, "params": {}},)), rulesets=("vibeflow.process",))

class StartNode:

    def run_pure(self, inputs, params):
        return {}


ValueInputNode_DECLARATION = node_declaration(NodeInfo("test.value_input", "Value Input", "test", "Reads value.in.", "0.1.0", "io"), NodeContract(
        requires=(REQ("value.in"),),
        input_semantics={"value.in": ("input value",)},
        examples=({"inputs": {"value.in": ENV("value.in", "value.in", 1)}, "params": {}},),
    ), rulesets=("vibeflow.io",))

class ValueInputNode:

    def run_pure(self, inputs, params):
        return {}


OutEndNode_DECLARATION = node_declaration(NodeInfo("test.out_end", "Out End", "test", "Ends after value.out.", "0.1.0", "terminal"), NodeContract(
        requires=(REQ("value.out"),),
        input_semantics={"value.out": ("output value",)},
        examples=({"inputs": {"value.out": ENV("value.out", "value.out", 1)}, "params": {}},),
    ), rulesets=("vibeflow.process",))

class OutEndNode:

    def run_pure(self, inputs, params):
        return {}


InEndNode_DECLARATION = node_declaration(NodeInfo("test.in_end", "In End", "test", "Ends after value.in.", "0.1.0", "terminal"), NodeContract(
        requires=(REQ("value.in"),),
        input_semantics={"value.in": ("input value",)},
        examples=({"inputs": {"value.in": ENV("value.in", "value.in", 1)}, "params": {}},),
    ), rulesets=("vibeflow.process",))

class InEndNode:

    def run_pure(self, inputs, params):
        return {}


SeedNode_DECLARATION = node_declaration(NodeInfo("test.seed", "Seed", "test", "Produces a seed value.", "0.1.0", "process"), NodeContract(
        provides=(PROV("value.in"),),
        output_semantics={"value.in": ("seed value",)},


        examples=({"inputs": {}, "params": {"value": 4}},),
    ), rulesets=("vibeflow.process",))

class SeedNode:

    def run_pure(self, inputs, params):
        return {"value.in": params.get("value", 1)}


LargePredictionNode_DECLARATION = node_declaration(NodeInfo("test.large_prediction", "Large Prediction", "test", "Produces many prediction rows.", "0.1.0", "process"), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("prediction mapping",)},

        examples=({"inputs": {}, "params": {}},),
    ), rulesets=("vibeflow.process",))

class LargePredictionNode:

    def run_pure(self, inputs, params):
        return {"value.out": {f"sample_{index:04d}": index for index in range(1000)}}


AddNode_DECLARATION = node_declaration(NodeInfo("test.add", "Add", "test", "Adds delta to input.", "0.1.0", "process"), NodeContract(
        requires=(REQ("value.in"),),
        provides=(PROV("value.out"),),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"value.out": ("output value",)},


        examples=({"inputs": {"value.in": ENV("value.in", "value.in", 4)}, "params": {"delta": 3}},),
    ), rulesets=("vibeflow.process",))

class AddNode:

    def run_pure(self, inputs, params):
        return {"value.out": V(inputs, "value.in") + params.get("delta", 1)}


CopyNode_DECLARATION = node_declaration(NodeInfo("test.copy", "Copy", "test", "Copies a value.", "0.1.0", "process"), NodeContract(
        requires=(REQ("value.out"),),
        provides=(PROV("value.in"),),
        input_semantics={"value.out": ("output value",)},
        output_semantics={"value.in": ("input value",)},

        examples=({"inputs": {"value.out": ENV("value.out", "value.out", 7)}, "params": {}},),
    ), rulesets=("vibeflow.process",))

class CopyNode:

    def run_pure(self, inputs, params):
        return {"value.in": V(inputs, "value.out")}


RouteNode_DECLARATION = node_declaration(NodeInfo("test.route", "Route", "test", "Routes the next step.", "0.1.0", "decision"), NodeContract(
        requires=(REQ("value.out"),),
        provides=(PROV("flow.route"),),
        input_semantics={"value.out": ("output value",)},
        output_semantics={"flow.route": ("branch route",)},

        examples=({"inputs": {"value.out": ENV("value.out", "value.out", 1)}, "params": {}},),
    ), rulesets=("vibeflow.process",))

class RouteNode:

    def run_pure(self, inputs, params):
        return {"flow.route": "done"}


NanOutputNode_DECLARATION = node_declaration(NodeInfo("test.nan_output", "NaN Output", "test", "Returns a runtime-invalid JSON value.", "0.1.0", "process"), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("output value",)},

    ), rulesets=("vibeflow.process",))

class NanOutputNode:

    def run_pure(self, inputs, params):
        return {"value.out": float("nan")}


EffectRequestNode_DECLARATION = node_declaration(NodeInfo("test.effect_request", "Effect Request", "test", "Emits a structured effect request.", "0.1.0", "data_store"), NodeContract(
        requires=(REQ("value.in"),),
        provides=(PROV("effects.request"),),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"effects.request": ("structured effect request",)},

    ), rulesets=("vibeflow.data_store",))

class EffectRequestNode:

    def run_pure(self, inputs, params):
        return {"effects.request": {"value": V(inputs, "value.in")}}


SetOutputNode_DECLARATION = node_declaration(NodeInfo(
        type_key="test.set_output",
        display_name="Set Output",
        category="test",
        description="Returns a non-json output.",
        version="0.1.0",
        flow_kind="process",
    ), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("output value",)},

    ), rulesets=("vibeflow.process",))

class SetOutputNode:

    def run_pure(self, inputs, params):
        return {"value.out": {1, 2}}


OpaqueOutputNode_DECLARATION = node_declaration(NodeInfo(
        type_key="test.opaque_output",
        display_name="Opaque Output",
        category="test",
        description="Returns an explicitly opaque output.",
        version="0.1.0",
        flow_kind="process",
    ), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("output value",)},

    ), rulesets=("vibeflow.process",))

class OpaqueOutputNode:

    def run_pure(self, inputs, params):
        return {"value.out": {1, 2}}


MutatingInputNode_DECLARATION = node_declaration(NodeInfo(
        type_key="test.mutating_input",
        display_name="Mutating Input",
        category="test",
        description="Mutates its input.",
        version="0.1.0",
        flow_kind="process",
    ), NodeContract(
        requires=(REQ("value.in"),),
        provides=(PROV("value.out"),),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"value.out": ("output value",)},

    ), rulesets=("vibeflow.process",))

class MutatingInputNode:

    def run_pure(self, inputs, params):
        V(inputs, "value.in").append(3)
        return {"value.out": V(inputs, "value.in")}


IdentityObjectNode_DECLARATION = node_declaration(NodeInfo(
        type_key="test.identity_object",
        display_name="Identity Object",
        category="test",
        description="Passes an object through unchanged.",
        version="0.1.0",
        flow_kind="process",
    ), NodeContract(
        requires=(REQ("value.in"),),
        provides=(PROV("value.out"),),
        input_semantics={"value.in": ("input object",)},
        output_semantics={"value.out": ("same object",)},
    ), rulesets=("vibeflow.process",))

class IdentityObjectNode:

    def run_pure(self, inputs, params):
        return {"value.out": V(inputs, "value.in")}


RuntimeFailNode_DECLARATION = node_declaration(NodeInfo(
        type_key="test.runtime_fail",
        display_name="Runtime Fail",
        category="test",
        description="Fails during runtime.",
        version="0.1.0",
        flow_kind="process",
    ), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("runtime output",)},


        examples=({"inputs": {}, "params": {"fail": False}},),
    ), rulesets=("vibeflow.process",))

class RuntimeFailNode:

    def run_pure(self, inputs, params):
        if params.get("fail", False):
            raise RuntimeError("boom")
        return {"value.out": 1}


CountingInitNode_DECLARATION = node_declaration(NodeInfo("test.counting_init", "Counting Init", "test", "Counts construction for execution plan tests.", "0.1.0", "process"), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("configured output",)},


        examples=({"inputs": {}, "params": {"value": 3}},),
    ), rulesets=("vibeflow.process",))

class CountingInitNode:
    instances = 0


    def __init__(self) -> None:
        type(self).instances += 1

    def run_pure(self, inputs, params):
        return {"value.out": params.get("value", 3)}


DuplicateOneNode_DECLARATION = node_declaration(NodeInfo("test.duplicate_one", "Duplicate One", "test", "Duplicates output.", "0.1.0", "process"), NodeContract(
        provides=(PROV("dup.one"),),
        output_semantics={"dup.one": ("duplicate value",)},

        examples=({"inputs": {}, "params": {}},),
    ), rulesets=("vibeflow.process",))

class DuplicateOneNode:

    def run_pure(self, inputs, params):
        return {"dup.one": 1}


DuplicateTwoNode_DECLARATION = node_declaration(NodeInfo("test.duplicate_two", "Duplicate Two", "test", "Duplicates output.", "0.1.0", "process"), NodeContract(
        provides=(PROV("dup.two"),),
        output_semantics={"dup.two": ("duplicate value",)},

        examples=({"inputs": {}, "params": {}},),
    ), rulesets=("vibeflow.process",))

class DuplicateTwoNode:

    def run_pure(self, inputs, params):
        return {"dup.two": 1}


__all__ = (
    "AddNode",
    "CopyNode",
    "CountingInitNode",
    "DuplicateOneNode",
    "DuplicateTwoNode",
    "EffectRequestNode",
    "InEndNode",
    "IdentityObjectNode",
    "LargePredictionNode",
    "MutatingInputNode",
    "NanOutputNode",
    "OpaqueOutputNode",
    "OutEndNode",
    "RouteNode",
    "RuntimeFailNode",
    "SeedNode",
    "SetOutputNode",
    "StartNode",
    "ValueInputNode",
)

__all__ = (*__all__, *(name for name in globals() if name.endswith("_DECLARATION")))
