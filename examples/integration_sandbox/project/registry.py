from __future__ import annotations

from vibeflow import BaseLibRegistry, NodeRegistry, PluginResourceRegistry

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
from nodes.legal_loop_nodes import CopyBackNode, DoneCheckNode, DoneValueNode, IncrementNode
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
    ResourceArithmeticNode,
    ResourceScaleNode,
    StartNode,
    SumPairNode,
    ValueInputNode,
)
from nodes.legal_semantic_nodes import (
    SemanticAddPairNode,
    SemanticBranchFinalEndNode,
    SemanticBranchTypeConsumerNode,
    SemanticAsyncValueEndNode,
    SemanticCompareGtNode,
    SemanticConditionalValueNode,
    SemanticCopyNextNode,
    SemanticFinalEndNode,
    SemanticFinalizeNode,
    SemanticIncrementUntilNode,
    SemanticInnerAccumulateNode,
    SemanticInnerLoopInitNode,
    SemanticInactiveRouteNode,
    SemanticJoinPassthroughNode,
    SemanticLeftBranchEndNode,
    SemanticLeftAdjustNode,
    SemanticLeftValueNode,
    SemanticLoopDoneNode,
    SemanticLoopDoneValueNode,
    SemanticLoopEndNode,
    SemanticNestedLoopSeedNode,
    SemanticOtherValueNode,
    SemanticOuterAdvanceNode,
    SemanticRightBranchEndNode,
    SemanticRightAdjustNode,
    SemanticRightValueNode,
    SemanticScaleNode,
    SemanticScaledEndNode,
    SemanticSlowAsyncValueNode,
    SemanticTwoInputJoinNode,
    SemanticUseScaledNode,
    SemanticValueEndNode,
)
from nodes.legal_training_nodes import (
    BackwardGradNode,
    BatchMetricsNode,
    ForwardLossNode,
    OptimizerStepNode,
    TrainingBatchStepNode,
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
    registry.register(
        "sandbox.resource_arithmetic",
        ResourceArithmeticNode,
        config_schema={
            "addend": {"type": "number"},
            "multiplier": {"type": "number"},
            "subtrahend": {"type": "number"},
            "divisor": {"type": "number"},
        },
        config_defaults={"addend": 0, "multiplier": 1, "subtrahend": 0, "divisor": 1},
    )
    registry.register("sandbox.resource_scale", ResourceScaleNode, config_schema={"factor": {"type": "number"}}, config_defaults={"factor": 1})
    registry.register("sandbox.increment", IncrementNode, config_schema={}, config_defaults={})
    registry.register("sandbox.copy_back", CopyBackNode, config_schema={}, config_defaults={})
    registry.register("sandbox.done_check", DoneCheckNode, config_schema={"target": {"type": "number"}}, config_defaults={"target": 3})
    registry.register("sandbox.done_value", DoneValueNode, config_schema={"target": {"type": "number"}}, config_defaults={"target": 3})
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
    registry.register("sandbox.training_batch_step", TrainingBatchStepNode, config_schema={}, config_defaults={})
    registry.register("sandbox.batch_metrics", BatchMetricsNode, config_schema={}, config_defaults={})
    registry.register("sandbox.training_metrics_end", TrainingMetricsEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.add_pair", SemanticAddPairNode, config_schema={}, config_defaults={})
    registry.register("semantic.scale", SemanticScaleNode, config_schema={"factor": {"type": "number"}}, config_defaults={"factor": 1})
    registry.register("semantic.use_scaled", SemanticUseScaledNode, config_schema={}, config_defaults={})
    registry.register("semantic.compare_gt", SemanticCompareGtNode, config_schema={}, config_defaults={})
    registry.register("semantic.left_adjust", SemanticLeftAdjustNode, config_schema={"bonus": {"type": "number"}}, config_defaults={"bonus": 0})
    registry.register("semantic.right_adjust", SemanticRightAdjustNode, config_schema={"penalty": {"type": "number"}}, config_defaults={"penalty": 0})
    registry.register("semantic.branch_type_consumer", SemanticBranchTypeConsumerNode, config_schema={}, config_defaults={})
    registry.register("semantic.branch_final_end", SemanticBranchFinalEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.join_passthrough", SemanticJoinPassthroughNode, config_schema={}, config_defaults={})
    registry.register("semantic.value_end", SemanticValueEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.inactive_route", SemanticInactiveRouteNode, config_schema={}, config_defaults={})
    registry.register("semantic.conditional_value", SemanticConditionalValueNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 7})
    registry.register("semantic.left_value", SemanticLeftValueNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 1})
    registry.register("semantic.right_value", SemanticRightValueNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 2})
    registry.register("semantic.other_value", SemanticOtherValueNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 5})
    registry.register("semantic.two_input_join", SemanticTwoInputJoinNode, config_schema={}, config_defaults={})
    registry.register("semantic.finalize", SemanticFinalizeNode, config_schema={"offset": {"type": "number"}}, config_defaults={"offset": 0})
    registry.register("semantic.increment_until", SemanticIncrementUntilNode, config_schema={"step": {"type": "number"}}, config_defaults={"step": 1})
    registry.register("semantic.loop_done", SemanticLoopDoneNode, config_schema={"target": {"type": "number"}}, config_defaults={"target": 0})
    registry.register("semantic.loop_done_value", SemanticLoopDoneValueNode, config_schema={"target": {"type": "number"}}, config_defaults={"target": 0})
    registry.register("semantic.nested_loop_seed", SemanticNestedLoopSeedNode, config_schema={"outer_start": {"type": "number"}, "total_start": {"type": "number"}}, config_defaults={"outer_start": 0, "total_start": 0})
    registry.register("semantic.inner_loop_init", SemanticInnerLoopInitNode, config_schema={"inner_start": {"type": "number"}}, config_defaults={"inner_start": 0})
    registry.register("semantic.inner_accumulate", SemanticInnerAccumulateNode, config_schema={"inner_step": {"type": "number"}, "inner_limit": {"type": "number"}}, config_defaults={"inner_step": 1, "inner_limit": 1})
    registry.register("semantic.outer_advance", SemanticOuterAdvanceNode, config_schema={"outer_step": {"type": "number"}, "outer_limit": {"type": "number"}}, config_defaults={"outer_step": 1, "outer_limit": 1})
    registry.register("semantic.copy_next", SemanticCopyNextNode, config_schema={}, config_defaults={})
    registry.register("semantic.slow_async_value", SemanticSlowAsyncValueNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 42})
    registry.register("semantic.async_value_end", SemanticAsyncValueEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.scaled_end", SemanticScaledEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.final_end", SemanticFinalEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.left_branch_end", SemanticLeftBranchEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.right_branch_end", SemanticRightBranchEndNode, config_schema={}, config_defaults={})
    registry.register("semantic.loop_end", SemanticLoopEndNode, config_schema={}, config_defaults={})
    return registry


