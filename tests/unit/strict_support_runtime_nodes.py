from __future__ import annotations

from topology_kernel import NodeContract, NodeInfo


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


__all__ = [name for name in globals() if not name.startswith("__")]
