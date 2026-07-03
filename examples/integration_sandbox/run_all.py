from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SANDBOX_DIR = Path(__file__).resolve().parent
REPO_ROOT = SANDBOX_DIR.parents[1]
SRC_KERNEL = REPO_ROOT / "src" / "vibeflow"
KERNEL_DIR = SANDBOX_DIR / "kernel"
KERNEL_LINK = KERNEL_DIR / "vibeflow"
PROJECT_DIR = SANDBOX_DIR / "project"
CONFIG_DIR = PROJECT_DIR / "configs"
REPORT_DIR = SANDBOX_DIR / "reports"
ASCII_DIR = REPORT_DIR / "ascii"
MERMAID_DIR = REPORT_DIR / "mermaid"
SVG_DIR = REPORT_DIR / "svg"
COMPILED_BLOCK_DIR = REPORT_DIR / "compiled_blocks"
RUN_ROOT = SANDBOX_DIR / "runs"
POLICY_PATH = PROJECT_DIR / "kernel_policy.jsonc"


class SandboxBatch:
    def __init__(self, items: list[int]) -> None:
        self.items = items


class SandboxModel:
    def __init__(self, weight: float) -> None:
        self.weight = weight

    def loss(self, batch: SandboxBatch) -> float:
        return sum(batch.items) * self.weight

    def grad(self, loss: float) -> float:
        return loss / 10


class SandboxOptimizer:
    def __init__(self, lr: float) -> None:
        self.lr = lr
        self.steps = 0

    def step(self, model: SandboxModel, grad: float) -> None:
        model.weight -= self.lr * grad
        self.steps += 1


def _training_initial() -> dict[str, Any]:
    return {"train.model": SandboxModel(1.0), "train.batch": SandboxBatch([2, 4]), "train.optimizer": SandboxOptimizer(0.5)}


def _batch_initial() -> dict[str, Any]:
    return {"train.batch": SandboxBatch([2, 4])}


COMPILED_SOURCE_FULL_REQUIRED = ("_execute_pure_outputs", "select_active_edges", "_record_edge")
COMPILED_SOURCE_FAST_REQUIRED = ("_execute_pure_outputs", "select_active_edges")
COMPILED_SOURCE_FORBIDDEN = ("_run_node(",)
COMPILED_SOURCE_FAST_FORBIDDEN = ("_run_node(", "_record_edge(edge)", "summarize_mapping(inputs)", "summarize_mapping(outputs)", "'node',")


