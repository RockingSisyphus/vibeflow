from __future__ import annotations

from vibeflow.core import DataProvider, DataRequirement
from vibeflow.targets.python.project import NodeContract, NodeInfo


def _require(data_type: str, display_name: str) -> DataRequirement:
    return DataRequirement(type=data_type, cardinality="exactly_one", display_name=display_name)


def _provide(key: str, data_type: str, display_name: str) -> DataProvider:
    return DataProvider(key=key, type=data_type, display_name=display_name)


def _value(inputs, data_type: str):
    return inputs[data_type]["value"]


class StartNode:
    NODE_INFO = NodeInfo(
        type_key="minimal.start",
        display_name="Workflow start",
        category="boundary",
        description="Marks the structural start of the minimal workflow.",
        version="0.13.2",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        return {}


class InputBoundaryNode:
    NODE_INFO = NodeInfo(
        type_key="minimal.input_boundary",
        display_name="Input boundary",
        category="boundary",
        description="Adapts the public request into the workflow's internal payload.",
        version="0.13.2",
        flow_kind="io",
    )
    CONTRACT = NodeContract(
        requires=(_require("payload.request", "Public request"),),
        provides=(_provide("internal_payload", "payload.internal", "Internal payload"),),
        input_semantics={"payload.request": ("Generic payload supplied by the caller.",)},
        output_semantics={"internal_payload": ("Internal payload passed to business processing.",)},
    )

    def run_pure(self, inputs, params):
        return {"internal_payload": _value(inputs, "payload.request")}


class ProcessPayloadNode:
    NODE_INFO = NodeInfo(
        type_key="minimal.process_payload",
        display_name="Process payload",
        category="business",
        description="Contains the project-specific business transformation.",
        version="0.13.2",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=(_require("payload.internal", "Internal payload"),),
        provides=(_provide("processed_payload", "payload.processed", "Processed payload"),),
        input_semantics={"payload.internal": ("Payload ready for project-specific processing.",)},
        output_semantics={"processed_payload": ("Result of project-specific processing.",)},
    )

    def run_pure(self, inputs, params):
        # BUSINESS CODE: replace this pass-through with the real transformation.
        return {"processed_payload": _value(inputs, "payload.internal")}


class OutputBoundaryNode:
    NODE_INFO = NodeInfo(
        type_key="minimal.output_boundary",
        display_name="Output boundary",
        category="boundary",
        description="Adapts the processed payload to the public response.",
        version="0.13.2",
        flow_kind="io",
    )
    CONTRACT = NodeContract(
        requires=(_require("payload.processed", "Processed payload"),),
        provides=(_provide("response", "payload.response", "Public response"),),
        input_semantics={"payload.processed": ("Processed payload ready to leave the workflow.",)},
        output_semantics={"response": ("Generic response returned to the caller.",)},
    )

    def run_pure(self, inputs, params):
        return {"response": _value(inputs, "payload.processed")}


class EndNode:
    NODE_INFO = NodeInfo(
        type_key="minimal.end",
        display_name="Workflow end",
        category="boundary",
        description="Marks the structural end after the response is available.",
        version="0.13.2",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        return {}
