from __future__ import annotations
from tests.fixtures.support.declarations import node_declaration, configured_declaration

from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.targets.python.project import NodeContract, NodeInfo
from .strict_support_runtime_implementations import (
    V,
    StartNode,
    ValueInputNode,
    OutEndNode,
    InEndNode,
    SeedNode,
    LargePredictionNode,
    AddNode,
    CopyNode,
    RouteNode,
    NanOutputNode,
    EffectRequestNode,
    SetOutputNode,
    OpaqueOutputNode,
    MutatingInputNode,
    IdentityObjectNode,
    RuntimeFailNode,
    CountingInitNode,
    DuplicateOneNode,
    DuplicateTwoNode,
)



def REQ(data_type: str, cardinality: str = "exactly_one") -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality, display_name=data_type.replace(".", " ").title())


def PROV(key: str, data_type: str | None = None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key, display_name=key.replace(".", " ").title())


def ENV(key: str, data_type: str, value):
    return {"key": key, "type": data_type, "value": value, "source_node": "example"}




StartNode_DECLARATION = node_declaration(NodeInfo("test.start", "Start", "Starts a test flow.", "0.1.0", "terminal"), NodeContract(examples=({"inputs": {}, "params": {}},)), rulesets=("vibeflow.process",))



ValueInputNode_DECLARATION = node_declaration(NodeInfo("test.value_input", "Value Input", "Reads value.in.", "0.1.0", "io"), NodeContract(
        requires=(REQ("value.in"),),
        input_semantics={"value.in": ("input value",)},
        examples=({"inputs": {"value.in": ENV("value.in", "value.in", 1)}, "params": {}},),
    ), rulesets=("vibeflow.io",))



OutEndNode_DECLARATION = node_declaration(NodeInfo("test.out_end", "Out End", "Ends after value.out.", "0.1.0", "terminal"), NodeContract(
        requires=(REQ("value.out"),),
        input_semantics={"value.out": ("output value",)},
        examples=({"inputs": {"value.out": ENV("value.out", "value.out", 1)}, "params": {}},),
    ), rulesets=("vibeflow.process",))



InEndNode_DECLARATION = node_declaration(NodeInfo("test.in_end", "In End", "Ends after value.in.", "0.1.0", "terminal"), NodeContract(
        requires=(REQ("value.in"),),
        input_semantics={"value.in": ("input value",)},
        examples=({"inputs": {"value.in": ENV("value.in", "value.in", 1)}, "params": {}},),
    ), rulesets=("vibeflow.process",))



SeedNode_DECLARATION = node_declaration(NodeInfo("test.seed", "Seed", "Produces a seed value.", "0.1.0", "process"), NodeContract(
        provides=(PROV("value.in"),),
        output_semantics={"value.in": ("seed value",)},


        examples=({"inputs": {}, "params": {"value": 4}},),
    ), rulesets=("vibeflow.process",))



LargePredictionNode_DECLARATION = node_declaration(NodeInfo("test.large_prediction", "Large Prediction", "Produces many prediction rows.", "0.1.0", "process"), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("prediction mapping",)},

        examples=({"inputs": {}, "params": {}},),
    ), rulesets=("vibeflow.process",))



AddNode_DECLARATION = node_declaration(NodeInfo("test.add", "Add", "Adds delta to input.", "0.1.0", "process"), NodeContract(
        requires=(REQ("value.in"),),
        provides=(PROV("value.out"),),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"value.out": ("output value",)},


        examples=({"inputs": {"value.in": ENV("value.in", "value.in", 4)}, "params": {"delta": 3}},),
    ), rulesets=("vibeflow.process",))



CopyNode_DECLARATION = node_declaration(NodeInfo("test.copy", "Copy", "Copies a value.", "0.1.0", "process"), NodeContract(
        requires=(REQ("value.out"),),
        provides=(PROV("value.in"),),
        input_semantics={"value.out": ("output value",)},
        output_semantics={"value.in": ("input value",)},

        examples=({"inputs": {"value.out": ENV("value.out", "value.out", 7)}, "params": {}},),
    ), rulesets=("vibeflow.process",))



