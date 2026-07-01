from __future__ import annotations

from vibeflow import NodeContract, NodeInfo


class MissingInfoNode:
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class InfoWrongTypeNode:
    NODE_INFO = {"type_key": "bad.info_type"}
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class EmptyTypeKeyNode:
    NODE_INFO = NodeInfo(
        type_key="",
        display_name="Bad",
        category="bad",
        description="Bad node with empty type key.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class NonPureNode:
    NODE_INFO = NodeInfo(
        type_key="bad.non_pure",
        display_name="Bad",
        category="bad",
        description="Bad node with non-pure metadata.",
        version="0.1.0",
        flow_kind="process",
        purity="impure",
    )
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class MissingContractNode:
    NODE_INFO = NodeInfo(
        type_key="bad.missing_contract",
        display_name="Bad",
        category="bad",
        description="Bad node without contract.",
        version="0.1.0",
        flow_kind="process",
    )

    def run_pure(self, inputs, params):
        return {"bad.out": 1}


class DuplicateKeysNode:
    NODE_INFO = NodeInfo(
        type_key="bad.duplicate_keys",
        display_name="Bad",
        category="bad",
        description="Bad node with duplicate contract keys.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("bad.in", "bad.in"),
        provides=("bad.out",),
        input_semantics={"bad.in": ("bad input",)},
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": inputs["bad.in"]}


class MissingSemanticsNode:
    NODE_INFO = NodeInfo(
        type_key="bad.missing_semantics",
        display_name="Bad",
        category="bad",
        description="Bad node with missing semantics.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("bad.in",),
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": inputs["bad.in"]}