VALID_RUN_CASES = [
    {"name": "linear", "config": "pass_linear.jsonc", "initial": {}, "expected_status": {"PASS", "CONCERNS"}, "expected_outputs": {"value.final": 14}},
    {"name": "free_nodes", "config": "pass_free_nodes.jsonc", "initial": {}, "expected_status": {"PASS", "CONCERNS"}},
    {"name": "decision_cycle_short", "config": "pass_decision_cycle_short.jsonc", "initial": {"value.in": 0}},
    {"name": "decision_cycle_long", "config": "pass_decision_cycle_long.jsonc", "initial": {"value.in": 0}},
    {"name": "nodeset_simple", "config": "pass_nodeset_simple.jsonc", "initial": {"value.in": 1}, "expected_outputs": {"value.out": 6}},
    {"name": "nodeset_nested", "config": "pass_nodeset_nested.jsonc", "initial": {"value.in": 1}, "expected_outputs": {"value.final": 11}},
    {"name": "io_data_store", "config": "pass_io_data_store.jsonc", "initial": {"io.result": 20}},
    {"name": "plugins", "config": "pass_plugins.jsonc", "initial": {"io.result": 20}},
    {"name": "comprehensive_flowchart", "config": "pass_comprehensive_flowchart.jsonc", "initial": {"value.in": 3}, "expected_outputs": {"io.output": "final=23;request=23"}},
    {
        "name": "training_object_flow",
        "config": "pass_training_object_flow.jsonc",
        "initial_factory": _training_initial,
        "expected_outputs": {"train.loss": 6.0, "train.grad": 0.6, "train.step_report": {"steps": 1, "weight": 0.7}},
        "expected_same_as_initial": [("train.model_after", "train.model"), ("train.optimizer_after", "train.optimizer")],
        "expected_object_attrs": [("train.model_after", "weight", 0.7), ("train.optimizer_after", "steps", 1)],
        "expect_training_metrics": True,
    },
    {
        "name": "training_nodeset_object_flow",
        "config": "pass_training_nodeset_object_flow.jsonc",
        "initial_factory": _training_initial,
        "expected_outputs": {"train.step_report": {"steps": 1, "weight": 0.7}},
        "expected_same_as_initial": [("train.model_after", "train.model"), ("train.optimizer_after", "train.optimizer")],
        "expected_object_attrs": [("train.model_after", "weight", 0.7), ("train.optimizer_after", "steps", 1)],
        "expect_training_metrics": True,
    },
    {
        "name": "training_non_json_metrics",
        "config": "pass_training_non_json_metrics.jsonc",
        "initial_factory": _batch_initial,
        "expect_batch_metrics": True,
    },
    {
        "name": "runtime_boundary_trace",
        "config": "pass_runtime_boundary_trace.jsonc",
        "initial": {"value.in": 1},
        "runtime_options": {"trace": "boundary"},
        "expected_outputs": {"value.out": 6},
        "expected_trace_kinds": ["run_start", "nodeset_enter", "nodeset_exit", "run_end", "runtime_summary"],
    },
    {
        "name": "runtime_trace_off",
        "config": "pass_runtime_trace_off.jsonc",
        "initial": {},
        "runtime_options": {"trace": "off"},
        "expected_outputs": {"value.out": 7},
        "expected_trace_kinds": ["runtime_summary"],
        "expected_trace_summary": {"stop_reason": "completed", "current_node": "end"},
    },
    {
        "name": "runtime_node_hooks_off",
        "config": "pass_runtime_node_hooks_off.jsonc",
        "initial": {},
        "runtime_options": {"node_hooks": False},
        "expected_outputs": {"value.out": 6},
        "expected_hook_delta_present": {"after_run"},
        "expected_hook_delta_absent": {"before_node", "after_node"},
    },
    {
        "name": "compiled_trace_full",
        "config": "pass_runtime_node_hooks_off.jsonc",
        "initial": {},
        "runtime_options": {"trace": "full", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"value.out": 6},
        "expected_trace_kinds": ["block_enter", "node", "node", "node", "node", "block_exit", "runtime_summary"],
        "expected_trace_kind_counts": {"block_enter": 1, "node": 4, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "end",
            "edge_executions": {"start->seed": 1, "seed->add": 1, "add->end": 1},
            "exec_order": ["start", "seed", "add", "end"],
            "node_runs": {"start": 1, "seed": 1, "add": 1, "end": 1},
            "step_count": 4,
            "stop_reason": "completed",
        },
    },
    {
        "name": "compiled_with_node_hooks",
        "config": "pass_runtime_node_hooks_off.jsonc",
        "initial": {},
        "runtime_options": {"trace": "boundary", "node_hooks": True, "execution": "compiled"},
        "expected_outputs": {"value.out": 6},
        "expected_trace_kind_counts": {"block_enter": 1, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "end",
            "exec_order": ["start", "seed", "add", "end"],
            "node_runs": {"start": 1, "seed": 1, "add": 1, "end": 1},
            "step_count": 4,
            "stop_reason": "completed",
        },
        "expected_hook_delta_present": {"before_node", "after_node", "after_run"},
    },
    {
        "name": "semantic_linear_arithmetic",
        "config": "pass_semantic_linear_arithmetic.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 21, "calc.branch": 21, "calc.final": 17},
        "expected_runtime_exec_order": ["start", "add_pair", "scale", "use_scaled", "finalize", "end"],
        "expected_trace_summary": {
            "current_node": "end",
            "edge_executions": {"start->add_pair": 1, "add_pair->scale": 1, "scale->use_scaled": 1, "use_scaled->finalize": 1, "finalize->end": 1},
            "exec_order": ["start", "add_pair", "scale", "use_scaled", "finalize", "end"],
            "node_runs": {"start": 1, "add_pair": 1, "scale": 1, "use_scaled": 1, "finalize": 1, "end": 1},
            "step_count": 6,
            "stop_reason": "completed",
        },
    },
    {
        "name": "compiled_semantic_linear_arithmetic",
        "config": "pass_semantic_linear_arithmetic.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5},
        "runtime_options": {"trace": "boundary", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 21, "calc.branch": 21, "calc.final": 17},
        "expected_runtime_exec_order": ["start", "add_pair", "scale", "use_scaled", "finalize", "end"],
        "expected_trace_kind_counts": {"block_enter": 1, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "end",
            "exec_order": ["start", "add_pair", "scale", "use_scaled", "finalize", "end"],
            "node_runs": {"start": 1, "add_pair": 1, "scale": 1, "use_scaled": 1, "finalize": 1, "end": 1},
            "step_count": 6,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "add_pair", "scale", "use_scaled", "finalize", "end"]],
        "expected_block_source_contains": COMPILED_SOURCE_FAST_REQUIRED,
        "expected_block_source_absent": COMPILED_SOURCE_FAST_FORBIDDEN,
    },
    {
        "name": "compiled_full_semantic_linear_arithmetic",
        "config": "pass_semantic_linear_arithmetic.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5},
        "runtime_options": {"trace": "full", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 21, "calc.branch": 21, "calc.final": 17},
        "expected_trace_kind_counts": {"block_enter": 1, "node": 6, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "end",
            "edge_executions": {"start->add_pair": 1, "add_pair->scale": 1, "scale->use_scaled": 1, "use_scaled->finalize": 1, "finalize->end": 1},
            "exec_order": ["start", "add_pair", "scale", "use_scaled", "finalize", "end"],
            "node_runs": {"start": 1, "add_pair": 1, "scale": 1, "use_scaled": 1, "finalize": 1, "end": 1},
            "step_count": 6,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "add_pair", "scale", "use_scaled", "finalize", "end"]],
        "expected_block_source_contains": COMPILED_SOURCE_FULL_REQUIRED,
        "expected_block_source_absent": COMPILED_SOURCE_FORBIDDEN,
    },
    {
        "name": "semantic_decision_branch_left",
        "config": "pass_semantic_decision_branch.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5, "calc.c": 9, "calc.d": 4},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 21, "route.branch": "left", "calc.left_branch": 31},
        "expected_runtime_exec_order": ["start", "add_pair", "compare", "scale", "left_adjust", "left_end"],
        "expected_trace_summary": {
            "current_node": "left_end",
            "edge_executions": {"start->add_pair": 1, "start->compare": 1, "add_pair->scale": 1, "scale->left_adjust": 1, "scale->right_adjust": 1, "compare->left_adjust": 1, "left_adjust->left_end": 1},
            "exec_order": ["start", "add_pair", "compare", "scale", "left_adjust", "left_end"],
            "node_runs": {"start": 1, "add_pair": 1, "scale": 1, "compare": 1, "left_adjust": 1, "left_end": 1},
            "step_count": 6,
            "stop_reason": "completed",
        },
    },
    {
        "name": "semantic_decision_branch_right",
        "config": "pass_semantic_decision_branch.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5, "calc.c": 1, "calc.d": 4},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 21, "route.branch": "right", "calc.right_branch": 15},
        "expected_runtime_exec_order": ["start", "add_pair", "compare", "scale", "right_adjust", "right_end"],
        "expected_trace_summary": {
            "current_node": "right_end",
            "edge_executions": {"start->add_pair": 1, "start->compare": 1, "add_pair->scale": 1, "scale->left_adjust": 1, "scale->right_adjust": 1, "compare->right_adjust": 1, "right_adjust->right_end": 1},
            "exec_order": ["start", "add_pair", "compare", "scale", "right_adjust", "right_end"],
            "node_runs": {"start": 1, "add_pair": 1, "scale": 1, "compare": 1, "right_adjust": 1, "right_end": 1},
            "step_count": 6,
            "stop_reason": "completed",
        },
    },
    {
        "name": "compiled_semantic_decision_branch_left",
        "config": "pass_semantic_decision_branch.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5, "calc.c": 9, "calc.d": 4},
        "runtime_options": {"trace": "boundary", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 21, "route.branch": "left", "calc.left_branch": 31},
        "expected_runtime_exec_order": ["start", "add_pair", "compare", "scale", "left_adjust", "left_end"],
        "expected_trace_kind_counts": {"block_enter": 1, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "left_end",
            "exec_order": ["start", "add_pair", "compare", "scale", "left_adjust", "left_end"],
            "node_runs": {"start": 1, "add_pair": 1, "scale": 1, "compare": 1, "left_adjust": 1, "left_end": 1},
            "step_count": 6,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "add_pair", "scale", "compare", "left_adjust", "right_adjust", "left_end", "right_end"]],
        "expected_block_source_contains": COMPILED_SOURCE_FAST_REQUIRED,
        "expected_block_source_absent": COMPILED_SOURCE_FAST_FORBIDDEN,
    },
    {
        "name": "compiled_full_semantic_decision_branch_left",
        "config": "pass_semantic_decision_branch.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5, "calc.c": 9, "calc.d": 4},
        "runtime_options": {"trace": "full", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 21, "route.branch": "left", "calc.left_branch": 31},
        "expected_trace_kind_counts": {"block_enter": 1, "node": 6, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "left_end",
            "edge_executions": {"start->add_pair": 1, "start->compare": 1, "add_pair->scale": 1, "scale->left_adjust": 1, "scale->right_adjust": 1, "compare->left_adjust": 1, "left_adjust->left_end": 1},
            "exec_order": ["start", "add_pair", "compare", "scale", "left_adjust", "left_end"],
            "node_runs": {"start": 1, "add_pair": 1, "scale": 1, "compare": 1, "left_adjust": 1, "left_end": 1},
            "step_count": 6,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "add_pair", "scale", "compare", "left_adjust", "right_adjust", "left_end", "right_end"]],
        "expected_block_source_contains": COMPILED_SOURCE_FULL_REQUIRED,
        "expected_block_source_absent": COMPILED_SOURCE_FORBIDDEN,
    },
    {
        "name": "compiled_semantic_decision_branch_right",
        "config": "pass_semantic_decision_branch.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5, "calc.c": 1, "calc.d": 4},
        "runtime_options": {"trace": "boundary", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 21, "route.branch": "right", "calc.right_branch": 15},
        "expected_runtime_exec_order": ["start", "add_pair", "compare", "scale", "right_adjust", "right_end"],
        "expected_trace_kind_counts": {"block_enter": 1, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "right_end",
            "exec_order": ["start", "add_pair", "compare", "scale", "right_adjust", "right_end"],
            "node_runs": {"start": 1, "add_pair": 1, "scale": 1, "compare": 1, "right_adjust": 1, "right_end": 1},
            "step_count": 6,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "add_pair", "scale", "compare", "left_adjust", "right_adjust", "left_end", "right_end"]],
        "expected_block_source_contains": COMPILED_SOURCE_FAST_REQUIRED,
        "expected_block_source_absent": COMPILED_SOURCE_FAST_FORBIDDEN,
    },
    {
        "name": "semantic_decision_loop",
        "config": "pass_semantic_decision_loop.jsonc",
        "initial": {"loop.current": 1},
        "expected_outputs": {"loop.next": 7, "loop.done": True},
        "expected_runtime_exec_order": ["start", "increment", "done", "copy", "increment", "done", "copy", "increment", "done", "end"],
        "expected_trace_summary": {
            "current_node": "end",
            "edge_executions": {"start->increment": 1, "increment->done": 3, "done->copy": 2, "copy->increment": 2, "done->end": 1},
            "exec_order": ["start", "increment", "done", "copy", "increment", "done", "copy", "increment", "done", "end"],
            "node_runs": {"start": 1, "increment": 3, "done": 3, "copy": 2, "end": 1},
            "step_count": 10,
            "stop_reason": "completed",
        },
    },
    {
        "name": "compiled_semantic_decision_loop",
        "config": "pass_semantic_decision_loop.jsonc",
        "initial": {"loop.current": 1},
        "runtime_options": {"trace": "boundary", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"loop.next": 7, "loop.done": True},
        "expected_runtime_exec_order": ["start", "increment", "done", "copy", "increment", "done", "copy", "increment", "done", "end"],
        "expected_trace_kind_counts": {"block_enter": 1, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "end",
            "exec_order": ["start", "increment", "done", "copy", "increment", "done", "copy", "increment", "done", "end"],
            "node_runs": {"start": 1, "increment": 3, "done": 3, "copy": 2, "end": 1},
            "step_count": 10,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "increment", "done", "copy", "end"]],
        "expected_block_source_contains": COMPILED_SOURCE_FAST_REQUIRED,
        "expected_block_source_absent": COMPILED_SOURCE_FAST_FORBIDDEN,
    },
    {
        "name": "compiled_full_semantic_decision_loop",
        "config": "pass_semantic_decision_loop.jsonc",
        "initial": {"loop.current": 1},
        "runtime_options": {"trace": "full", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"loop.next": 7, "loop.done": True},
        "expected_trace_kind_counts": {"block_enter": 1, "node": 10, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "end",
            "edge_executions": {"start->increment": 1, "increment->done": 3, "done->copy": 2, "copy->increment": 2, "done->end": 1},
            "exec_order": ["start", "increment", "done", "copy", "increment", "done", "copy", "increment", "done", "end"],
            "node_runs": {"start": 1, "increment": 3, "done": 3, "copy": 2, "end": 1},
            "step_count": 10,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "increment", "done", "copy", "end"]],
        "expected_block_source_contains": COMPILED_SOURCE_FULL_REQUIRED,
        "expected_block_source_absent": COMPILED_SOURCE_FORBIDDEN,
    },
    {
        "name": "semantic_nodeset_arithmetic",
        "config": "pass_semantic_nodeset_arithmetic.jsonc",
        "initial": {"calc.a": 4, "calc.b": 6},
        "expected_outputs": {"calc.scaled": 20, "calc.branch": 20, "calc.final": 25},
        "expected_runtime_exec_order": ["start", "arithmetic", "use_scaled", "finalize", "end"],
        "expected_trace_summary": {
            "current_node": "end",
            "edge_executions": {"start->arithmetic": 1, "arithmetic->use_scaled": 1, "use_scaled->finalize": 1, "finalize->end": 1},
            "exec_order": ["start", "arithmetic", "use_scaled", "finalize", "end"],
            "node_runs": {"start": 1, "arithmetic": 1, "use_scaled": 1, "finalize": 1, "end": 1},
            "step_count": 5,
            "stop_reason": "completed",
        },
        "expected_nodeset_subplan_params": {"arithmetic.scale": {"factor": 2}},
        "expected_nodeset_subplan_nodes": {"arithmetic": ["start", "add_pair", "scale", "end"]},
        "expected_nodeset_exports": {"arithmetic": ["calc.scaled"]},
    },
    {
        "name": "config_resources_nodeset_arithmetic",
        "config": "pass_config_resources_nodeset_arithmetic.jsonc",
        "initial": {"calc.a": 4, "calc.b": 6},
        "expected_outputs": {"calc.sum": 10, "calc.resource": 50, "calc.final": 203},
        "expected_plan_params": {
            "resource_calc": {
                "addend": 5,
                "multiplier": 3,
                "subtrahend": 4,
                "divisor": 1,
                "_global": {"addend": 5, "multiplier": 3, "subtrahend": 4, "divisor": 1},
            }
        },
        "expected_nodeset_subplan_params": {"configured_finalize.scale": {"factor": 4}, "configured_finalize.finalize": {"offset": 3}},
        "expected_nodeset_exports": {"configured_finalize": ["calc.final"]},
        "expected_health_warnings": [
            "NODESET.CONFIG.OVERRIDES_GLOBAL_CONFIG",
            "CONFIG.GLOBAL_CONFIG.OVERRIDES_LOCAL",
        ],
        "expected_mermaid_contains": [
            "resource_base_lib",
            "Sandbox Arithmetic",
            "base_lib.future_arithmetic",
            "resource_plugins",
            "Sandbox Value Shift",
            "future_value_plugin",
            "config: shift",
        ],
        "expected_run_mermaid_contains": [
            "Sandbox Arithmetic",
            "Sandbox Value Shift",
            "planned runtime value hook",
        ],
    },
    {
        "name": "planned_python_stub_arithmetic",
        "config": "pass_planned_python_stub_arithmetic.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5},
        "runtime_options": {"allow_planned_stub": True, "trace": "boundary"},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 30, "calc.branch": 30, "calc.final": 36},
        "expected_runtime_exec_order": ["start", "add_pair", "planned_scale", "use_scaled", "finalize", "end"],
        "expected_trace_kind_counts": {"planned_stub": 1},
        "expected_plan_params": {
            "planned_scale": {
                "factor": 4,
                "bias": 2,
                "_global": {"bias": 2},
            }
        },
        "expected_health_warnings": [
            "GRAPH.PLANNED.NODE",
            "GRAPH.PLANNED.PYTHON_STUB_DEV_ONLY",
        ],
        "expected_mermaid_contains": [
            "planned python_stub",
            "project/stubs/runtime_control_stub.py",
        ],
        "expected_run_mermaid_contains": [
            "planned python_stub",
            "project/stubs/runtime_control_stub.py",
        ],
    },
    {
        "name": "compiled_semantic_nodeset_arithmetic",
        "config": "pass_semantic_nodeset_arithmetic.jsonc",
        "initial": {"calc.a": 4, "calc.b": 6},
        "runtime_options": {"trace": "boundary", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"calc.scaled": 20, "calc.branch": 20, "calc.final": 25},
        "expected_runtime_exec_order": ["start", "arithmetic", "use_scaled", "finalize", "end"],
        "expected_trace_kind_counts": {"nodeset_enter": 1, "nodeset_exit": 1, "block_enter": 1, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "end",
            "edge_executions": {"start->arithmetic": 1, "arithmetic->use_scaled": 1},
            "exec_order": ["start", "arithmetic", "use_scaled", "finalize", "end"],
            "node_runs": {"start": 1, "arithmetic": 1, "use_scaled": 1, "finalize": 1, "end": 1},
            "step_count": 5,
            "stop_reason": "completed",
        },
        "expected_blocks": [["use_scaled", "finalize", "end"]],
        "expected_nodeset_subplan_params": {"arithmetic.scale": {"factor": 2}},
        "expected_nodeset_subplan_nodes": {"arithmetic": ["start", "add_pair", "scale", "end"]},
        "expected_nodeset_exports": {"arithmetic": ["calc.scaled"]},
        "expected_block_source_contains": COMPILED_SOURCE_FAST_REQUIRED,
        "expected_block_source_absent": COMPILED_SOURCE_FAST_FORBIDDEN,
    },
    {
        "name": "execution_plan_bound_params",
        "config": "pass_execution_plan_bound_params.jsonc",
        "initial": {},
        "expected_outputs": {"value.final": 26},
        "expected_plan_params": {"seed": {"value": 4}, "add": {"delta": 9}, "multiply": {"factor": 2}},
    },
    {
        "name": "execution_plan_nodeset_subplan",
        "config": "pass_execution_plan_nodeset_subplan.jsonc",
        "initial": {"value.in": 2},
        "expected_outputs": {"value.out": 10},
        "expected_nodeset_subplan_params": {"add_one.add": {"delta": 8}},
    },
    {
        "name": "execution_plan_training_nodeset",
        "config": "pass_execution_plan_training_nodeset.jsonc",
        "initial_factory": _training_initial,
        "expected_outputs": {"train.step_report": {"steps": 1, "weight": 0.7}},
        "expected_same_as_initial": [("train.model_after", "train.model"), ("train.optimizer_after", "train.optimizer")],
        "expected_object_attrs": [("train.model_after", "weight", 0.7), ("train.optimizer_after", "steps", 1)],
        "expect_training_metrics": True,
        "expected_nodeset_subplan_nodes": {"training_step": ["start", "training_input", "forward_loss", "backward_grad", "optimizer_step", "training_metrics", "end"]},
    },
    {
        "name": "nodeset_loop_subplan_reuse",
        "config": "pass_nodeset_loop_subplan_reuse.jsonc",
        "initial": {"value.in": 1},
        "expected_outputs": {"value.next": 3},
        "expected_nodeset_exports": {"increment_step": ["value.next"]},
        "expected_trace_kind_counts": {"nodeset_enter": 2, "nodeset_exit": 2},
    },
    {
        "name": "nodeset_reference_exports",
        "config": "pass_nodeset_reference_exports.jsonc",
        "initial_factory": _training_initial,
        "expected_outputs": {"train.step_report": {"steps": 1, "weight": 0.7}},
        "expected_same_as_initial": [("train.model_after", "train.model"), ("train.optimizer_after", "train.optimizer")],
        "expected_object_attrs": [("train.model_after", "weight", 0.7), ("train.optimizer_after", "steps", 1)],
        "expect_training_metrics": True,
        "expected_nodeset_exports": {"train_step": ["train.model_after", "train.optimizer_after", "train.step_report", "train.metrics"]},
    },
    {
        "name": "block_linear_training",
        "config": "pass_block_linear_training.jsonc",
        "initial_factory": _training_initial,
        "runtime_options": {"execution": "block"},
        "expected_outputs": {"train.loss": 6.0, "train.grad": 0.6, "train.step_report": {"steps": 1, "weight": 0.7}},
        "expected_same_as_initial": [("train.model_after", "train.model"), ("train.optimizer_after", "train.optimizer")],
        "expected_object_attrs": [("train.model_after", "weight", 0.7), ("train.optimizer_after", "steps", 1)],
        "expect_training_metrics": True,
        "expected_runtime_exec_order": ["start", "training_input", "forward_loss", "backward_grad", "optimizer_step", "training_metrics", "end"],
    },
    {
        "name": "compiled_linear_training",
        "config": "pass_block_linear_training.jsonc",
        "initial_factory": _training_initial,
        "runtime_options": {"trace": "boundary", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"train.loss": 6.0, "train.grad": 0.6, "train.step_report": {"steps": 1, "weight": 0.7}},
        "expected_same_as_initial": [("train.model_after", "train.model"), ("train.optimizer_after", "train.optimizer")],
        "expected_object_attrs": [("train.model_after", "weight", 0.7), ("train.optimizer_after", "steps", 1)],
        "expect_training_metrics": True,
        "expected_runtime_exec_order": ["start", "training_input", "forward_loss", "backward_grad", "optimizer_step", "training_metrics", "end"],
        "expected_trace_kind_counts": {"block_enter": 1, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "end",
            "node_runs": {
                "start": 1,
                "training_input": 1,
                "forward_loss": 1,
                "backward_grad": 1,
                "optimizer_step": 1,
                "training_metrics": 1,
                "end": 1,
            },
            "step_count": 7,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "training_input", "forward_loss", "backward_grad", "optimizer_step", "training_metrics", "end"]],
    },
    {
        "name": "block_decision_loop",
        "config": "pass_block_decision_loop.jsonc",
        "initial": {"value.in": 1},
        "runtime_options": {"execution": "block"},
        "expected_outputs": {"value.next": 3},
        "expected_runtime_exec_order": ["start", "input", "increment", "done", "copy", "increment", "done", "end"],
    },
    {
        "name": "compiled_decision_loop",
        "config": "pass_block_decision_loop.jsonc",
        "initial": {"value.in": 1},
        "runtime_options": {"trace": "boundary", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"value.next": 3},
        "expected_runtime_exec_order": ["start", "input", "increment", "done", "copy", "increment", "done", "end"],
        "expected_trace_kind_counts": {"block_enter": 1, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "end",
            "exec_order": ["start", "input", "increment", "done", "copy", "increment", "done", "end"],
            "node_runs": {"start": 1, "input": 1, "increment": 2, "done": 2, "copy": 1, "end": 1},
            "step_count": 8,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "input", "increment", "done", "copy", "end"]],
    },
    {
        "name": "compiled_decision_branch_exit",
        "config": "pass_compiled_decision_branch_exit.jsonc",
        "initial": {"value.in": 4},
        "runtime_options": {"trace": "boundary", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"flow.route": "external", "value.final": 15},
        "expected_runtime_exec_order": ["start", "input", "prepare", "compute", "route", "external", "end"],
        "expected_trace_kind_counts": {"block_enter": 1, "block_exit": 1},
        "expected_trace_summary": {
            "current_node": "end",
            "exec_order": ["start", "input", "prepare", "compute", "route", "external", "end"],
            "node_runs": {"start": 1, "input": 1, "prepare": 1, "compute": 1, "route": 1, "external": 1, "end": 1},
            "step_count": 7,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "input", "prepare", "compute", "route", "loop_back", "external", "end"]],
    },
    {
        "name": "async_result_key_join",
        "config": "pass_async_result_key_join.jsonc",
        "initial": {},
        "expected_outputs": {"value.out": 12},
        "expected_trace_kind_counts": {"async_result": 1, "async_result_join": 1},
        "expected_runtime_exec_order": ["start", "seed", "add", "end"],
    },
    {
        "name": "semantic_async_result_key_unconsumed",
        "config": "pass_semantic_async_result_unconsumed.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5, "calc.c": 9, "calc.d": 4},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 21, "route.branch": "left", "calc.branch": 21, "calc.final": 17},
        "expected_absent_outputs": ["async.value"],
        "expected_trace_kind_counts": {"async_result": 1, "async_result_join": 1},
        "expected_trace_kind_absent": ["async_result_abandoned"],
        "expected_runtime_exec_order": ["start", "slow_async", "add_pair", "compare", "scale", "use_scaled", "finalize", "end"],
        "expected_trace_summary": {
            "current_node": "end",
            "edge_executions": {
                "start->slow_async": 1,
                "slow_async->add_pair": 2,
                "start->add_pair": 1,
                "start->compare": 1,
                "add_pair->scale": 1,
                "compare->use_scaled": 1,
                "scale->use_scaled": 1,
                "use_scaled->finalize": 1,
                "finalize->end": 1,
            },
            "exec_order": ["start", "slow_async", "add_pair", "compare", "scale", "use_scaled", "finalize", "end"],
            "node_runs": {"start": 1, "slow_async": 1, "add_pair": 1, "scale": 1, "compare": 1, "use_scaled": 1, "finalize": 1, "end": 1},
            "step_count": 8,
            "stop_reason": "completed",
        },
    },
    {
        "name": "compiled_fallback_mixed_graph",
        "config": "pass_async_result_key_join.jsonc",
        "initial": {},
        "runtime_options": {"trace": "boundary", "node_hooks": False, "execution": "compiled"},
        "expected_outputs": {"value.out": 12},
        "expected_trace_kind_counts": {"block_enter": 1, "block_exit": 1},
        "expected_runtime_exec_order": ["start", "seed", "add", "end"],
        "expected_trace_summary": {
            "current_node": "end",
            "edge_executions": {"start->seed": 1, "seed->add": 2},
            "exec_order": ["start", "seed", "add", "end"],
            "node_runs": {"start": 1, "seed": 1, "add": 1, "end": 1},
            "step_count": 4,
            "stop_reason": "completed",
        },
        "expected_blocks": [["add", "end"]],
    },
    {
        "name": "async_nodeset_result_key_join",
        "config": "pass_async_nodeset_result_key_join.jsonc",
        "initial": {"value.in": 3},
        "expected_outputs": {"value.out": 8},
        "expected_trace_kind_counts": {"async_result": 1, "async_result_join": 1},
        "expected_runtime_exec_order": ["start", "input", "composite", "end"],
    },
    {
        "name": "async_detached_metrics",
        "config": "pass_async_detached_metrics.jsonc",
        "initial_factory": _batch_initial,
        "expected_outputs": {"value.out": 10},
        "expected_trace_kind_counts": {"async_detached": 1, "async_detached_done": 1},
        "expected_runtime_exec_order": ["start", "metrics", "seed", "add", "end"],
    },
]


