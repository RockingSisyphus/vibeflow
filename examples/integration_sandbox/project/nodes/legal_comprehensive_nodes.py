from __future__ import annotations

from topology_kernel import NodeContract, NodeInfo


class PrepareValueNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.prepare_value",
        display_name="Prepare Value",
        category="sandbox",
        description="Initializes a prepared value for the comprehensive flow.",
        version="0.1.0",
        flow_kind="preparation",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.prepared",),
        input_semantics={"value.in": ("initial numeric value",)},
        output_semantics={"value.prepared": ("prepared numeric value",)},
        params_schema={"offset": {"type": "number"}},
        output_schema={"value.prepared": {"type": "number"}},
        examples=({"inputs": {"value.in": 3}, "params": {"offset": 1}, "outputs": {"value.prepared": 4}},),
    )

    def run_pure(self, inputs, params):
        return {"value.prepared": inputs["value.in"] + params.get("offset", 0)}


class CoreComputeNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.core_compute",
        display_name="Core Compute",
        category="sandbox",
        description="Computes the core value inside a predefined nodeset.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.prepared",),
        provides=("value.out",),
        input_semantics={"value.prepared": ("prepared numeric value",)},
        output_semantics={"value.out": ("computed numeric value",)},
        params_schema={"factor": {"type": "number"}},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {"value.prepared": 4}, "params": {"factor": 2}, "outputs": {"value.out": 8}},),
    )

    def run_pure(self, inputs, params):
        return {"value.out": inputs["value.prepared"] * params.get("factor", 2)}


class RouteDecisionNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.route_decision",
        display_name="Route Decision",
        category="sandbox",
        description="Chooses whether to loop or exit to external post-processing.",
        version="0.1.0",
        flow_kind="decision",
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("flow.route",),
        input_semantics={"value.out": ("computed numeric value",)},
        output_semantics={"flow.route": ("selected route",)},
        params_schema={"threshold": {"type": "number"}},
        output_schema={"flow.route": {"type": "string", "enum": ["again", "external"]}},
        examples=(
            {"inputs": {"value.out": 8}, "params": {"threshold": 10}, "outputs": {"flow.route": "again"}},
            {"inputs": {"value.out": 18}, "params": {"threshold": 10}, "outputs": {"flow.route": "external"}},
        ),
    )

    def run_pure(self, inputs, params):
        return {"flow.route": "again" if inputs["value.out"] < params.get("threshold", 10) else "external"}


class LoopBackNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.loop_back",
        display_name="Loop Back",
        category="sandbox",
        description="Feeds the computed value back into the next loop iteration.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("value.in",),
        input_semantics={"value.out": ("computed numeric value",)},
        output_semantics={"value.in": ("next loop input value",)},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {"value.out": 8}, "params": {}, "outputs": {"value.in": 8}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": inputs["value.out"]}


class ExternalBoostNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.external_boost",
        display_name="External Boost",
        category="sandbox",
        description="Represents externally maintained post-processing code.",
        version="0.1.0",
        flow_kind="process",
        external=True,
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("value.final",),
        input_semantics={"value.out": ("computed numeric value",)},
        output_semantics={"value.final": ("externally adjusted value",)},
        params_schema={"bonus": {"type": "number"}},
        output_schema={"value.final": {"type": "number"}},
        examples=({"inputs": {"value.out": 8}, "params": {"bonus": 5}, "outputs": {"value.final": 13}},),
    )

    def run_pure(self, inputs, params):
        return {"value.final": inputs["value.out"] + params.get("bonus", 5)}


class AuditStoreNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.audit_store",
        display_name="Audit Store",
        category="sandbox",
        description="Models storing an audit request as flow data.",
        version="0.1.0",
        flow_kind="data_store",
    )
    CONTRACT = NodeContract(
        requires=("value.final",),
        provides=("effects.request",),
        input_semantics={"value.final": ("final numeric value",)},
        output_semantics={"effects.request": ("structured audit-store request",)},
        output_schema={"effects.request": {"type": "object"}},
        examples=({"inputs": {"value.final": 13}, "params": {}, "outputs": {"effects.request": {"final": 13}}},),
    )

    def run_pure(self, inputs, params):
        return {"effects.request": {"final": inputs["value.final"]}}


class ReportDocumentNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.report_document",
        display_name="Report Document",
        category="sandbox",
        description="Builds a report document payload.",
        version="0.1.0",
        flow_kind="document",
    )
    CONTRACT = NodeContract(
        requires=("value.final", "effects.request"),
        provides=("document.report",),
        input_semantics={"value.final": ("final numeric value",), "effects.request": ("audit-store request",)},
        output_semantics={"document.report": ("rendered report document",)},
        output_schema={"document.report": {"type": "string"}},
        examples=(
            {
                "inputs": {"value.final": 13, "effects.request": {"final": 13}},
                "params": {},
                "outputs": {"document.report": "final=13;request=13"},
            },
        ),
    )

    def run_pure(self, inputs, params):
        return {"document.report": f"final={inputs['value.final']};request={inputs['effects.request']['final']}"}


class ReportOutputNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.report_output",
        display_name="Report Output",
        category="sandbox",
        description="Adapts the report document to program output.",
        version="0.1.0",
        flow_kind="io",
    )
    CONTRACT = NodeContract(
        requires=("document.report",),
        provides=("io.output",),
        input_semantics={"document.report": ("rendered report document",)},
        output_semantics={"io.output": ("program output payload",)},
        output_schema={"io.output": {"type": "string"}},
        examples=({"inputs": {"document.report": "final=13;request=13"}, "params": {}, "outputs": {"io.output": "final=13;request=13"}},),
    )

    def run_pure(self, inputs, params):
        return {"io.output": inputs["document.report"]}


class ReportEndNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.report_end",
        display_name="Report End",
        category="sandbox",
        description="Ends a flow after io.output is produced.",
        version="0.1.0",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract(
        requires=("io.output",),
        input_semantics={"io.output": ("program output payload",)},
        examples=({"inputs": {"io.output": "final=13;request=13"}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}