RouteNode_DECLARATION = node_declaration(NodeInfo("test.route", "Route", "Routes the next step.", "0.1.0", "decision"), NodeContract(
        requires=(REQ("value.out"),),
        provides=(PROV("flow.route"),),
        input_semantics={"value.out": ("output value",)},
        output_semantics={"flow.route": ("branch route",)},

        examples=({"inputs": {"value.out": ENV("value.out", "value.out", 1)}, "params": {}},),
    ), rulesets=("vibeflow.process",))



NanOutputNode_DECLARATION = node_declaration(NodeInfo("test.nan_output", "NaN Output", "Returns a runtime-invalid JSON value.", "0.1.0", "process"), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("output value",)},

    ), rulesets=("vibeflow.process",))



EffectRequestNode_DECLARATION = node_declaration(NodeInfo("test.effect_request", "Effect Request", "Emits a structured effect request.", "0.1.0", "data_store"), NodeContract(
        requires=(REQ("value.in"),),
        provides=(PROV("effects.request"),),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"effects.request": ("structured effect request",)},

    ), rulesets=("vibeflow.data_store",))



SetOutputNode_DECLARATION = node_declaration(NodeInfo(
        type_key="test.set_output",
        display_name="Set Output",

        description="Returns a non-json output.",
        version="0.1.0",
        flow_kind="process",
    ), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("output value",)},

    ), rulesets=("vibeflow.process",))



OpaqueOutputNode_DECLARATION = node_declaration(NodeInfo(
        type_key="test.opaque_output",
        display_name="Opaque Output",

        description="Returns an explicitly opaque output.",
        version="0.1.0",
        flow_kind="process",
    ), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("output value",)},

    ), rulesets=("vibeflow.process",))



MutatingInputNode_DECLARATION = node_declaration(NodeInfo(
        type_key="test.mutating_input",
        display_name="Mutating Input",

        description="Mutates its input.",
        version="0.1.0",
        flow_kind="process",
    ), NodeContract(
        requires=(REQ("value.in"),),
        provides=(PROV("value.out"),),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"value.out": ("output value",)},

    ), rulesets=("vibeflow.process",))



IdentityObjectNode_DECLARATION = node_declaration(NodeInfo(
        type_key="test.identity_object",
        display_name="Identity Object",

        description="Passes an object through unchanged.",
        version="0.1.0",
        flow_kind="process",
    ), NodeContract(
        requires=(REQ("value.in"),),
        provides=(PROV("value.out"),),
        input_semantics={"value.in": ("input object",)},
        output_semantics={"value.out": ("same object",)},
    ), rulesets=("vibeflow.process",))



RuntimeFailNode_DECLARATION = node_declaration(NodeInfo(
        type_key="test.runtime_fail",
        display_name="Runtime Fail",

        description="Fails during runtime.",
        version="0.1.0",
        flow_kind="process",
    ), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("runtime output",)},


        examples=({"inputs": {}, "params": {"fail": False}},),
    ), rulesets=("vibeflow.process",))



CountingInitNode_DECLARATION = node_declaration(NodeInfo("test.counting_init", "Counting Init", "Counts construction for execution plan tests.", "0.1.0", "process"), NodeContract(
        provides=(PROV("value.out"),),
        output_semantics={"value.out": ("configured output",)},


        examples=({"inputs": {}, "params": {"value": 3}},),
    ), rulesets=("vibeflow.process",))



DuplicateOneNode_DECLARATION = node_declaration(NodeInfo("test.duplicate_one", "Duplicate One", "Duplicates output.", "0.1.0", "process"), NodeContract(
        provides=(PROV("dup.one"),),
        output_semantics={"dup.one": ("duplicate value",)},

        examples=({"inputs": {}, "params": {}},),
    ), rulesets=("vibeflow.process",))



DuplicateTwoNode_DECLARATION = node_declaration(NodeInfo("test.duplicate_two", "Duplicate Two", "Duplicates output.", "0.1.0", "process"), NodeContract(
        provides=(PROV("dup.two"),),
        output_semantics={"dup.two": ("duplicate value",)},

        examples=({"inputs": {}, "params": {}},),
    ), rulesets=("vibeflow.process",))



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