INVALID_CASES = [
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "MissingInfoNode", "type": "bad.missing_info", "expect": "NODE.CONTRACT.MISSING_NODE_INFO"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "InfoWrongTypeNode", "type": "bad.info_type", "expect": "MISSING_NODE_INFO"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "EmptyTypeKeyNode", "type": "bad.empty", "expect": "NODE_INFO_TYPE_KEY"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "NonPureNode", "type": "bad.non_pure", "expect": "NON_PURE_NODE"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "MissingContractNode", "type": "bad.missing_contract", "expect": "NODE.CONTRACT.MISSING_CONTRACT"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "DuplicateKeysNode", "type": "bad.duplicate_keys", "expect": "CONTRACT_DUPLICATE_REQUIREMENT_TYPE"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "MissingSemanticsNode", "type": "bad.missing_semantics", "expect": "CONTRACT_SEMANTICS_MISSING"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "MissingRunPureNode", "type": "bad.missing_run_pure", "expect": "NODE.CONTRACT.MISSING_RUN_PURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "ContextRunNode", "type": "bad.context_run", "expect": "NODE.CONTRACT.CONTEXT_RUN_FORBIDDEN"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "TooManyParamsNode", "type": "bad.too_many_params", "expect": "NODE.CONTRACT.RUN_PURE_SIGNATURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "VarArgsNode", "type": "bad.varargs", "expect": "NODE.CONTRACT.RUN_PURE_SIGNATURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "PublicHelperNode", "type": "bad.public_helper", "expect": "NODE.CONTRACT.PUBLIC_CALLABLE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "InitWithClientNode", "type": "bad.init_client", "expect": "NODE.CONTRACT.INIT_SIGNATURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "ResourceFieldNode", "type": "bad.resource_field", "expect": "NODE.PURITY.RESOURCE_FIELD"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "AsyncRunPureNode", "type": "bad.async_run_pure", "expect": "NODE.CONTRACT.ASYNC_RUN_PURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "GeneratorRunPureNode", "type": "bad.generator_run_pure", "expect": "NODE.PURITY.GENERATOR_RUN_PURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "OpenFileNode", "type": "bad.open", "expect": "NODE.PURITY.BANNED_CALL"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "PathReadTextNode", "type": "bad.path_read", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "OsGetenvNode", "type": "bad.getenv", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "SubprocessNode", "type": "bad.subprocess", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "SocketNode", "type": "bad.socket", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "RequestsNode", "type": "bad.requests", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "SqliteNode", "type": "bad.sqlite", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "EvalNode", "type": "bad.eval", "expect": "NODE.PURITY.BANNED_CALL"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "DynamicImportNode", "type": "bad.dynamic_import", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/coupling_cases.py", "class": "NodeImportNode", "type": "bad.node_import", "expect": "NODE_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/coupling_cases.py", "class": "DirectNodeCallNode", "type": "bad.node_call", "expect": "NODE_DIRECT_CALL"},
    {"kind": "inspect_node", "module": "illegal_nodes/coupling_cases.py", "class": "NodeInternalReadNode", "type": "bad.node_internal", "expect": "NODE_INTERNAL_READ"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "DynamicOutputKeyNode", "type": "bad.dynamic_output", "expect": "NODE.PURITY.DYNAMIC_OUTPUT_KEY"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "MissingOutputNode", "type": "bad.missing_output", "expect": "NODE.PURITY.MISSING_OUTPUT"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "ExtraOutputNode", "type": "bad.extra_output", "expect": "NODE.PURITY.UNDECLARED_OUTPUT"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "MutateInputsNode", "type": "bad.mutate_inputs", "expect": "NODE.PURITY.INPUT_MUTATION"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "MutateNestedInputNode", "type": "bad.mutate_nested", "expect": "NODE.PURITY.INPUT_MUTATION"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "UndeclaredParamNode", "type": "bad.undeclared_param", "expect": "UNDECLARED_PARAM"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "GlobalStateNode", "type": "bad.global_state", "expect": "MODULE_GLOBAL_STATE"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "SetAttrNode", "type": "bad.setattr", "expect": "NODE.PURITY.MONKEY_PATCH"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "MonkeyPatchNode", "type": "bad.monkey_patch", "expect": "NODE.PURITY.MONKEY_PATCH"},
    {"kind": "inspect_node_small_source", "module": "illegal_nodes/maintainability_cases.py", "class": "LongSourceNode", "type": "bad.long_source", "expect": "NODE.PURITY.SOURCE_TOO_LARGE"},
    {"kind": "inspect_node_warn", "module": "illegal_nodes/maintainability_cases.py", "class": "WarnCallChainNode", "type": "bad.warn_call_chain", "expect": "CALL_CHAIN_TOO_DEEP"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "DeepCallChainNode", "type": "bad.deep_call_chain", "expect": "NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "RecursiveNode", "type": "bad.recursive", "expect": "NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "IndirectRecursiveNode", "type": "bad.indirect_recursive", "expect": "NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN"},
    {"kind": "health_node", "module": "illegal_nodes/maintainability_cases.py", "class": "DeepBaseLibNode", "type": "bad.deep_base_lib", "expect": "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"},
    {"kind": "base_lib", "expect": "BASE_LIB.SIDE_EFFECT_CALL"},
    {"kind": "base_lib", "expect": "BASE_LIB.GLOBAL_STATE"},
    {"kind": "base_lib", "expect": "BASE_LIB.FORBIDDEN_PROJECT_IMPORT"},
    {"kind": "base_lib", "expect": "BASE_LIB.BANNED_IMPORT"},
    {"kind": "base_lib_chain", "expect_length_gt": 4},
    {"kind": "config", "config": "fail_schema_bad_edge.jsonc", "expect": "CONFIG.SCHEMA.EDGE_PAIR"},
    {"kind": "run", "config": "fail_unknown_node.jsonc", "expect": "NODE.TYPE.UNKNOWN"},
    {"kind": "config", "config": "fail_removed_loop_registration.jsonc", "expect": "CONFIG.LOOPS.REMOVED"},
    {"kind": "run", "config": "fail_nodeset_key_leak.jsonc", "expect": "NODESET.INTERNAL_KEY_LEAK"},
    {"kind": "run", "config": "fail_nodeset_recursion.jsonc", "expect": "NODESET.RECURSION"},
    {"kind": "config", "config": "fail_removed_boundary.jsonc", "expect": "CONFIG.BOUNDARY.REMOVED"},
    {"kind": "run", "config": "fail_planned_architecture_run.jsonc", "expect": "GRAPH.PLANNED.NODE_IN_RUN"},
    {
        "kind": "run",
        "config": "fail_planned_transparent_allow_run.jsonc",
        "expect": "GRAPH.PLANNED.NODE_IN_RUN",
        "runtime_options": {"allow_planned_stub": True},
        "absent": ["GRAPH.FLOW.ORPHAN_NODE", "GRAPH.FLOW.UNREACHABLE_FROM_START", "GRAPH.FLOW.CANNOT_REACH_END"],
    },
    {"kind": "config", "config": "fail_plugin_load.jsonc", "expect": "PLUGIN.LOAD"},
    {"kind": "run", "config": "fail_plugin_unclosed_relaxation.jsonc", "expect": "PLUGIN.POLICY.RELAXATION_REQUIRED"},
    {"kind": "run", "config": "fail_plugin_execution.jsonc", "expect": "PLUGIN.EXECUTION"},
    {"kind": "config", "config": "fail_plugin_bad_shape.jsonc", "expect": "PLUGIN.POLICY.SHAPE"},
]


