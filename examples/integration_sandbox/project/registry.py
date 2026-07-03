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
from nodes.legal_semantic_nodes import (
    SemanticAddPairNode,
    SemanticAsyncValueEndNode,
    SemanticCompareGtNode,
    SemanticCopyNextNode,
    SemanticFinalEndNode,
    SemanticFinalizeNode,
    SemanticIncrementUntilNode,
    SemanticLeftBranchEndNode,
    SemanticLeftAdjustNode,
    SemanticLoopDoneNode,
    SemanticLoopEndNode,
    SemanticRightBranchEndNode,
    SemanticRightAdjustNode,
    SemanticScaleNode,
    SemanticScaledEndNode,
    SemanticSlowAsyncValueNode,
    SemanticUseScaledNode,
)
from nodes.legal_training_nodes import (
    BackwardGradNode,
    BatchMetricsNode,
    ForwardLossNode,
    OptimizerStepNode,
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
    registry.register("sandbox.training_metrics_end", TrainingMetricsEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.add_pair", SemanticAddPairNode, config_schema={}, config_defaults={})
    registry.register("semantic.scale", SemanticScaleNode, config_schema={"factor": {"type": "number"}}, config_defaults={"factor": 1})
    registry.register("semantic.use_scaled", SemanticUseScaledNode, config_schema={}, config_defaults={})
    registry.register("semantic.compare_gt", SemanticCompareGtNode, config_schema={}, config_defaults={})
    registry.register("semantic.left_adjust", SemanticLeftAdjustNode, config_schema={"bonus": {"type": "number"}}, config_defaults={"bonus": 0})
    registry.register("semantic.right_adjust", SemanticRightAdjustNode, config_schema={"penalty": {"type": "number"}}, config_defaults={"penalty": 0})
    registry.register("semantic.finalize", SemanticFinalizeNode, config_schema={"offset": {"type": "number"}}, config_defaults={"offset": 0})
    registry.register("semantic.increment_until", SemanticIncrementUntilNode, config_schema={"step": {"type": "number"}}, config_defaults={"step": 1})
    registry.register("semantic.loop_done", SemanticLoopDoneNode, config_schema={"target": {"type": "number"}}, config_defaults={"target": 0})
    registry.register("semantic.copy_next", SemanticCopyNextNode, config_schema={}, config_defaults={})
    registry.register("semantic.slow_async_value", SemanticSlowAsyncValueNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 42})
    registry.register("semantic.async_value_end", SemanticAsyncValueEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.scaled_end", SemanticScaledEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.final_end", SemanticFinalEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.left_branch_end", SemanticLeftBranchEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.right_branch_end", SemanticRightBranchEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.loop_end", SemanticLoopEndNode, config_schema={}, config_defaults={})
    return registry