def build_base_lib_registry() -> BaseLibRegistry:
    registry = BaseLibRegistry()
    registry.register(
        "good_math",
        module="base_lib.good_math",
        display_name="Good Math",
        category="sandbox",
        description="Validated arithmetic helper functions for sandbox resource checks.",
        version="0.1.0",
    )
    registry.register(
        "good_chain_a",
        module="base_lib.good_chain_a",
        display_name="Good Chain A",
        category="sandbox",
        description="A valid dependency-chain helper module for sandbox resource checks.",
        version="0.1.0",
    )
    registry.register(
        "sandbox_arithmetic",
        module="base_lib.sandbox_arithmetic",
        display_name="Sandbox Arithmetic",
        category="sandbox",
        description="Arithmetic helper functions used by the resource nodeset fixture.",
        version="0.1.0",
    )
    return registry


def build_plugin_registry() -> PluginResourceRegistry:
    registry = PluginResourceRegistry()
    registry.register(
        "value_shift",
        module="plugins.value_plugin",
        class_name="ValueShiftPlugin",
        plugin_type="runtime",
        display_name="Sandbox Value Shift",
        category="sandbox",
        description="Runtime plugin that shifts sandbox values during resource fixture execution.",
        version="0.1.0",
    )
    registry.register(
        "policy_plugin",
        module="plugins.policy_plugins",
        class_name="PolicyPlugin",
        plugin_type="policy",
        display_name="Policy Plugin",
        category="sandbox",
        description="Extends sandbox policy checks for the plugin fixture.",
        version="0.1.0",
    )
    registry.register(
        "finding_plugin",
        module="plugins.policy_plugins",
        class_name="FindingPlugin",
        plugin_type="policy",
        display_name="Finding Plugin",
        category="sandbox",
        description="Adds a sandbox graph finding through the policy plugin interface.",
        version="0.1.0",
    )
    registry.register(
        "compiler_hook",
        module="plugins.hook_plugins",
        class_name="CompilerPlugin",
        plugin_type="compiler",
        display_name="Compiler Hook Plugin",
        category="sandbox",
        description="Records compiler hook calls for the plugin fixture.",
        version="0.1.0",
    )
    registry.register(
        "runtime_hook",
        module="plugins.hook_plugins",
        class_name="RuntimePlugin",
        plugin_type="runtime",
        display_name="Runtime Hook Plugin",
        category="sandbox",
        description="Records runtime hook calls for the plugin fixture.",
        version="0.1.0",
    )
    return registry