@dataclass
class CaseResult:
    name: str
    status: str
    detail: str = ""
    payload: dict[str, Any] | None = None


def main() -> int:
    try:
        _prepare_environment()
        _reset_outputs()
        results = [*_run_valid_cases(), *_run_invalid_cases()]
        _write_reports(results)
    except EnvironmentError as exc:
        print(f"ENVIRONMENT ERROR: {exc}")
        return 2
    failed = [result for result in results if result.status != "PASS"]
    print(f"integration sandbox: total={len(results)} passed={len(results) - len(failed)} failed={len(failed)}")
    for result in failed:
        print(f"FAIL {result.name}: {result.detail}")
    return 1 if failed else 0


def _prepare_environment() -> None:
    KERNEL_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_kernel_link()
    for path in (KERNEL_DIR, PROJECT_DIR):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    os.chdir(SANDBOX_DIR)


def _ensure_kernel_link() -> None:
    target = SRC_KERNEL.resolve()
    if KERNEL_LINK.exists() or KERNEL_LINK.is_symlink():
        if KERNEL_LINK.resolve() == target:
            return
        raise EnvironmentError(f"kernel link exists but points elsewhere: {KERNEL_LINK}")
    try:
        os.symlink(target, KERNEL_LINK, target_is_directory=True)
        return
    except OSError as symlink_error:
        if os.name != "nt":
            raise EnvironmentError(f"cannot create kernel symlink: {symlink_error}") from symlink_error
    command = ["cmd", "/c", "mklink", "/J", str(KERNEL_LINK), str(target)]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise EnvironmentError(
            "cannot create kernel symlink or junction: "
            + (completed.stderr.strip() or completed.stdout.strip() or "unknown error")
        )


