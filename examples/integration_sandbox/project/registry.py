from __future__ import annotations

from vibeflow import NodeRegistry

from nodes.legal_comprehensive_nodes import (
    AuditStoreNode,
    CoreComputeNode,
    ExternalBoostNode,
    LoopBackNode,
    PrepareValueNode,
    ReportDocumentNode,
    ReportEndNode,
    ReportOutputNode,
    RouteDecisionNode,
)
from nodes.legal_external_nodes import EffectRequestNode, IoResultAddNode, IoResultInputNode
from nodes.legal_loop_nodes import CopyBackNode, DoneCheckNode, IncrementNode
from nodes.legal_math_nodes import (
    AddNode,
    AddOutNode,
    AddThreeNode,
    BranchLeftNode,
    BranchRightNode,
    ConstantNode,
    FinalValueEndNode,
    IoInputNode,
    MultiplyNode,
    NextValueEndNode,
    OutValueEndNode,
    StartNode,
    SumPairNode,
    ValueInputNode,
)
from nodes.legal_training_nodes import (
    BackwardGradNode,
    BatchMetricsNode,
    ForwardLossNode,
    OptimizerStepNode,
    SnapshotUnsafeMetricsNode,
    TrainingInputNode,
    TrainingMetricsEndNode,
    TrainingMetricsNode,
)


def build_node_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("sandbox.start", StartNode, config_schema={}, config_defaults={})
    registry.register("sandbox.value_input", ValueInputNode, config_schema={}, config_defaults={})
    registry.register("sandbox.io_input", IoInputNode, config_schema={}, config_defaults={})
    registry.register("sandbox.final_value_end", FinalValueEndNode, config_schema={}, config_defaults={})
    registry.register("sandbox.out_value_end", OutValueEndNode, config_schema={}, config_defaults={})
    registry.register("sandbox.next_value_end", NextValueEndNode, config_schema={}, config_defaults={})
    registry.register("sandbox.constant", ConstantNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 1})
    registry.register("sandbox.add", AddNode, config_schema={"delta": {"type": "number"}}, config_defaults={"delta": 1})
    registry.register("sandbox.add_out", AddOutNode, config_schema={"delta": {"type": "number"}}, config_defaults={"delta": 1})
    registry.register("sandbox.multiply", MultiplyNode, config_schema={"factor": {"type": "number"}}, config_defaults={"factor": 2})
    registry.register("sandbox.branch_left", BranchLeftNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 1})
    registry.register("sandbox.branch_right", BranchRightNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 1})
    registry.register("sandbox.sum_pair", SumPairNode, config_schema={}, config_defaults={})
    registry.register("sandbox.add_three", AddThreeNode, config_schema={}, config_defaults={})
    registry.register("sandbox.increment", IncrementNode, config_schema={}, config_defaults={})
    registry.register("sandbox.copy_back", CopyBackNode, config_schema={}, config_defaults={})
    registry.register("sandbox.done_check", DoneCheckNode, config_schema={"target": {"type": "number"}}, config_defaults={"target": 3})
    registry.register("sandbox.effect_request", EffectRequestNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 1})
    registry.register("sandbox.io_result_add", IoResultAddNode, config_schema={"delta": {"type": "number"}}, config_defaults={"delta": 1})
    registry.register("sandbox.io_result_input", IoResultInputNode, config_schema={"delta": {"type": "number"}}, config_defaults={"delta": 1})
    registry.register("sandbox.prepare_value", PrepareValueNode, config_schema={"offset": {"type": "number"}}, config_defaults={"offset": 0})
    registry.register("sandbox.core_compute", CoreComputeNode, config_schema={"factor": {"type": "number"}}, config_defaults={"factor": 2})
    registry.register("sandbox.route_decision", RouteDecisionNode, config_schema={"threshold": {"type": "number"}}, config_defaults={"threshold": 10})
    registry.register("sandbox.loop_back", LoopBackNode, config_schema={}, config_defaults={})
    registry.register("sandbox.external_boost", ExternalBoostNode, config_schema={"bonus": {"type": "number"}}, config_defaults={"bonus": 5})
    registry.register("sandbox.audit_store", AuditStoreNode, config_schema={}, config_defaults={})
    registry.register("sandbox.report_document", ReportDocumentNode, config_schema={}, config_defaults={})
    registry.register("sandbox.report_output", ReportOutputNode, config_schema={}, config_defaults={})
    registry.register("sandbox.report_end", ReportEndNode, config_schema={}, config_defaults={})
    registry.register("sandbox.training_input", TrainingInputNode, config_schema={}, config_defaults={})
    registry.register("sandbox.forward_loss", ForwardLossNode, config_schema={}, config_defaults={})
    registry.register("sandbox.backward_grad", BackwardGradNode, config_schema={}, config_defaults={})
    registry.register("sandbox.optimizer_step", OptimizerStepNode, config_schema={}, config_defaults={})
    registry.register("sandbox.training_metrics", TrainingMetricsNode, config_schema={}, config_defaults={})
    registry.register("sandbox.batch_metrics", BatchMetricsNode, config_schema={}, config_defaults={})
    registry.register("sandbox.snapshot_unsafe_metrics", SnapshotUnsafeMetricsNode, config_schema={}, config_defaults={})
    registry.register("sandbox.training_metrics_end", TrainingMetricsEndNode, config_schema={}, config_defaults={})
    return registry
