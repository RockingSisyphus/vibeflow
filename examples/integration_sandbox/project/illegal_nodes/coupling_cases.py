from __future__ import annotations

from nodes.legal_math_nodes import ConstantNode
from topology_kernel import NodeContract, NodeInfo


class NodeImportNode:
    NODE_INFO = NodeInfo(
        type_key="bad.node_import",
        display_name="Bad",
        category="bad",
        description="Bad node importing another node.",
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


class DirectNodeCallNode:
    NODE_INFO = NodeInfo(
        type_key="bad.node_call",
        display_name="Bad",
        category="bad",
        description="Bad node directly calling another node.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        ConstantNode().run_pure({}, {"value": 1})
        return {"bad.out": 1}


class NodeInternalReadNode:
    NODE_INFO = NodeInfo(
        type_key="bad.node_internal",
        display_name="Bad",
        category="bad",
        description="Bad node reading another node internals.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("bad.out",),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"bad.out": len(ConstantNode.CONTRACT.provides)}