def _reset_outputs() -> None:
    for path in (REPORT_DIR, RUN_ROOT):
        if path.exists():
            shutil.rmtree(path)
    ASCII_DIR.mkdir(parents=True, exist_ok=True)
    COMPILED_BLOCK_DIR.mkdir(parents=True, exist_ok=True)
    MERMAID_DIR.mkdir(parents=True, exist_ok=True)
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)


def _run_valid_cases() -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in VALID_RUN_CASES:
        try:
            result = _run_valid_case(case)
        except Exception as exc:
            result = CaseResult(f"valid:{case['name']}", "FAIL", str(exc))
        results.append(result)
    return results


def _run_valid_case(case: dict[str, Any]) -> CaseResult:
    from vibeflow import GraphCompiler, RuntimeOptions, build_execution_plan, export_ascii_flowchart, export_mermaid, is_mermaid_svg_renderer_available, load_config_document, load_config_resources, parse_graph_config, render_mermaid_svg, resolve_effective_policy, run_checked, validate_graph_health
    from vibeflow.config_schema import collect_config_schema_findings
    from vibeflow.plugin import load_plugins_from_config

    from registry import build_node_registry

    name = str(case["name"])
    config_path = CONFIG_DIR / str(case["config"])
    document = load_config_document(config_path)
    schema_findings = collect_config_schema_findings(document.data)
    if schema_findings:
        raise AssertionError(f"schema findings: {[finding.rule_id for finding in schema_findings]}")
    plugin_registry, plugin_findings = load_plugins_from_config(document.data, base_path=config_path.parent)
    if plugin_findings:
        raise AssertionError(f"plugin findings: {[finding.rule_id for finding in plugin_findings]}")
    resources, resource_findings = load_config_resources(document.data, base_path=config_path.parent, plugin_registry=plugin_registry)
    if resource_findings:
        raise AssertionError(f"resource findings: {[finding.rule_id for finding in resource_findings]}")
    policy_result = resolve_effective_policy(document.data, config_path=config_path, explicit_policy_path=POLICY_PATH, plugin_registry=plugin_registry)
    graph = parse_graph_config(document.data)
    node_registry = build_node_registry()
    compiled = GraphCompiler().compile(graph, registry=node_registry, plugin_registry=plugin_registry)
    runtime_options = RuntimeOptions(**case["runtime_options"]) if "runtime_options" in case else None
    plan = build_execution_plan(graph, compiled, registry=node_registry, runtime_options=runtime_options, global_config=resources.global_config)
    _assert_execution_plan(case, plan)
    block_source_paths = _write_compiled_block_sources(name, plan)
    _assert_compiled_block_sources(case, plan, block_source_paths)
    health = validate_graph_health(
        graph,
        registry=node_registry,
        plugin_registry=plugin_registry,
        global_config=resources.global_config,
        purity_policy=policy_result.effective_policy.to_purity_policy(),
    )
    allowed = set(case.get("expected_status", {"PASS", "CONCERNS"}))
    if health.status not in allowed:
        raise AssertionError(f"health status {health.status}, expected {sorted(allowed)}")
    _assert_health_warnings(case, health)
    collapsed = export_mermaid(graph, compiled=compiled, registry=node_registry, health_report=health, resources=resources)
    expanded = export_mermaid(graph, compiled=compiled, registry=node_registry, expand_nodesets=True, health_report=health, resources=resources)
    ascii_collapsed = export_ascii_flowchart(graph, compiled=compiled, registry=node_registry, health_report=health)
    ascii_expanded = export_ascii_flowchart(graph, compiled=compiled, registry=node_registry, expand_nodesets=True, health_report=health)
    _assert_mermaid_contains(case, name, collapsed, expanded)
    _assert_ascii_contains(name, ascii_collapsed, ascii_expanded)
    (ASCII_DIR / f"{name}.txt").write_text(ascii_collapsed, encoding="utf-8")
    (ASCII_DIR / f"{name}.expanded.txt").write_text(ascii_expanded, encoding="utf-8")
    (MERMAID_DIR / f"{name}.mmd").write_text(collapsed, encoding="utf-8")
    (MERMAID_DIR / f"{name}.expanded.mmd").write_text(expanded, encoding="utf-8")
    if is_mermaid_svg_renderer_available():
        render_mermaid_svg(collapsed, SVG_DIR / f"{name}.svg")
        render_mermaid_svg(expanded, SVG_DIR / f"{name}.expanded.svg", max_text_size=500_000, max_edges=5_000)
    initial = case["initial_factory"]() if "initial_factory" in case else case.get("initial", {})
    hook_marker = REPORT_DIR / "plugin_hooks.jsonl"
    hook_count_before = len(hook_marker.read_text(encoding="utf-8").splitlines()) if hook_marker.exists() else 0
    run_result = run_checked(
        config_path,
        registry=node_registry,
        initial=initial,
        policy_path=POLICY_PATH,
        run_root=RUN_ROOT,
        run_id=name,
        runtime_options=runtime_options,
    )
    _assert_artifacts(run_result.run_dir)
    _assert_run_mermaid(case, run_result.run_dir)
    for key, expected in dict(case.get("expected_outputs", {})).items():
        actual = _context_value(run_result.context, str(key))
        if actual != expected:
            raise AssertionError(f"{key} expected {expected!r}, got {actual!r}")
    for key in case.get("expected_absent_outputs", ()):
        if run_result.context.exists(str(key)):
            raise AssertionError(f"{key} should be absent, got {run_result.context.get(str(key))!r}")
    for key, initial_key in case.get("expected_same_as_initial", ()):
        if _context_value(run_result.context, key) is not initial[initial_key]:
            raise AssertionError(f"{key} is not initial {initial_key}")
    for key, attr, expected in case.get("expected_object_attrs", ()):
        actual = getattr(_context_value(run_result.context, key), attr)
        if actual != expected:
            raise AssertionError(f"{key}.{attr} expected {expected!r}, got {actual!r}")
    if case.get("expect_training_metrics"):
        metrics = _context_value(run_result.context, "train.metrics")
        if metrics["model"] is not _context_value(run_result.context, "train.model_after"):
            raise AssertionError("train.metrics.model did not preserve model reference")
        if metrics["tags"] != {"sandbox", "train"} or metrics["unstable"] == metrics["unstable"]:
            raise AssertionError("train.metrics did not preserve non-JSON set/NaN values")
    if case.get("expect_batch_metrics"):
        metrics = _context_value(run_result.context, "train.metrics")
        if metrics["batch"] is not initial["train.batch"] or metrics["items"] != {2, 4} or metrics["unstable"] == metrics["unstable"]:
            raise AssertionError("batch metrics did not preserve batch reference/set/NaN values")
    if "expected_trace_kinds" in case:
        actual_kinds = [line["kind"] for line in _runtime_trace_lines(run_result.run_dir)]
        expected_kinds = list(case["expected_trace_kinds"])
        comparable_actual, comparable_expected = _comparable_trace_kinds(actual_kinds, expected_kinds)
        if comparable_actual != comparable_expected:
            raise AssertionError(f"trace kinds expected {comparable_expected!r}, got {comparable_actual!r} from raw {actual_kinds!r}")
    if "expected_trace_kind_counts" in case:
        actual_kinds = [line["kind"] for line in _runtime_trace_lines(run_result.run_dir)]
        for kind, expected in case["expected_trace_kind_counts"].items():
            if kind in {"block_enter", "block_exit"} and kind not in actual_kinds:
                continue
            actual = actual_kinds.count(kind)
            if actual != expected:
                raise AssertionError(f"trace kind {kind} expected {expected}, got {actual}")
    if "expected_trace_kind_absent" in case:
        actual_kinds = [line["kind"] for line in _runtime_trace_lines(run_result.run_dir)]
        unexpected = set(case["expected_trace_kind_absent"]) & set(actual_kinds)
        if unexpected:
            raise AssertionError(f"unexpected trace kinds present: {sorted(unexpected)}")
    if "expected_trace_summary" in case:
        summary = _runtime_trace_lines(run_result.run_dir)[-1]
        for key, expected in case["expected_trace_summary"].items():
            actual = summary.get(key)
            if key == "edge_executions":
                if not _mapping_contains(actual, expected):
                    raise AssertionError(f"runtime summary {key} expected subset {expected!r}, got {actual!r}")
            elif actual != expected:
                raise AssertionError(f"runtime summary {key} expected {expected!r}, got {summary.get(key)!r}")
    if "expected_runtime_exec_order" in case:
        actual = list(run_result.context.get("runtime.exec_order"))
        if actual != case["expected_runtime_exec_order"]:
            raise AssertionError(f"runtime exec_order expected {case['expected_runtime_exec_order']!r}, got {actual!r}")
    if "expected_hook_delta_present" in case or "expected_hook_delta_absent" in case:
        delta_lines = hook_marker.read_text(encoding="utf-8").splitlines()[hook_count_before:] if hook_marker.exists() else []
        delta_hooks = {json.loads(line)["hook"] for line in delta_lines}
        missing = set(case.get("expected_hook_delta_present", ())) - delta_hooks
        forbidden = set(case.get("expected_hook_delta_absent", ())) & delta_hooks
        if missing:
            raise AssertionError(f"missing expected hook delta: {sorted(missing)}")
        if forbidden:
            raise AssertionError(f"unexpected hook delta: {sorted(forbidden)}")
    return CaseResult(
        f"valid:{name}",
        "PASS",
        payload={
            "compiled_blocks": [list(block.nodes) for block in plan.blocks],
            "compiled_block_sources": block_source_paths,
            "health": health.status,
            "run_dir": str(run_result.run_dir),
        },
    )


def _write_compiled_block_sources(name: str, plan) -> list[str]:
    paths: list[str] = []
    for index, block in enumerate(plan.blocks):
        path = COMPILED_BLOCK_DIR / f"{name}.block{index}.{block.entry}.py"
        header = [
            f"# generated compiled block for integration sandbox case: {name}",
            f"# block: {block.name}",
            f"# entry: {block.entry}",
            f"# nodes: {', '.join(block.nodes)}",
            "",
        ]
        path.write_text("\n".join(header) + block.source + "\n", encoding="utf-8")
        paths.append(str(path))
    return paths


def _assert_compiled_block_sources(case: dict[str, Any], plan, source_paths: list[str]) -> None:
    if "expected_block_source_contains" not in case and "expected_block_source_absent" not in case:
        return
    if not plan.blocks:
        return
    missing_files = [path for path in source_paths if not Path(path).exists()]
    if missing_files:
        raise AssertionError(f"missing compiled block source files: {missing_files}")
    source = "\n".join(block.source for block in plan.blocks)
    for expected in case.get("expected_block_source_contains", ()):
        if str(expected) not in source:
            raise AssertionError(f"compiled block source missing {expected!r}")
    for forbidden in case.get("expected_block_source_absent", ()):
        if str(forbidden) in source:
            raise AssertionError(f"compiled block source unexpectedly contains {forbidden!r}")


def _runtime_trace_lines(run_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]


def _comparable_trace_kinds(actual: list[str], expected: list[str]) -> tuple[list[str], list[str]]:
    actual_compare = list(actual)
    expected_compare = list(expected)
    if "type_resolve" not in expected_compare:
        actual_compare = [kind for kind in actual_compare if kind != "type_resolve"]
    if not ({"block_enter", "block_exit"} & set(actual_compare)):
        expected_compare = [kind for kind in expected_compare if kind not in {"block_enter", "block_exit"}]
    return actual_compare, expected_compare


def _mapping_contains(actual: Any, expected: Any) -> bool:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return actual == expected
    for key, expected_value in expected.items():
        if actual.get(key) != expected_value:
            return False
    return True


def _assert_execution_plan(case: dict[str, Any], plan) -> None:
    for node_name, expected_params in dict(case.get("expected_plan_params", {})).items():
        params = plan.frame(str(node_name)).params
        for key, expected in expected_params.items():
            if params.get(key) != expected:
                raise AssertionError(f"plan {node_name}.{key} expected {expected!r}, got {params.get(key)!r}")
    for path, expected_params in dict(case.get("expected_nodeset_subplan_params", {})).items():
        node_name, child_name = str(path).split(".", 1)
        subplan = plan.frame(node_name).subplan
        if subplan is None:
            raise AssertionError(f"plan node {node_name} missing subplan")
        params = subplan.frame(child_name).params
        for key, expected in expected_params.items():
            if params.get(key) != expected:
                raise AssertionError(f"subplan {path}.{key} expected {expected!r}, got {params.get(key)!r}")
    for node_name, expected_nodes in dict(case.get("expected_nodeset_subplan_nodes", {})).items():
        subplan = plan.frame(str(node_name)).subplan
        if subplan is None:
            raise AssertionError(f"plan node {node_name} missing subplan")
        if list(subplan.order) != list(expected_nodes):
            raise AssertionError(f"subplan {node_name} order expected {expected_nodes!r}, got {list(subplan.order)!r}")
    for node_name, expected_exports in dict(case.get("expected_nodeset_exports", {})).items():
        frame = plan.frame(str(node_name))
        actual_exports = [provider.key for provider in frame.exports]
        if actual_exports != list(expected_exports):
            raise AssertionError(f"nodeset {node_name} exports expected {expected_exports!r}, got {actual_exports!r}")
    if "expected_blocks" in case:
        blocks = [list(block.nodes) for block in plan.blocks]
        if blocks and blocks != case["expected_blocks"]:
            raise AssertionError(f"compiled blocks expected {case['expected_blocks']!r}, got {blocks!r}")


def _context_value(context, key: str):
    item = context.get(key)
    if isinstance(item, dict) and {"key", "type", "value", "source_node"} <= set(item):
        return item["value"]
    return item


def _assert_mermaid_contains(case: dict[str, Any], name: str, collapsed: str, expanded: str) -> None:
    if "flowchart TD" not in collapsed:
        raise AssertionError("collapsed Mermaid missing flowchart TD")
    if "flowchart TD" not in expanded:
        raise AssertionError("expanded Mermaid missing flowchart TD")
    if "nodeset" in name and "subgraph" not in expanded:
        raise AssertionError("expanded nodeset Mermaid missing subgraph")
    expected = tuple(str(value) for value in case.get("expected_mermaid_contains", ()))
    missing = [value for value in expected if value not in collapsed and value not in expanded]
    if missing:
        raise AssertionError(f"Mermaid missing expected content: {missing}")


def _assert_health_warnings(case: dict[str, Any], health) -> None:
    expected = set(case.get("expected_health_warnings", ()))
    if not expected:
        return
    actual = {finding.rule_id for finding in health.warnings}
    missing = expected - actual
    if missing:
        raise AssertionError(f"missing expected health warnings: {sorted(missing)}")


def _assert_run_mermaid(case: dict[str, Any], run_dir: Path) -> None:
    expected = tuple(str(value) for value in case.get("expected_run_mermaid_contains", ()))
    if not expected:
        return
    text = (run_dir / "graph.mmd").read_text(encoding="utf-8")
    missing = [value for value in expected if value not in text]
    if missing:
        raise AssertionError(f"run Mermaid missing expected content: {missing}")


def _assert_ascii_contains(name: str, collapsed: str, expanded: str) -> None:
    if "TOPOLOGY FLOWCHART" not in collapsed:
        raise AssertionError("collapsed ASCII missing header")
    if "Flow edges:" not in collapsed:
        raise AssertionError("collapsed ASCII missing flow edges")
    if "nodeset" in name and "nodeset " not in expanded:
        raise AssertionError("expanded nodeset ASCII missing nodeset section")


def _assert_artifacts(run_dir: Path) -> None:
    from vibeflow import is_mermaid_svg_renderer_available

    required = (
        "health_report.json",
        "compiled_graph.json",
        "graph.txt",
        "graph.mmd",
        "runtime_trace.jsonl",
        "effective_policy.json",
        "input_summary.json",
        "output_summary.json",
    )
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise AssertionError(f"missing run artifacts: {missing}")
    if is_mermaid_svg_renderer_available():
        svg = run_dir / "graph.svg"
        if not svg.exists() or "<svg" not in svg.read_text(encoding="utf-8"):
            raise AssertionError("missing rendered SVG artifact")


def _run_invalid_cases() -> list[CaseResult]:
    results: list[CaseResult] = []
    base_lib_report = None
    for index, case in enumerate(INVALID_CASES):
        name = f"invalid:{case['kind']}:{case.get('class', case.get('config', case.get('expect', index)))}"
        try:
            result, base_lib_report = _run_invalid_case(case, base_lib_report)
        except Exception as exc:
            result = CaseResult(name, "FAIL", str(exc))
        results.append(result)
    return results


def _run_invalid_case(case: dict[str, Any], base_lib_report):
    kind = case["kind"]
    if kind.startswith("inspect_node"):
        return _inspect_invalid_node(case, kind), base_lib_report
    if kind == "runtime_node":
        return _runtime_invalid_node(case), base_lib_report
    if kind == "health_node":
        return _health_invalid_node(case), base_lib_report
    if kind == "base_lib":
        report = base_lib_report or _bad_base_lib_report()
        _assert_report_has_rule(report.to_dict()["findings"], str(case["expect"]))
        return CaseResult(f"invalid:base_lib:{case['expect']}", "PASS"), report
    if kind == "base_lib_chain":
        report = base_lib_report or _bad_base_lib_report()
        from vibeflow import summarize_base_lib_dependency_chain

        summary = summarize_base_lib_dependency_chain(("bad_base_lib.deep_chain_a",), report)
        if summary.longest_chain_length <= int(case["expect_length_gt"]):
            raise AssertionError(f"expected deep chain > {case['expect_length_gt']}, got {summary.longest_chain_length}")
        return CaseResult("invalid:base_lib_chain", "PASS", payload=summary.to_dict()), report
    if kind == "config":
        return _invalid_config(case), base_lib_report
    if kind == "run":
        return _invalid_run(case), base_lib_report
    raise AssertionError(f"unknown invalid case kind: {kind}")


def _inspect_invalid_node(case: dict[str, Any], kind: str) -> CaseResult:
    from vibeflow.purity import validate_node_class
    from vibeflow.purity_types import PurityPolicy

    cls = _load_class(PROJECT_DIR / str(case["module"]), str(case["class"]))
    policy = PurityPolicy(max_source_lines=500, warn_source_lines=None, allowed_base_lib_modules=("base_lib",))
    if kind == "inspect_node_small_source":
        policy = PurityPolicy(max_source_lines=10, allowed_base_lib_modules=("base_lib",))
    elif kind == "inspect_node_warn":
        policy = PurityPolicy(max_source_lines=500, warn_call_chain_length=4, max_call_chain_length=99, allowed_base_lib_modules=("base_lib",))
    violations = validate_node_class(
        cls,
        policy=policy,
        expected_type=str(case["type"]),
        known_node_class_names=("ConstantNode",),
        known_node_modules=("nodes.legal_math_nodes",),
        scan_module=True,
    )
    _assert_violations_have_rule(violations, str(case["expect"]))
    return CaseResult(f"invalid:inspect_node:{case['class']}", "PASS", payload={"rules": [item.rule_id for item in violations]})


def _runtime_invalid_node(case: dict[str, Any]) -> CaseResult:
    from vibeflow import DataProvider, DataRequirement, EdgeSpec, GraphConfig, NodeContract, NodeInfo, NodeSpec, PipelineRuntime
    from vibeflow.registry import NodeRegistry

    class RuntimeStartNode:
        NODE_INFO = NodeInfo("sandbox.runtime_start", "Runtime Start", "sandbox", "runtime test start", "0.1.0", "terminal")
        CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}},))

        def run_pure(self, inputs, params):
            return {}

    class RuntimeEndNode:
        NODE_INFO = NodeInfo("sandbox.runtime_end", "Runtime End", "sandbox", "runtime test end", "0.1.0", "terminal")
        CONTRACT = NodeContract(requires=(DataRequirement("bad.out", "exactly_one"),), input_semantics={"bad.out": ("bad output",)}, examples=({"inputs": {"bad.out": 1}, "params": {}},))

        def run_pure(self, inputs, params):
            return {}

    cls = _load_class(PROJECT_DIR / str(case["module"]), str(case["class"]))
    registry = NodeRegistry()
    registry.register("sandbox.runtime_start", RuntimeStartNode, config_schema={}, config_defaults={})
    registry.register("sandbox.runtime_end", RuntimeEndNode, config_schema={}, config_defaults={})
    registry.register(str(case["type"]), cls, config_schema={}, config_defaults={})
    graph = GraphConfig(
        nodes=(
            NodeSpec(name="start", node_type="sandbox.runtime_start"),
            NodeSpec(name="bad", node_type=str(case["type"]), provides=(DataProvider("bad.out", "bad.out"),)),
            NodeSpec(name="end", node_type="sandbox.runtime_end", requires=(DataRequirement("bad.out", "exactly_one"),)),
        ),
        edges=(EdgeSpec("start", "bad"), EdgeSpec("bad", "end")),
    )
    try:
        PipelineRuntime(graph, registry=registry).run({})
    except Exception as exc:
        if str(case["expect"]) not in str(exc):
            raise AssertionError(f"runtime error did not include {case['expect']}: {exc}") from exc
        return CaseResult(f"invalid:runtime_node:{case['class']}", "PASS", str(exc))
    raise AssertionError("runtime node was not rejected")


def _health_invalid_node(case: dict[str, Any]) -> CaseResult:
    from vibeflow import DataProvider, GraphConfig, NodeSpec, validate_graph_health
    from vibeflow.purity_types import PurityPolicy
    from vibeflow.registry import NodeRegistry

    cls = _load_class(PROJECT_DIR / str(case["module"]), str(case["class"]))
    registry = NodeRegistry()
    registry.register(str(case["type"]), cls, config_schema={}, config_defaults={})
    graph = GraphConfig(nodes=(NodeSpec(name="bad", node_type=str(case["type"]), provides=(DataProvider("bad.out", "bad.out"),)),))
    report = validate_graph_health(
        graph,
        registry=registry,
        purity_policy=PurityPolicy(
            allowed_base_lib_paths=(str(PROJECT_DIR / "base_lib"),),
            allowed_base_lib_modules=("base_lib",),
            warn_dependency_chain_length=2,
            max_dependency_chain_length=4,
        ),
    )
    _assert_report_has_rule([item.to_dict() for item in (*report.errors, *report.warnings)], str(case["expect"]))
    return CaseResult(f"invalid:health_node:{case['class']}", "PASS", payload=report.to_dict())


def _bad_base_lib_report():
    from vibeflow import scan_base_lib
    from vibeflow.purity_types import PurityPolicy

    return scan_base_lib(
        PROJECT_DIR,
        policy=PurityPolicy(
            allowed_base_lib_paths=(str(PROJECT_DIR / "bad_base_lib"),),
            max_source_lines=20,
            max_functions=3,
            max_branches=4,
            banned_import_roots=("subprocess",),
        ),
    )


def _invalid_config(case: dict[str, Any]) -> CaseResult:
    from vibeflow.cli_config import validate_config_path

    report = validate_config_path(CONFIG_DIR / str(case["config"]), policy_path=POLICY_PATH)
    if report.status not in {"FAIL", "ERROR"}:
        raise AssertionError(f"config case was not rejected: {report.status}")
    _assert_report_has_rule([item.to_dict() for item in (*report.errors, *report.warnings)], str(case["expect"]))
    return CaseResult(f"invalid:config:{case['config']}", "PASS", payload=report.to_dict())


def _invalid_run(case: dict[str, Any]) -> CaseResult:
    from registry import build_node_registry
    from vibeflow import CheckedRunError, RuntimeOptions, run_checked

    try:
        runtime_options = RuntimeOptions(**case["runtime_options"]) if "runtime_options" in case else None
        run_checked(
            CONFIG_DIR / str(case["config"]),
            registry=build_node_registry(),
            initial={"value.in": 0, "io.result": 1},
            policy_path=POLICY_PATH,
            run_root=RUN_ROOT,
            run_id=f"expected_fail_{Path(str(case['config'])).stem}",
            runtime_options=runtime_options,
        )
    except CheckedRunError as exc:
        report = exc.result.health
        if report.status not in {"FAIL", "ERROR"}:
            raise AssertionError(f"run case status was {report.status}")
        findings = [item.to_dict() for item in (*report.errors, *report.warnings)]
        _assert_report_has_rule(findings, str(case["expect"]))
        present = {str(item.get("rule_id", "")) for item in findings}
        forbidden = set(case.get("absent", ())) & present
        if forbidden:
            raise AssertionError(f"run case had forbidden rules: {sorted(forbidden)}")
        return CaseResult(f"invalid:run:{case['config']}", "PASS", payload=report.to_dict())
    raise AssertionError("run case was not rejected")


def _load_class(path: Path, class_name: str):
    module_name = f"_sandbox_{path.stem}_{class_name}_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def _assert_violations_have_rule(violations, expected: str) -> None:
    payloads = [
        {
            "rule_id": item.rule_id,
            "code": item.code,
            "message": item.message,
            "severity": item.severity,
            "failure_layer": item.failure_layer,
            "details": dict(item.details),
        }
        for item in violations
    ]
    _assert_report_has_rule(payloads, expected)


def _assert_report_has_rule(items: list[dict[str, Any]], expected: str) -> None:
    for item in items:
        rule_id = str(item.get("rule_id", ""))
        code = str(item.get("code", item.get("details", {}).get("legacy_code", "")))
        message = str(item.get("message", ""))
        if expected == rule_id or expected == code or expected in rule_id or expected in code or expected in message:
            return
    raise AssertionError(f"expected {expected}, got {[item.get('rule_id', item.get('code')) for item in items]}")


def _write_reports(results: list[CaseResult]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item.status == "PASS"),
        "failed": sum(1 for item in results if item.status != "PASS"),
        "results": [
            {"name": item.name, "status": item.status, "detail": item.detail, "payload": item.payload or {}}
            for item in results
        ],
    }
    (REPORT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# Integration Sandbox Summary",
        "",
        f"- total: {summary['total']}",
        f"- passed: {summary['passed']}",
        f"- failed: {summary['failed']}",
        "",
    ]
    for item in results:
        detail = f" - {item.detail}" if item.detail else ""
        lines.append(f"- {item.status}: {item.name}{detail}")
    (REPORT_DIR / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
