from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _find_repository_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "src" / "vibeflow").is_dir()
        ):
            return candidate
    raise EnvironmentError(
        "cannot locate the VibeFlow repository root; expected pyproject.toml "
        "and src/vibeflow in one parent directory"
    )


SANDBOX_DIR = Path(__file__).resolve().parent
REPO_ROOT = _find_repository_root(SANDBOX_DIR)
SOURCE_ROOT = REPO_ROOT / "src"
FIXTURE_PROJECT_DIR = SANDBOX_DIR / "project"
FIXTURE_WORKSPACE_PATH = SANDBOX_DIR / "vibeflow_config.jsonc"
WORK_ROOT = SANDBOX_DIR
PROJECT_DIR = FIXTURE_PROJECT_DIR
CONFIG_DIR = PROJECT_DIR / "configs"
REPORT_DIR = WORK_ROOT / "reports"
ASCII_DIR = REPORT_DIR / "ascii"
MERMAID_DIR = REPORT_DIR / "mermaid"
SVG_DIR = REPORT_DIR / "svg"
COMPILED_BLOCK_DIR = REPORT_DIR / "compiled_blocks"
RUN_ROOT = WORK_ROOT / "runs"
POLICY_PATH = PROJECT_DIR / "kernel_policy.jsonc"
WORKSPACE_PATH = FIXTURE_WORKSPACE_PATH
REVIEW_ARCHITECTURE_DIR = PROJECT_DIR / "review_artifacts"
REVIEW_ARCHITECTURE_PATH = REVIEW_ARCHITECTURE_DIR / "ARCHITECTURE.jsonc"
REVIEW_DIR = REPORT_DIR / "review"
EXTERNAL_DEDUP_REVIEW_CONFIG_PATH = CONFIG_DIR / "review_external_nodeset_dedup.jsonc"


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


def _callback_initial() -> dict[str, Any]:
    return {"callback.in": lambda: 23}


COMPILED_SOURCE_FULL_REQUIRED = ("runtime._run_compiled_frame",)
COMPILED_SOURCE_FAST_REQUIRED = ("runtime._run_compiled_frame",)
COMPILED_SOURCE_FORBIDDEN = ("_run_node(",)
COMPILED_SOURCE_FAST_FORBIDDEN = ("_run_node(",)


VALID_RUN_CASES = [
    {"name": "free_nodes", "config": "pass_free_nodes.jsonc", "initial": {}, "expected_status": {"PASS", "CONCERNS"}},
    {"name": "io_data_store", "config": "pass_io_data_store.jsonc", "initial": {"io.result": 20}},
    {"name": "comprehensive_flowchart", "config": "pass_comprehensive_flowchart.jsonc", "initial": {"value.in": 3}, "expected_outputs": {"io.output": "final=13;request=13"}},
    {
        "name": "global_state_execution_lock",
        "config": "pass_global_state_execution_lock.jsonc",
        "initial": {},
        "expected_outputs": {"value.out": 1},
        "expected_mermaid_contains": (
            "state@{ shape: cloud",
            "effect_scope: global_state",
            "execution_lock: sandbox.global-state.serial",
        ),
        "expected_run_mermaid_contains": (
            "state@{ shape: cloud",
            "effect_scope: global_state",
            "execution_lock: sandbox.global-state.serial",
        ),
        "expected_trace_kind_counts": {
            "lock_wait": 2,
            "lock_acquired": 2,
            "lock_released": 2,
            "global_state_enter": 1,
            "global_state_exit": 1,
        },
        "reset_global_state_probe": True,
        "expected_workflow_global_state": True,
        "expected_svg_cloud_nodes": ("state",),
        "expected_global_state_trace": True,
    },
    {
        "name": "ordinary_callback_warning",
        "config": "pass_callback_warning.jsonc",
        "initial_factory": _callback_initial,
        "expected_outputs": {"value.out": 23},
        "expected_health_warnings": [],
    },
    {
        "name": "training_object_flow",
        "config": "pass_training_object_flow.jsonc",
        "initial_factory": _training_initial,
        "expected_outputs": {"train.loss": 6.0, "train.grad": 0.6, "train.step_report": {"steps": 1, "weight": 0.7}},
        "expected_same_as_initial": [("train.model_after", "train.model"), ("train.optimizer_after", "train.optimizer")],
        "expected_object_attrs": [("train.model_after", "weight", 0.7), ("train.optimizer_after", "steps", 1)],
        "expect_training_metrics": True,
        "expected_health_warnings": [
            "GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED",
        ],
        "expected_mermaid_contains": (
            "forward@{ shape: cloud",
            "execution_lock: none",
        ),
        "expected_svg_cloud_nodes": ("forward", "backward", "step"),
    },
    {
        "name": "training_non_json_metrics",
        "config": "pass_training_non_json_metrics.jsonc",
        "initial_factory": _batch_initial,
        "expect_batch_metrics": True,
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
            "resource_plugins",
            "Sandbox Value Shift",
            "config: shift",
        ],
        "expected_mermaid_not_contains": [
            "base_lib.future_arithmetic",
            "future_value_plugin",
            "planned runtime value hook",
        ],
        "expected_run_mermaid_contains": [
            "Sandbox Arithmetic",
            "Sandbox Value Shift",
        ],
        "expected_run_mermaid_not_contains": [
            "base_lib.future_arithmetic",
            "future_value_plugin",
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
            "stubs/runtime_control_stub.py",
        ],
        "expected_run_mermaid_contains": [
            "planned python_stub",
            "stubs/runtime_control_stub.py",
        ],
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
        "expected_blocks": [["start", "input", "prepare", "compute", "route", "external", "end", "again_end"]],
    },
    {
        "name": "async_result_key_join",
        "config": "pass_async_result_key_join.jsonc",
        "initial": {},
        "expected_outputs": {"value.out": 12},
        "expected_trace_kind_counts": {"async_result": 1, "async_result_join": 1},
        "expected_runtime_exec_order": ["start", "seed", "add", "end"],
        "expected_portable_execution": {
            "seed": ["immediate", "deferred", "thread"],
            "add": ["immediate", "inline", "current"],
        },
        "expected_portable_tasks": [
            {
                "node_id": "seed",
                "schedule": "deferred",
                "executor": "thread",
                "result_key": "value.in",
            }
        ],
    },
    {
        "name": "semantic_async_result_key_unconsumed",
        "config": "pass_semantic_async_result_unconsumed.jsonc",
        "initial": {"calc.a": 2, "calc.b": 5, "calc.c": 9, "calc.d": 4},
        "expected_outputs": {"calc.sum": 7, "calc.scaled": 21, "route.branch": "left", "calc.branch": 21, "calc.final": 17},
        "expected_absent_outputs": ["async.value"],
        "expected_trace_kind_counts": {"async_result": 1, "async_result_join": 1},
        "expected_trace_kind_absent": ["async_result_abandoned"],
        "expected_runtime_exec_order": ["start", "add_pair", "compare", "slow_async", "scale", "use_scaled", "finalize", "end"],
        "expected_trace_summary": {
            "current_node": "end",
            "edge_executions": {
                "start->slow_async": 1,
                "slow_async->add_pair": 1,
                "start->add_pair": 1,
                "start->compare": 1,
                "add_pair->scale": 1,
                "compare->use_scaled": 1,
                "scale->use_scaled": 1,
                "use_scaled->finalize": 1,
                "finalize->end": 1,
            },
            "exec_order": ["start", "add_pair", "compare", "slow_async", "scale", "use_scaled", "finalize", "end"],
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
            "edge_executions": {"start->seed": 1, "seed->add": 1},
            "exec_order": ["start", "seed", "add", "end"],
            "node_runs": {"start": 1, "seed": 1, "add": 1, "end": 1},
            "step_count": 4,
            "stop_reason": "completed",
        },
        "expected_blocks": [["start", "seed", "add", "end"]],
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
        "expected_runtime_exec_order": ["start", "seed", "metrics", "add", "end"],
        "expected_portable_execution": {
            "metrics": ["immediate", "detached", "thread"],
            "seed": ["immediate", "inline", "current"],
        },
        "expected_portable_tasks": [
            {
                "node_id": "metrics",
                "schedule": "detached",
                "executor": "thread",
                "result_key": "",
            }
        ],
    },
    {
        "name": "mainline_async_nodeset_side_task",
        "config": "pass_mainline_async_nodeset_side_task.jsonc",
        "initial": {},
        "expected_outputs": {"value.out": 10},
        "expected_trace_kind_counts": {"async_detached": 1, "async_detached_done": 1},
        "expected_runtime_exec_order": ["start", "seed", "side_task", "main_add", "end"],
    },
]


INVALID_CASES = [
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "MissingInfoNode", "type": "bad.missing_info", "expect": "type_key"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "InfoWrongTypeNode", "type": "bad.info_type", "expect": "display_name"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "EmptyTypeKeyNode", "type": "bad.empty", "expect": "type_key"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "MissingContractNode", "type": "bad.missing_contract", "expect": "contract"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "DuplicateKeysNode", "type": "bad.duplicate_keys", "expect": "duplicate"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "MissingSemanticsNode", "type": "bad.missing_semantics", "expect": "semantics"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "MissingRunPureNode", "type": "bad.missing_run_pure", "expect": "NODE.CONTRACT.MISSING_RUN_PURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "ContextRunNode", "type": "bad.context_run", "expect": "NODE.CONTRACT.CONTEXT_RUN_FORBIDDEN"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "TooManyParamsNode", "type": "bad.too_many_params", "expect": "NODE.CONTRACT.RUN_PURE_SIGNATURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "VarArgsNode", "type": "bad.varargs", "expect": "NODE.CONTRACT.RUN_PURE_SIGNATURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "PublicHelperNode", "type": "bad.public_helper", "expect": "NODE.CONTRACT.PUBLIC_CALLABLE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "InitWithClientNode", "type": "bad.init_client", "expect": "NODE.CONTRACT.INIT_SIGNATURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "ResourceFieldNode", "type": "bad.resource_field", "allowed": True, "retired_expect": "NODE.PURITY.RESOURCE_FIELD"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "AsyncRunPureNode", "type": "bad.async_run_pure", "expect": "NODE.CONTRACT.ASYNC_RUN_PURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "GeneratorRunPureNode", "type": "bad.generator_run_pure", "expect": "NODE.CONTRACT.GENERATOR_RUN_PURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "OpenFileNode", "type": "bad.open", "expect": "NODE.EFFECT.CALL_FORBIDDEN"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "PathReadTextNode", "type": "bad.path_read", "expect": "NODE.EFFECT.IMPORT_FORBIDDEN"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "OsGetenvNode", "type": "bad.getenv", "expect": "NODE.EFFECT.IMPORT_FORBIDDEN"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "SubprocessNode", "type": "bad.subprocess", "expect": "NODE.EFFECT.IMPORT_FORBIDDEN"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "SocketNode", "type": "bad.socket", "expect": "NODE.EFFECT.IMPORT_FORBIDDEN"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "RequestsNode", "type": "bad.requests", "expect": "NODE.EFFECT.IMPORT_FORBIDDEN"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "SqliteNode", "type": "bad.sqlite", "expect": "NODE.EFFECT.IMPORT_FORBIDDEN"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "EvalNode", "type": "bad.eval", "allowed": True, "retired_expect": "NODE.PURITY.BANNED_CALL"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "DynamicImportNode", "type": "bad.dynamic_import", "allowed": True, "retired_expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/coupling_cases.py", "class": "NodeImportNode", "type": "bad.node_import", "expect": "NODE_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/coupling_cases.py", "class": "DirectNodeCallNode", "type": "bad.node_call", "expect": "NODE_DIRECT_CALL"},
    {"kind": "inspect_node", "module": "illegal_nodes/coupling_cases.py", "class": "NodeInternalReadNode", "type": "bad.node_internal", "expect": "NODE_INTERNAL_READ"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "DynamicOutputKeyNode", "type": "bad.dynamic_output", "allowed": True, "retired_expect": "NODE.PURITY.DYNAMIC_OUTPUT_KEY"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "MissingOutputNode", "type": "bad.missing_output", "allowed": True, "retired_expect": "NODE.PURITY.MISSING_OUTPUT"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "ExtraOutputNode", "type": "bad.extra_output", "allowed": True, "retired_expect": "NODE.PURITY.UNDECLARED_OUTPUT"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "MutateInputsNode", "type": "bad.mutate_inputs", "expect": "NODE.PURITY.INPUT_MUTATION"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "MutateNestedInputNode", "type": "bad.mutate_nested", "expect": "NODE.PURITY.INPUT_MUTATION"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "GlobalStateNode", "type": "bad.global_state", "expect": "NODE.IMPORT.SIDE_EFFECT"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "SetAttrNode", "type": "bad.setattr", "remaining_expect": "NODE.IMPORT.SIDE_EFFECT", "retired_expect": "NODE.PURITY.MONKEY_PATCH"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "MonkeyPatchNode", "type": "bad.monkey_patch", "remaining_expect": "NODE.IMPORT.SIDE_EFFECT", "retired_expect": "NODE.PURITY.MONKEY_PATCH"},
    {"kind": "inspect_node_small_source", "module": "illegal_nodes/maintainability_cases.py", "class": "LongSourceNode", "type": "bad.long_source", "expect": "NODE.PURITY.SOURCE_TOO_LARGE"},
    {"kind": "inspect_node_warn", "module": "illegal_nodes/maintainability_cases.py", "class": "WarnCallChainNode", "type": "bad.warn_call_chain", "expect": "CALL_CHAIN_TOO_DEEP"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "DeepCallChainNode", "type": "bad.deep_call_chain", "expect": "NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "RecursiveNode", "type": "bad.recursive", "remaining_expect": "NODE.IMPORT.SIDE_EFFECT", "retired_expect": "NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "IndirectRecursiveNode", "type": "bad.indirect_recursive", "remaining_expect": "NODE.IMPORT.SIDE_EFFECT", "retired_expect": "NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN"},
    {"kind": "health_node", "module": "illegal_nodes/deep_dependency_node.py", "class": "DeepBaseLibNode", "type": "bad.deep_base_lib", "expect": "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"},
    {"kind": "base_lib", "expect": "BASE_LIB.SIDE_EFFECT_CALL"},
    {"kind": "base_lib", "expect": "BASE_LIB.GLOBAL_STATE"},
    {"kind": "base_lib", "expect": "VF_IMPORT_LAYER"},
    {"kind": "base_lib", "expect": "BASE_LIB.BANNED_IMPORT"},
    {"kind": "base_lib_chain", "expect_length_gt": 4},
    {"kind": "config", "config": "fail_schema_bad_edge.jsonc", "expect": "CONFIG.SCHEMA.EDGE_PAIR"},
    {
        "kind": "config",
        "config": "fail_async_result_key_missing.jsonc",
        "expect": "GRAPH.ASYNC.RESULT_KEY_CONTRACT",
    },
    {"kind": "run", "config": "fail_unknown_node.jsonc", "expect": "NODE.TYPE.UNKNOWN"},
    {"kind": "config", "config": "fail_removed_loop_registration.jsonc", "expect": "CONFIG.LOOPS.REMOVED"},
    {"kind": "run", "config": "fail_nodeset_key_leak.jsonc", "expect": "NODESET.PROVIDES.UNKNOWN_KEY"},
    {"kind": "run", "config": "fail_nodeset_recursion.jsonc", "expect": "NODESET.RECURSION"},
    {"kind": "config", "config": "fail_removed_boundary.jsonc", "expect": "CONFIG.BOUNDARY.REMOVED"},
    {"kind": "run", "config": "fail_decision_cycle_forbidden.jsonc", "expect": "GRAPH.CYCLE.FORBIDDEN"},
    {"kind": "run", "config": "fail_planned_architecture_run.jsonc", "expect": "GRAPH.PLANNED.NODE_IN_RUN"},
    {
        "kind": "run",
        "config": "fail_planned_transparent_allow_run.jsonc",
        "expect": "GRAPH.PLANNED.NODE_IN_RUN",
        "runtime_options": {"allow_planned_stub": True},
        "absent": ["GRAPH.FLOW.ORPHAN_NODE", "GRAPH.FLOW.UNREACHABLE_FROM_START", "GRAPH.FLOW.CANNOT_REACH_END"],
    },
    {"kind": "config", "config": "fail_plugin_load.jsonc", "expect": "PLUGIN.DECLARATION.LOAD"},
    {"kind": "run", "config": "fail_rule_missing_record.jsonc", "expect": "RULE.EXECUTION"},
    {"kind": "run", "config": "fail_rule_execution.jsonc", "expect": "RULE.EXECUTION"},
    {"kind": "config", "config": "fail_rule_bad_shape.jsonc", "expect": "RULE.EXECUTION"},
    {"kind": "runtime_run", "config": "fail_loop_max_iterations.jsonc", "initial": {"loop.current": 1}, "expect": "max_iterations=2"},
    {"kind": "concerns", "config": "concern_mainline_unjoined_sync_fanout.jsonc", "expect": "GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT", "details": ["owner", "source", "target", "branch_nodes", "branch_edges", "suggested_fixes"]},
    {"kind": "run", "config": "fail_mainline_decision_branch_dead_end.jsonc", "expect": "GRAPH.MAINLINE.DECISION_BRANCH_DEAD_END"},
    {"kind": "run", "config": "fail_safe_or_join_ambiguous_unconditional.jsonc", "expect": "GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL"},
    {"kind": "run", "config": "fail_safe_or_join_multiple_exactly_one.jsonc", "expect": "GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS"},
]


@dataclass
class CaseResult:
    name: str
    status: str
    detail: str = ""
    payload: dict[str, Any] | None = None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the VibeFlow Python integration sandbox."
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="preserve reports and run directories under .artifacts",
    )
    args = parser.parse_args()
    if args.keep_artifacts:
        artifact_root = SANDBOX_DIR / ".artifacts"
        if artifact_root.exists():
            shutil.rmtree(artifact_root)
        artifact_root.mkdir(parents=True)
        result = _run_sandbox(artifact_root)
        print(f"sandbox artifacts: {artifact_root}")
        return result
    with tempfile.TemporaryDirectory(prefix="vibeflow-python-sandbox-") as raw:
        return _run_sandbox(Path(raw))


def _run_sandbox(work_root: Path) -> int:
    try:
        _configure_runtime(work_root)
        _prepare_environment()
        _reset_outputs()
        results = [
            _run_workspace_quality_case(),
            _run_comprehensive_math_case(),
            _run_rule_selection_case(),
            *_run_review_cases(),
            *(_run_addition_case(name) for name in ("cli_addition", "object_addition", "plugin_addition", "piecewise_math", "workflow_math")),
            *_run_execution_model_cases(),
            *_run_source_preflight_cases(),
            *_run_global_state_cases(),
            *_run_valid_cases(),
            *_run_invalid_cases(),
        ]
        results.append(_run_published_diagram_audit_case(results))
        _write_reports(results)
    except EnvironmentError as exc:
        print(f"ENVIRONMENT ERROR: {exc}")
        return 2
    failed = [result for result in results if result.status != "PASS"]
    print(f"integration sandbox: total={len(results)} passed={len(results) - len(failed)} failed={len(failed)}")
    for result in failed:
        print(f"FAIL {result.name}: {result.detail}")
    return 1 if failed else 0


def _run_rule_selection_case() -> CaseResult:
    work = WORK_ROOT / "rule_selection"
    completed = subprocess.run(
        [sys.executable, str(SANDBOX_DIR.parent / "rule_selection/run_all.py"), "--work-dir", str(work)],
        env={**os.environ, "PYTHONPATH": str(SOURCE_ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True,
    )
    if completed.returncode:
        return CaseResult("rule_selection", "FAIL", completed.stdout + completed.stderr)
    payload = json.loads((work / "report.json").read_text())
    return CaseResult("rule_selection", "PASS", completed.stdout.strip(), payload)


def _run_comprehensive_math_case() -> CaseResult:
    work = WORK_ROOT / "comprehensive_math"
    completed = subprocess.run(
        [sys.executable, str(SANDBOX_DIR.parent / "comprehensive_math/run_all.py"),
         "--work-dir", str(work), "--renderer-root", os.environ["VIBEFLOW_MERMAID_RENDERER_ROOT"]],
        env={**os.environ, "PYTHONPATH": str(SOURCE_ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True,
    )
    if completed.returncode:
        return CaseResult("comprehensive_math", "FAIL", completed.stdout + completed.stderr)
    payload = json.loads((work / "report.json").read_text())
    return CaseResult("comprehensive_math", "PASS", completed.stdout.strip(), payload)


def _run_addition_case(name: str) -> CaseResult:
    work = WORK_ROOT / name
    completed = subprocess.run(
        [sys.executable, str(SANDBOX_DIR.parent / name / "run_all.py"), "--work-dir", str(work),
         "--renderer-root", os.environ["VIBEFLOW_MERMAID_RENDERER_ROOT"]],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True,
    )
    if completed.returncode:
        return CaseResult(name, "FAIL", completed.stdout + completed.stderr)
    payload = json.loads((work / "report.json").read_text())
    return CaseResult(name, payload["status"], completed.stdout.strip(), payload)


def _configure_runtime(work_root: Path) -> None:
    global WORK_ROOT, PROJECT_DIR, CONFIG_DIR, REPORT_DIR, ASCII_DIR
    global MERMAID_DIR, SVG_DIR, COMPILED_BLOCK_DIR, RUN_ROOT, POLICY_PATH
    global WORKSPACE_PATH, REVIEW_ARCHITECTURE_DIR, REVIEW_ARCHITECTURE_PATH
    global REVIEW_DIR
    global EXTERNAL_DEDUP_REVIEW_CONFIG_PATH

    WORK_ROOT = work_root.resolve()
    PROJECT_DIR = WORK_ROOT / "project"
    shutil.copytree(
        FIXTURE_PROJECT_DIR,
        PROJECT_DIR,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "review_artifacts", ".artifacts"
        ),
    )
    WORKSPACE_PATH = WORK_ROOT / "vibeflow_config.jsonc"
    shutil.copy2(FIXTURE_WORKSPACE_PATH, WORKSPACE_PATH)
    CONFIG_DIR = PROJECT_DIR / "configs"
    REPORT_DIR = WORK_ROOT / "reports"
    ASCII_DIR = REPORT_DIR / "ascii"
    MERMAID_DIR = REPORT_DIR / "mermaid"
    SVG_DIR = REPORT_DIR / "svg"
    COMPILED_BLOCK_DIR = REPORT_DIR / "compiled_blocks"
    RUN_ROOT = WORK_ROOT / "runs"
    POLICY_PATH = PROJECT_DIR / "kernel_policy.jsonc"
    REVIEW_ARCHITECTURE_DIR = PROJECT_DIR / "review_artifacts"
    REVIEW_ARCHITECTURE_PATH = REVIEW_ARCHITECTURE_DIR / "ARCHITECTURE.jsonc"
    REVIEW_DIR = REPORT_DIR / "review"
    EXTERNAL_DEDUP_REVIEW_CONFIG_PATH = (
        CONFIG_DIR / "review_external_nodeset_dedup.jsonc"
    )


def _prepare_environment() -> None:
    if not (SOURCE_ROOT / "vibeflow").is_dir():
        raise EnvironmentError(f"VibeFlow source package is missing: {SOURCE_ROOT}")
    _prepare_temporary_mermaid_renderer()
    for path in (SOURCE_ROOT, PROJECT_DIR):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    os.chdir(WORK_ROOT)


def _prepare_temporary_mermaid_renderer() -> None:
    supplied = os.environ.get("VIBEFLOW_MERMAID_RENDERER_ROOT")
    if supplied:
        if not (Path(supplied) / "node_modules/.bin/mmdc").is_file():
            raise EnvironmentError(f"explicit Mermaid renderer is unavailable: {supplied}")
        return
    source = REPO_ROOT / "tools" / "mermaid-renderer"
    destination = WORK_ROOT / "mermaid-renderer"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        source_file = source / name
        if not source_file.is_file():
            raise EnvironmentError(f"Mermaid renderer manifest is missing: {source_file}")
        shutil.copy2(source_file, destination / name)
    try:
        completed = subprocess.run(
            ["npm", "ci"],
            cwd=destination,
            check=False,
            text=True,
        )
    except FileNotFoundError as exc:
        raise EnvironmentError("npm is not available") from exc
    if completed.returncode != 0:
        raise EnvironmentError(
            "temporary Mermaid renderer install failed with status "
            f"{completed.returncode}"
        )
    os.environ["VIBEFLOW_MERMAID_RENDERER_ROOT"] = str(destination)


def _reset_outputs() -> None:
    for path in (REPORT_DIR, RUN_ROOT, REVIEW_ARCHITECTURE_DIR):
        if path.exists():
            shutil.rmtree(path)
    ASCII_DIR.mkdir(parents=True, exist_ok=True)
    COMPILED_BLOCK_DIR.mkdir(parents=True, exist_ok=True)
    MERMAID_DIR.mkdir(parents=True, exist_ok=True)
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)


def _run_workspace_quality_case() -> CaseResult:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/run_tests.py"),
            "--",
            str(REPO_ROOT / "tests/targets/python/test_quality_workspace_sandbox.py"),
        ],
        cwd=WORK_ROOT,
        env=dict(os.environ),
        text=True,
        capture_output=True,
        check=False,
    )
    output = completed.stdout + completed.stderr
    return CaseResult(
        "quality:cross_root_workspace",
        "PASS" if completed.returncode == 0 else "FAIL",
        output.strip(),
    )


def _run_review_cases() -> list[CaseResult]:
    cases = (
        ("review:registered_expanded", _run_registered_review_case),
        ("review:external_nodeset_dedup_visual", _run_external_nodeset_dedup_review_case),
        ("review:unregistered_fail_closed", _run_unregistered_review_case),
    )
    results: list[CaseResult] = []
    for name, runner in cases:
        try:
            result = runner()
        except Exception as exc:
            result = CaseResult(name, "FAIL", str(exc))
        results.append(result)
    return results


def _run_published_diagram_audit_case(results: list[CaseResult]) -> CaseResult:
    name = "audit:published_diagrams_health_gated"
    try:
        return _audit_published_diagrams(results)
    except Exception as exc:
        return CaseResult(name, "FAIL", str(exc))


def _audit_published_diagrams(results: list[CaseResult]) -> CaseResult:
    from vibeflow.tooling.application.python.presentation.mermaid.render import (
        is_mermaid_svg_renderer_available,
    )

    valid_names = {str(case["name"]) for case in VALID_RUN_CASES}
    success_run_names = valid_names
    success_run_svgs: set[Path] = set()
    for run_name in sorted(success_run_names):
        run_dir = RUN_ROOT / run_name
        health_path = run_dir / "health_report.json"
        if not health_path.is_file():
            raise AssertionError(f"successful diagram run is missing health_report.json: {run_name}")
        health = json.loads(health_path.read_text(encoding="utf-8"))
        if health.get("status") not in {"PASS", "CONCERNS"} or health.get("errors"):
            raise AssertionError(
                f"successful diagram run has invalid health: {run_name} "
                f"status={health.get('status')!r} errors={health.get('errors')!r}"
            )
        svg_path = run_dir / "graph.svg"
        if is_mermaid_svg_renderer_available():
            if not svg_path.is_file():
                raise AssertionError(f"successful diagram run is missing graph.svg: {run_name}")
            success_run_svgs.add(svg_path)

    expected_error_run_names = {
        f"expected_fail_{Path(str(case['config'])).stem}"
        for case in INVALID_CASES
        if case["kind"] == "run"
    }
    expected_error_run_names.update(
        f"expected_runtime_fail_{Path(str(case['config'])).stem}"
        for case in INVALID_CASES
        if case["kind"] == "runtime_run"
    )
    actual_run_svgs = set(RUN_ROOT.glob("*/graph.svg"))
    allowed_error_run_svgs = {RUN_ROOT / run_name / "graph.svg" for run_name in expected_error_run_names}
    unexpected_run_svgs = actual_run_svgs - success_run_svgs - allowed_error_run_svgs
    if unexpected_run_svgs:
        raise AssertionError(
            "run SVGs are not owned by a health-gated success or an explicit error-path case: "
            f"{sorted(str(path.relative_to(WORK_ROOT)) for path in unexpected_run_svgs)}"
        )

    expected_report_svgs: set[Path] = {
        REVIEW_DIR / "pass_nodeset_nested.expanded.svg",
        REVIEW_DIR / "external_nodeset_dedup.expanded.svg",
    }
    if is_mermaid_svg_renderer_available():
        for run_name in valid_names:
            expected_report_svgs.add(SVG_DIR / f"{run_name}.svg")
            expected_report_svgs.add(SVG_DIR / f"{run_name}.expanded.svg")
    actual_report_svgs = set(REPORT_DIR.rglob("*.svg"))
    if actual_report_svgs != expected_report_svgs:
        raise AssertionError(
            "published report SVG set does not match health-gated producers: "
            f"unexpected={sorted(str(path.relative_to(WORK_ROOT)) for path in actual_report_svgs - expected_report_svgs)}, "
            f"missing={sorted(str(path.relative_to(WORK_ROOT)) for path in expected_report_svgs - actual_report_svgs)}"
        )

    result_by_name = {result.name: result for result in results}
    registered_review = result_by_name.get("review:registered_expanded")
    registered_payload = registered_review.payload if registered_review is not None else None
    if not isinstance(registered_payload, dict) or registered_payload.get("status") not in {"PASS", "CONCERNS"}:
        raise AssertionError("registered review SVG does not have a successful validation result")
    external_review = result_by_name.get("review:external_nodeset_dedup_visual")
    external_payload = external_review.payload if external_review is not None else None
    if not isinstance(external_payload, dict) or external_payload.get("health") != "PASS":
        raise AssertionError("external/dedup review SVG does not have a strict PASS validation result")

    for svg_path in sorted((*expected_report_svgs, *success_run_svgs)):
        try:
            root = ET.parse(svg_path).getroot()
        except ET.ParseError as exc:
            raise AssertionError(f"published success SVG is not valid XML: {svg_path}") from exc
        if _xml_local_name(root.tag) != "svg":
            raise AssertionError(f"published success diagram root is not svg: {svg_path}")

    excluded_error_svgs = actual_run_svgs & allowed_error_run_svgs
    return CaseResult(
        "audit:published_diagrams_health_gated",
        "PASS",
        payload={
            "report_svgs": len(actual_report_svgs),
            "successful_run_svgs": len(success_run_svgs),
            "health_gated_success_runs": len(success_run_names),
            "explicit_error_path_svgs_excluded": len(excluded_error_svgs),
        },
    )














def _run_registered_review_case() -> CaseResult:
    REVIEW_ARCHITECTURE_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_ARCHITECTURE_PATH.write_text("stale architecture\n", encoding="utf-8")
    output_path = REVIEW_DIR / "pass_nodeset_nested.expanded.svg"
    output_path.write_text("legacy svg\n", encoding="utf-8")

    completed, payload = _run_review_cli(CONFIG_DIR / "pass_nodeset_nested.jsonc", output_path)
    if completed.returncode != 0:
        raise AssertionError(f"review returned {completed.returncode}: {payload}")
    if payload.get("status") not in {"PASS", "CONCERNS"}:
        raise AssertionError(f"unexpected review status: {payload.get('status')}")
    if payload.get("failed_stage") is not None or payload.get("published") is not True:
        raise AssertionError(f"review did not publish successfully: {payload}")
    expected_paths = {
        "config": str((CONFIG_DIR / "pass_nodeset_nested.jsonc").resolve()),
        "architecture": str(REVIEW_ARCHITECTURE_PATH.resolve()),
        "svg": str(output_path.resolve()),
    }
    for field, expected in expected_paths.items():
        if payload.get(field) != expected:
            raise AssertionError(f"unexpected {field}: {payload.get(field)!r}, expected {expected!r}")
    validation = payload.get("validation")
    if not isinstance(validation, dict) or validation.get("status") != payload.get("status"):
        raise AssertionError(f"review validation summary is inconsistent: {validation}")

    architecture_text = REVIEW_ARCHITECTURE_PATH.read_text(encoding="utf-8")
    if not architecture_text.startswith("// GENERATED BY VIBEFLOW. DO NOT EDIT."):
        raise AssertionError("review did not replace the stale architecture with a canonical document")
    for marker in ("math.add_one", "math.add_two"):
        if marker not in architecture_text:
            raise AssertionError(f"canonical architecture is missing nested nodeset marker {marker!r}")

    root = ET.parse(output_path).getroot()
    if _xml_local_name(root.tag) != "svg":
        raise AssertionError("review output root is not svg")
    if root.attrib.get("aria-roledescription") != "flowchart-review-columns":
        raise AssertionError("review output is missing the canonical review-columns marker")
    fragments = [
        element
        for element in root.iter()
        if _xml_local_name(element.tag) == "g"
        and "review-inline-fragment" in element.attrib.get("class", "").split()
        and len(list(element)) > 0
    ]
    if len(fragments) < 2:
        raise AssertionError(f"expected expanded main/nodeset SVG fragments, got {len(fragments)}")
    if list(REVIEW_DIR.rglob("*.provenance.json")):
        raise AssertionError("review unexpectedly emitted a provenance sidecar")
    if list(REVIEW_DIR.rglob("*.mmd")):
        raise AssertionError("review unexpectedly published an intermediate Mermaid file")
    if "provenance" in output_path.read_text(encoding="utf-8").lower():
        raise AssertionError("review unexpectedly embedded provenance metadata")

    return CaseResult(
        "review:registered_expanded",
        "PASS",
        payload={
            "status": payload["status"],
            "published": True,
            "architecture": str(REVIEW_ARCHITECTURE_PATH.relative_to(WORK_ROOT)),
            "svg": str(output_path.relative_to(WORK_ROOT)),
            "svg_fragments": len(fragments),
        },
    )


def _run_unregistered_review_case() -> CaseResult:
    output_path = REVIEW_DIR / "unregistered.svg"
    output_path.unlink(missing_ok=True)
    architecture_before = REVIEW_ARCHITECTURE_PATH.read_bytes()

    completed, payload = _run_review_cli(CONFIG_DIR / "pass_free_nodes.jsonc", output_path)
    if completed.returncode != 1:
        raise AssertionError(f"unregistered review returned {completed.returncode}, expected 1: {payload}")
    if payload.get("status") != "FAIL" or payload.get("failed_stage") != "architecture":
        raise AssertionError(f"unregistered review failed with the wrong stage/status: {payload}")
    if payload.get("published") is not False:
        raise AssertionError("unregistered review reported an SVG publication")
    error = payload.get("error")
    if not isinstance(error, dict) or error.get("rule_id") != "REVIEW.ARCHITECTURE.UNREGISTERED":
        raise AssertionError(f"unexpected unregistered review error: {error}")
    if output_path.exists():
        raise AssertionError("unregistered review published an SVG")
    if REVIEW_ARCHITECTURE_PATH.read_bytes() != architecture_before:
        raise AssertionError("unregistered review modified the registered architecture document")

    return CaseResult(
        "review:unregistered_fail_closed",
        "PASS",
        payload={
            "status": payload["status"],
            "published": False,
            "rule_id": error["rule_id"],
        },
    )


def _run_external_nodeset_dedup_review_case() -> CaseResult:
    output_path = REVIEW_DIR / "external_nodeset_dedup.expanded.svg"
    output_path.unlink(missing_ok=True)

    validation = _run_validate_cli(EXTERNAL_DEDUP_REVIEW_CONFIG_PATH)
    if validation.returncode != 0 or "VIBEFLOW_STRUCTURE_PASS" not in validation.stdout:
        raise AssertionError(
            "review fixture must pass health validation before SVG export: "
            f"returncode={validation.returncode}, stdout={validation.stdout!r}, stderr={validation.stderr!r}"
        )

    completed = _run_export_svg_cli(EXTERNAL_DEDUP_REVIEW_CONFIG_PATH, output_path)
    if completed.returncode != 0:
        raise AssertionError(
            f"expanded SVG export returned {completed.returncode}: "
            f"stdout={completed.stdout!r}, stderr={completed.stderr!r}"
        )
    root = ET.parse(output_path).getroot()
    if root.attrib.get("aria-roledescription") != "flowchart-review-columns":
        raise AssertionError("expanded SVG is missing the canonical review-columns marker")

    svg_text = output_path.read_text(encoding="utf-8")
    for marker in ("stroke-width:7px", "vector-effect:non-scaling-stroke"):
        if marker not in svg_text:
            raise AssertionError(f"expanded SVG is missing external boundary marker {marker!r}")

    external_nodes = [
        element
        for element in root.iter()
        if _xml_local_name(element.tag) == "g"
        and "externalBoundary" in element.attrib.get("class", "").split()
    ]
    if len(external_nodes) != 1:
        raise AssertionError(f"expected one externalBoundary node, got {len(external_nodes)}")
    external_classes = set(external_nodes[0].attrib.get("class", "").split())
    if "externalDependency" not in external_classes:
        raise AssertionError(f"external node lost its color class: {sorted(external_classes)}")

    text_elements = [
        " ".join("".join(element.itertext()).split())
        for element in root.iter()
        if _xml_local_name(element.tag) == "text"
    ]
    visible_text = " ".join(text_elements)
    for marker in (
        "[EXTERNAL] External Boost",
        "external: true",
        "body: visual.reusable_worker",
        "id: worker_a",
        "id: worker_b",
        "id: worker_c",
        "id: worker_d",
        "id: end",
    ):
        if marker not in visible_text:
            raise AssertionError(f"expanded SVG is missing visible marker {marker!r}")

    svg_ids = {element.attrib["id"] for element in root.iter() if "id" in element.attrib}
    for worker_id in ("worker_a", "worker_b", "worker_c", "worker_d"):
        expected_suffix = f"L_{worker_id}_n_end_0"
        if not any(svg_id.endswith(expected_suffix) for svg_id in svg_ids):
            raise AssertionError(f"expanded SVG is missing {worker_id}->end edge {expected_suffix!r}")

    review_titles = [
        " ".join("".join(element.itertext()).split())
        for element in root.iter()
        if _xml_local_name(element.tag) == "text"
        and "review-title" in element.attrib.get("class", "").split()
    ]
    grouped_titles = [title for title in review_titles if "type_key: visual.reusable_worker" in title]
    if len(grouped_titles) != 1:
        raise AssertionError(f"expected one locally deduplicated worker detail, got {grouped_titles!r}")
    grouped_title = grouped_titles[0]
    for marker in (
        "calls: 4",
        "worker_a",
        "worker_b{node_configs=1}",
        "worker_c{node_configs=1}",
        "+1",
    ):
        if marker not in grouped_title:
            raise AssertionError(f"grouped detail title is missing {marker!r}: {grouped_title!r}")
    if "101" in grouped_title or "202" in grouped_title:
        raise AssertionError(f"grouped detail title leaked config values: {grouped_title!r}")

    fragments = [
        element
        for element in root.iter()
        if _xml_local_name(element.tag) == "g"
        and "review-inline-fragment" in element.attrib.get("class", "").split()
    ]
    if len(fragments) != 4:
        raise AssertionError(f"expected main graph, plugins, base_lib and one deduplicated detail, got {len(fragments)}")
    if set(review_titles) != {"main pipeline", "plugins", "base_lib", grouped_title}:
        raise AssertionError(f"expanded review has unexpected resource groups: {review_titles!r}")
    if "resources and implementation files" in visible_text or "Node types and rules" in visible_text:
        raise AssertionError("expanded review must show selected resource directories without source or rule projections")

    return CaseResult(
        "review:external_nodeset_dedup_visual",
        "PASS",
        payload={
            "health": "PASS",
            "result_code": "VIBEFLOW_STRUCTURE_PASS",
            "svg": str(output_path.relative_to(WORK_ROOT)),
            "external_nodes": len(external_nodes),
            "worker_calls": 4,
            "worker_detail_fragments": len(grouped_titles),
            "svg_fragments": len(fragments),
        },
    )


def _run_review_cli(config_path: Path, output_path: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "vibeflow",
            "review",
            "--workspace",
            str(WORKSPACE_PATH),
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
        cwd=WORK_ROOT,
        env=_sandbox_cli_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"review stdout is not one JSON object: stdout={completed.stdout!r}, stderr={completed.stderr!r}"
        ) from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"review stdout JSON is not an object: {payload!r}")
    return completed, payload


def _run_export_svg_cli(config_path: Path, output_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "vibeflow",
            "export-svg",
            "--workspace",
            str(WORKSPACE_PATH),
            "--config",
            str(config_path),
            "--expand-nodesets",
            "--output",
            str(output_path),
        ],
        cwd=WORK_ROOT,
        env=_sandbox_cli_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def _run_validate_cli(config_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "vibeflow",
            "validate",
            "--workspace",
            str(WORKSPACE_PATH),
            "--config",
            str(config_path),
        ],
        cwd=WORK_ROOT,
        env=_sandbox_cli_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def _sandbox_cli_environment() -> dict[str, str]:
    environment = os.environ.copy()
    python_paths = [str(SOURCE_ROOT), str(PROJECT_DIR)]
    if environment.get("PYTHONPATH"):
        python_paths.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(python_paths)
    return environment


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _node_declaration(descriptor, contract, *, schema=None, defaults=None):
    from dataclasses import replace
    return replace(descriptor, rulesets=(), contract=replace(contract,
        params_schema=schema or {}, params_defaults=defaults or {}))


def _project_registry():
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry
    return declared_python_registry(load_workspace_config(WORKSPACE_PATH),config_path=PROJECT_DIR / 'configs/pass_nodeset_nested.jsonc')


def _node_source_report(type_key, *, policy=None):
    from vibeflow.tooling.application.python.project.declarations import collect_node_source_context
    from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules
    registry = _project_registry()
    context = collect_node_source_context(registry, (type_key,))
    imported = execute_python_node_rules(registry, context, phase="import", purity_policy=policy)
    reviewed = execute_python_node_rules(registry, context, phase="static", purity_policy=policy)
    return (*imported.findings, *reviewed.findings)


def _run_valid_cases() -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in VALID_RUN_CASES:
        try:
            result = _run_valid_case(case)
        except Exception as exc:
            result = CaseResult(f"valid:{case['name']}", "FAIL", str(exc))
        results.append(result)
        print(f"{result.status} {result.name}", flush=True)
    return results


def _run_execution_model_cases() -> list[CaseResult]:
    cases = (
        (
            "execution:python-sync-vs-result-key-thread",
            _run_python_sync_async_thread_case,
        ),
        (
            "execution:python-thread-pool-boundaries",
            _run_python_thread_pool_boundary_case,
        ),
    )
    results: list[CaseResult] = []
    for name, runner in cases:
        try:
            result = runner()
        except Exception as exc:
            result = CaseResult(name, "FAIL", str(exc))
        results.append(result)
    return results


def _run_global_state_cases() -> list[CaseResult]:
    cases = (
        (
            "global-state:forbidden-effect-audit",
            _run_global_state_forbidden_effect_audit,
        ),
        (
            "global-state:protected-async-compile",
            _run_global_state_protected_async_compile_case,
        ),
        (
            "global-state:unlocked-overlap",
            _run_global_state_unlocked_overlap_case,
        ),
        (
            "global-state:failure-releases-lock",
            _run_global_state_failure_release_case,
        ),
    )
    results: list[CaseResult] = []
    for name, runner in cases:
        try:
            result = runner()
        except Exception as exc:
            result = CaseResult(name, "FAIL", str(exc))
        results.append(result)
    return results


def _run_source_preflight_cases() -> list[CaseResult]:
    cases = (
        (
            "source-preflight:imported-declarative-contract-helper",
            _run_imported_declarative_helper_preflight_case,
        ),
        (
            "source-preflight:effectful-imported-helper-rejected",
            _run_effectful_imported_helper_preflight_case,
        ),
    )
    results: list[CaseResult] = []
    for name, runner in cases:
        try:
            result = runner()
        except Exception as exc:
            result = CaseResult(name, "FAIL", str(exc))
        results.append(result)
    return results


def _import_rule_findings(entry: Path, *, project_root: Path, source_roots=()):
    """Run an explicitly selected import Rule on the real local source closure."""
    from vibeflow.core.descriptors.models import NodeContractDescriptor, NodeDescriptor
    from vibeflow.core.rules import RuleContext, compile_ruleset, execute_rule_plan
    from vibeflow.targets.python.rules import builtin_rule_resources
    from vibeflow.targets.python.rules.plugin import builtin_plugin
    from vibeflow.targets.python.quality.source_context import (
        PythonSourceFile, PythonSourceNode, build_python_source_context,
    )
    from vibeflow.targets.python.project.source_closure import collect_python_source_facts

    descriptor = NodeDescriptor(type_key="sandbox.preflight", display_name="Preflight",
         description="Import-rule acceptance fixture.", version="0.1.0",
        flow_kind="process", rulesets=("vibeflow.process",), contract=NodeContractDescriptor())
    facts = collect_python_source_facts(entry, project_root=project_root, source_roots=tuple(source_roots))
    context = build_python_source_context(
        (PythonSourceNode(descriptor, str(entry), "SandboxNode"),),
        (PythonSourceFile.parse(item.path, item.module_name, item.source) for item in facts),
    )
    rules, rulesets = builtin_rule_resources()
    plan = compile_ruleset("vibeflow.process", rules={item.id:item for item in rules},
        rulesets={item.id:item for item in rulesets}, entrypoint="import")
    return execute_rule_plan(plan, RuleContext(facts={"source_context":context},
        subject={"type_key":descriptor.type_key,"descriptor":descriptor,"kind":"node"},
        target="python", phase="import"), handlers={key:value for (kind,key),value in builtin_plugin().bindings().items() if kind == "rule"}).findings


def _run_imported_declarative_helper_preflight_case() -> CaseResult:
    case_root = WORK_ROOT / "source_preflight" / "allowed"
    framework_root = case_root / "framework"
    project_root = case_root / "project"
    framework_root.mkdir(parents=True, exist_ok=True)
    project_root.mkdir(parents=True, exist_ok=True)
    (framework_root / "contracts.py").write_text(
        """
class SafeRunMixin:
    def run_pure(self, inputs, params):
        return {"sandbox.out": 1}
""".strip(), encoding="utf-8")
    entry = project_root / "node.py"
    entry.write_text(
        """
from contracts import SafeRunMixin

class SandboxNode(SafeRunMixin):
    pass
""".strip(), encoding="utf-8")
    findings = _import_rule_findings(entry, project_root=project_root, source_roots=(framework_root,))
    if findings:
        raise AssertionError(f"safe imported helper rejected: {findings!r}")
    return CaseResult("source-preflight:imported-declarative-contract-helper", "PASS")


def _run_effectful_imported_helper_preflight_case() -> CaseResult:
    case_root = WORK_ROOT / "source_preflight" / "rejected"
    case_root.mkdir(parents=True, exist_ok=True)
    artifact = case_root / "must_not_exist.txt"
    helper = case_root / "contracts.py"
    helper.write_text(f"open({str(artifact)!r}, 'w').write('executed')\n", encoding="utf-8")
    entry = case_root / "node.py"
    entry.write_text("import contracts\n\nclass SandboxNode:\n    def run_pure(self, inputs, params):\n        return {}\n", encoding="utf-8")
    findings = _import_rule_findings(entry, project_root=case_root)
    if not any(item.code == "NODE.IMPORT.SIDE_EFFECT" and item.source_location.get("path") == str(helper) for item in findings):
        raise AssertionError(f"effectful helper was not rejected with its actual source: {findings!r}")
    if artifact.exists():
        raise AssertionError("effectful imported helper executed before rejection")
    return CaseResult("source-preflight:effectful-imported-helper-rejected", "PASS")


def _run_global_state_forbidden_effect_audit() -> CaseResult:
    from vibeflow.targets.python.quality.source_analysis import PurityPolicy
    cases = {"file":"bad.global_state.file", "environment":"bad.global_state.environment",
             "network":"bad.global_state.network", "subprocess":"bad.global_state.subprocess",
             "thread":"bad.global_state.thread", "eval":"bad.global_state.eval",
             "dynamic_import":"bad.global_state.dynamic_import", "ffi":"bad.global_state.ffi", "cffi":"bad.global_state.cffi"}
    policy = PurityPolicy(max_source_lines=500, warn_source_lines=None)
    rules = {}
    accepted = {"NODE.EFFECT.IMPORT_FORBIDDEN", "NODE.EFFECT.CALL_FORBIDDEN", "NODE.PURITY.BANNED_CALL"}
    for category, type_key in cases.items():
        findings = _node_source_report(type_key, policy=policy)
        errors = [finding.rule_id for finding in findings if finding.severity == "error"]
        if category in {"eval", "dynamic_import", "ffi", "cffi"}:
            if errors:
                raise AssertionError(f"retired security restriction still rejects {category}: {errors}")
        elif not set(errors) & accepted:
            raise AssertionError(f"selected global-state Rules unexpectedly allowed {category}: {errors}")
        rules[category] = errors
    return CaseResult("global-state:forbidden-effect-audit", "PASS", payload={"rejected":rules})


def _run_global_state_protected_async_compile_case() -> CaseResult:
    from vibeflow.targets.python.project import GraphCompileError, GraphCompiler
    from vibeflow.tooling.project.graph_config import parse_graph_config


    state = {
        "id": "state",
        "type_used": "sandbox.global_state_probe",
        "display_name": "State",
        "description": "Declares process-local ambient state.",
    }
    cases = (
        (
            "GRAPH.EXECUTION_LOCK.DETACHED_FORBIDDEN",
            {
                "id": "side",
                "type_used": "sandbox.constant",
                "display_name": "Side",
                "description": "Attempts to escape the protected root.",
                "async": "detached",
            },
            {"owner": "pipeline", "node": "side", "async": "detached"},
        ),
        (
            "GRAPH.EXECUTION_LOCK.RESULT_UNJOINABLE",
            {
                "id": "future",
                "type_used": "sandbox.constant",
                "display_name": "Future",
                "description": "Has no statically provable consumer path.",
                "async": "result_key",
                "result_key": "value.in",
            },
            {
                "owner": "pipeline",
                "node": "future",
                "async": "result_key",
                "result_key": "value.in",
            },
        ),
    )
    rejected: list[str] = []
    unlocked = parse_graph_config(
        {"pipeline": {"nodes": [dict(state), dict(cases[0][1])]}}
    )
    GraphCompiler().compile(unlocked, registry=_project_registry())
    for expected_rule, async_node, expected_details in cases:
        graph = parse_graph_config(
            {
                "pipeline": {
                    "execution_lock": {
                        "key": "sandbox.global-state.async"
                    },
                    "nodes": [dict(state), async_node],
                }
            }
        )
        try:
            GraphCompiler().compile(graph, registry=_project_registry())
        except GraphCompileError as exc:
            if exc.rule_id != expected_rule:
                raise AssertionError(
                    f"expected {expected_rule}, got {exc.rule_id}: {exc}"
                ) from exc
            if exc.details != expected_details:
                raise AssertionError(
                    f"{expected_rule} details expected {expected_details!r}, "
                    f"got {exc.details!r}"
                ) from exc
            rejected.append(exc.rule_id)
        else:
            raise AssertionError(
                f"protected async case was accepted: {expected_rule}"
            )
    return CaseResult(
        "global-state:protected-async-compile",
        "PASS",
        payload={"unlocked_detached": "accepted", "rejected": rejected},
    )


def _global_state_runtime_graph(
    node_type: str,
    *,
    root_lock: str = "",
):
    from vibeflow.tooling.project.graph_config import parse_graph_config

    pipeline: dict[str, Any] = {
        "nodes": [
            {
                "id": "start",
                "type_used": "sandbox.start",
                "display_name": "Start",
                "description": "Starts the lock probe.",
            },
            {
                "id": "work",
                "type_used": node_type,
                "display_name": "Work",
                "description": "Runs the lock probe.",
            },
            {
                "id": "end",
                "type_used": "sandbox.start",
                "display_name": "End",
                "description": "Ends the lock probe.",
            },
        ],
        "edges": [
            {"from": "start", "to": "work"},
            {"from": "work", "to": "end"},
        ],
    }
    if root_lock:
        pipeline["execution_lock"] = {"key": root_lock}
    return parse_graph_config({"pipeline": pipeline})


def _normal_runtime_graph():
    from vibeflow.tooling.project.graph_config import parse_graph_config

    return parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {
                        "id": "start",
                        "type_used": "sandbox.start",
                        "display_name": "Start",
                        "description": "Starts the normal root.",
                    },
                    {
                        "id": "end",
                        "type_used": "sandbox.start",
                        "display_name": "End",
                        "description": "Ends the normal root.",
                    },
                ],
                "edges": [{"from": "start", "to": "end"}],
            }
        }
    )


def _run_global_state_unlocked_overlap_case() -> CaseResult:
    from vibeflow.targets.python.project import PluginRegistry
    from vibeflow.targets.python.runtime.engine import PipelineRuntime


    entered = threading.Event()
    release = threading.Event()

    class HoldNormalRoot:
        name = "hold-normal-root"

        def before_run(self, initial):
            del initial
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("timed out waiting to release normal root")

    plugins = PluginRegistry()
    plugins.register(HoldNormalRoot(), plugin_type="runtime")
    registry = _project_registry()
    normal_dir = RUN_ROOT / "global-state-normal-reader"
    global_dir = RUN_ROOT / "global-state-unlocked-cloud"
    normal = PipelineRuntime(
        _normal_runtime_graph(),
        registry=registry,
        plugin_registry=plugins,
        run_dir=normal_dir,
    )
    global_runtime = PipelineRuntime(
        _global_state_runtime_graph("sandbox.global_state_probe"),
        registry=registry,
        run_dir=global_dir,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        normal_future = executor.submit(normal.run)
        if not entered.wait(timeout=2):
            raise AssertionError("normal root never entered its protected hook")
        global_future = executor.submit(global_runtime.run)
        global_future.result(timeout=3)
        release.set()
        normal_future.result(timeout=3)
    events = _runtime_trace_lines(global_dir)
    lock_events = [
        event for event in events if str(event.get("kind", "")).startswith("lock_")
    ]
    if lock_events:
        raise AssertionError(
            f"unlocked global-state root emitted lock events: {lock_events!r}"
        )
    return CaseResult(
        "global-state:unlocked-overlap",
        "PASS",
        payload={"overlapped_normal_root": True, "lock_events": 0},
    )


def _run_global_state_failure_release_case() -> CaseResult:
    from vibeflow.targets.python.runtime.engine import PipelineRuntime


    lock_key = "sandbox.global-state.failure"
    registry = _project_registry()
    failure_dir = RUN_ROOT / "global-state-failure"
    failing = PipelineRuntime(
        _global_state_runtime_graph(
            "sandbox.global_state_failure",
            root_lock=lock_key,
        ),
        registry=registry,
        run_dir=failure_dir,
    )
    try:
        failing.run()
    except RuntimeError as exc:
        if "sandbox global-state failure" not in str(exc):
            raise
    else:
        raise AssertionError("global-state failure probe unexpectedly succeeded")
    events = _runtime_trace_lines(failure_dir)
    kinds = [event["kind"] for event in events]
    if "global_state_may_have_changed" not in kinds:
        raise AssertionError("failed global-state run omitted state-change warning")
    warning = kinds.index("global_state_may_have_changed")
    release_positions = [
        index for index, kind in enumerate(kinds) if kind == "lock_released"
    ]
    if not release_positions or warning >= min(release_positions):
        raise AssertionError(
            f"state-change warning must precede lock release: {kinds!r}"
        )
    recovered = PipelineRuntime(
        _global_state_runtime_graph(
            "sandbox.global_state_probe",
            root_lock=lock_key,
        ),
        registry=registry,
        run_dir=RUN_ROOT / "global-state-recovered",
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(recovered.run).result(timeout=3)
    return CaseResult(
        "global-state:failure-releases-lock",
        "PASS",
        payload={"warning_before_release": True, "lock_reused": True},
    )


def _thread_probe_graph(*, async_mode: bool):
    from vibeflow.tooling.project.graph_config import parse_graph_config

    probe: dict[str, Any] = {
        "id": "probe",
        "type_used": "sandbox.thread_probe",
        "display_name": "Thread probe",
        "description": "Reports the Python thread used to execute this node.",
    }
    if async_mode:
        probe.update(
            {
                "async": "result_key",
                "result_key": "thread.name",
            }
        )
    return parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {
                        "id": "start",
                        "type_used": "sandbox.thread_start",
                        "display_name": "Thread probe start",
                        "description": "Starts the thread execution fixture.",
                    },
                    probe,
                    {
                        "id": "end",
                        "type_used": "sandbox.thread_end",
                        "display_name": "Thread probe end",
                        "description": "Joins the thread probe result.",
                    },
                ],
                "edges": [
                    {"from": "start", "to": "probe"},
                    {"from": "probe", "to": "end"},
                ],
                "outputs": [
                    {
                        "type": "thread.result",
                        "cardinality": "exactly_one",
                        "display_name": "Thread result",
                    }
                ],
            }
        }
    )


def _thread_probe_registry():
    from vibeflow.core import DataProvider, DataRequirement
    from vibeflow.targets.python.project import NodeRegistry
    from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor

    ThreadProbeNode_DECLARATION = _node_declaration(NodeDescriptor(type_key='sandbox.thread_probe', display_name='Thread probe', description='Reports the current Python thread.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('thread.name', 'thread.name', display_name='thread.name'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('thread.name', 'thread.name', display_name='thread.name'),)}))
    class ThreadProbeNode:

        def run_pure(self, inputs, params):
            del inputs, params
            return {"thread.name": threading.current_thread().name}

    ThreadStartNode_DECLARATION = _node_declaration(NodeDescriptor(type_key='sandbox.thread_start', display_name='Thread probe start', description='Starts the thread execution fixture.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor())
    class ThreadStartNode:

        def run_pure(self, inputs, params):
            del inputs, params
            return {}

    ThreadEndNode_DECLARATION = _node_declaration(NodeDescriptor(type_key='sandbox.thread_end', display_name='Thread probe end', description='Ends after joining a thread probe result.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('thread.name', 'exactly_one', display_name='thread.name'),), provides=(DataProvider('thread.result', 'thread.result', display_name='thread.result'),), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('thread.name', 'exactly_one', display_name='thread.name'),)}, output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('thread.result', 'thread.result', display_name='thread.result'),)}))
    class ThreadEndNode:

        def run_pure(self, inputs, params):
            del params
            return {"thread.result": inputs["thread.name"]["value"]}

    registry = NodeRegistry()
    registry.register(
        ThreadStartNode_DECLARATION,
        ThreadStartNode,
    )
    registry.register(
        ThreadProbeNode_DECLARATION,
        ThreadProbeNode,
    )
    registry.register(
        ThreadEndNode_DECLARATION,
        ThreadEndNode,
    )
    return registry


def _run_python_sync_async_thread_case() -> CaseResult:
    from vibeflow.targets.python.runtime.engine import PipelineRuntime
    from vibeflow.targets.python.runtime.options import RuntimeOptions

    registry = _thread_probe_registry()
    main_thread = threading.current_thread().name
    sync_context = PipelineRuntime(
        _thread_probe_graph(async_mode=False),
        registry=registry,
        runtime_options=RuntimeOptions(trace="full"),
    ).run({})
    async_context = PipelineRuntime(
        _thread_probe_graph(async_mode=True),
        registry=registry,
        runtime_options=RuntimeOptions(trace="full", async_max_workers=2),
    ).run({})
    sync_thread = _context_value(sync_context, "thread.result")
    async_thread = _context_value(async_context, "thread.result")
    if sync_thread != main_thread:
        raise AssertionError(
            f"sync node ran on {sync_thread!r}, expected {main_thread!r}"
        )
    if async_thread == main_thread:
        raise AssertionError(
            "result_key node did not leave the current Python thread"
        )
    if async_context.get("runtime.stop_reason") != "completed":
        raise AssertionError(async_context.to_dict())
    return CaseResult(
        "execution:python-sync-vs-result-key-thread",
        "PASS",
        payload={
            "main_thread": main_thread,
            "sync_thread": sync_thread,
            "async_thread": async_thread,
            "runtime_run_blocked_until_join": True,
        },
    )


def _run_python_thread_pool_boundary_case() -> CaseResult:
    from vibeflow.targets.python.runtime.engine import PipelineRuntime
    from vibeflow.targets.python.runtime.options import RuntimeOptions

    registry = _thread_probe_registry()
    graph = _thread_probe_graph(async_mode=False)
    concurrent_runtime = PipelineRuntime(
        graph,
        registry=registry,
        runtime_options=RuntimeOptions(async_max_workers=3),
    )
    barrier = threading.Barrier(4)

    def concurrent_task() -> str:
        barrier.wait(timeout=2)
        return threading.current_thread().name

    try:
        executor = concurrent_runtime._executor_for_async()
        futures = [executor.submit(concurrent_task) for _ in range(3)]
        barrier.wait(timeout=2)
        worker_names = [future.result(timeout=2) for future in futures]
    finally:
        concurrent_runtime._shutdown_executor()
    if len(set(worker_names)) != 3:
        raise AssertionError(
            f"expected three concurrent workers, got {worker_names!r}"
        )

    queued_runtime = PipelineRuntime(
        graph,
        registry=registry,
        runtime_options=RuntimeOptions(async_max_workers=1),
    )
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    queued_started = threading.Event()

    def blocker() -> str:
        blocker_started.set()
        if not release_blocker.wait(timeout=2):
            raise TimeoutError("worker release timed out")
        return "blocker"

    def queued() -> str:
        queued_started.set()
        return "queued"

    try:
        executor = queued_runtime._executor_for_async()
        blocker_future = executor.submit(blocker)
        if not blocker_started.wait(timeout=2):
            raise AssertionError("single worker did not start")
        queued_future = executor.submit(queued)
        if queued_started.wait(timeout=0.05):
            raise AssertionError("queued task ignored async_max_workers=1")
        release_blocker.set()
        if blocker_future.result(timeout=2) != "blocker":
            raise AssertionError("blocker returned an unexpected result")
        if queued_future.result(timeout=2) != "queued":
            raise AssertionError("queued task returned an unexpected result")
    finally:
        release_blocker.set()
        queued_runtime._shutdown_executor()

    rejected: list[object] = []
    for value in (0, -1, True, 1.5):
        try:
            RuntimeOptions(async_max_workers=value)
        except ValueError:
            rejected.append(value)
        else:
            raise AssertionError(
                f"invalid async_max_workers was accepted: {value!r}"
            )
    return CaseResult(
        "execution:python-thread-pool-boundaries",
        "PASS",
        payload={
            "concurrent_workers": worker_names,
            "single_worker_queued": True,
            "invalid_worker_limits_rejected": rejected,
        },
    )


def _run_valid_case(case: dict[str, Any]) -> CaseResult:
    from vibeflow.targets.python.quality.workflow import validate_graph_health
    from vibeflow.targets.python.runtime.options import RuntimeOptions
    from vibeflow.targets.python.runtime.planning import build_execution_plan
    from vibeflow.tooling.application.python.runner import run_checked
    from vibeflow.tooling.application.python.presentation.ascii_flowchart import export_ascii_flowchart
    from vibeflow.tooling.application.python.presentation.architecture_document import (
        build_architecture_document,
    )
    from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
    from vibeflow.tooling.application.python.presentation.prepared import (
        final_python_compilation,
        prepare_python_presentation,
    )
    from vibeflow.targets.python.project.check_session import python_check_scope
    from vibeflow.tooling.application.python.presentation.mermaid.render import (
        is_mermaid_svg_renderer_available,
        render_mermaid_svg,
    )
    from vibeflow.tooling.project.config_loader import load_config_document
    from vibeflow.tooling.project.config_schema import collect_config_schema_findings
    from vibeflow.tooling.application.python.project.effective_policy import resolve_effective_policy



    name = str(case["name"])
    if case.get("reset_global_state_probe"):
        from nodes import legal_global_state_nodes

        legal_global_state_nodes.reset_global_state_probe()
    config_path = CONFIG_DIR / str(case["config"])
    document = load_config_document(config_path)
    schema_findings = collect_config_schema_findings(document.data)
    if schema_findings:
        raise AssertionError(f"schema findings: {[finding.rule_id for finding in schema_findings]}")
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    from vibeflow.tooling.application.python.project.core import build_workspace_environment
    from vibeflow.tooling.application.python.workspace_service import _prepare_workspace_graph
    from vibeflow.core.findings import HealthReport
    workspace = load_workspace_config(WORKSPACE_PATH)
    environment = build_workspace_environment(workspace, config_path=config_path)
    policy_result = resolve_effective_policy(document.data, config_path=config_path, explicit_policy_path=POLICY_PATH)
    node_registry = environment.registry
    runtime_options = RuntimeOptions(**case["runtime_options"]) if "runtime_options" in case else None
    with python_check_scope(node_registry):
        prepared = _prepare_workspace_graph(config_path, workspace=workspace, env=environment, policy_override=policy_result)
        if isinstance(prepared, HealthReport):
            raise AssertionError(f"assembly failed: {prepared.to_dict()}")
        graph, resources = prepared.graph, prepared.resources
        from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context
        health = validate_graph_health(
            graph,
            registry=node_registry,
            source_context=collect_workflow_source_context(node_registry, graph),
            plugin_registry=prepared.plugin_registry,
            global_config=resources.global_config,
            purity_policy=prepared.effective_policy.to_purity_policy(),
            compilation=prepared.compilation,
        )
        allowed = set(case.get("expected_status", {"PASS", "CONCERNS"}))
        if health.status not in allowed:
            raise AssertionError(f"health status {health.status}, expected {sorted(allowed)}: {[item.to_dict() for item in health.errors]}")
        _assert_health_warnings(case, health)
        compilation = final_python_compilation(graph, node_registry)
        graph, compiled = compilation.workflow.graph, compilation.compiled_graph
        plan = build_execution_plan(graph, compiled, registry=node_registry, runtime_options=runtime_options, global_config=resources.global_config)
        _assert_execution_plan(case, plan)
        block_source_paths = _write_compiled_block_sources(name, plan)
        _assert_compiled_block_sources(case, plan, block_source_paths)
        presentation = prepare_python_presentation(graph, registry=node_registry, resources=resources, compilation=compilation)
        if case.get("expected_workflow_global_state"):
            architecture = build_architecture_document(graph, prepared=presentation)
            _assert_global_state_architecture(architecture)
        collapsed = export_mermaid(graph, health_report=health, resources=resources, prepared=presentation)
        expanded = export_mermaid(graph, expand_nodesets=True, health_report=health, resources=resources, prepared=presentation)
        ascii_collapsed = export_ascii_flowchart(graph, health_report=health, prepared=presentation)
        ascii_expanded = export_ascii_flowchart(graph, expand_nodesets=True, health_report=health, prepared=presentation)
    _assert_mermaid_contains(case, name, collapsed, expanded)
    _assert_ascii_contains(name, ascii_collapsed, ascii_expanded)
    (ASCII_DIR / f"{name}.txt").write_text(ascii_collapsed, encoding="utf-8")
    (ASCII_DIR / f"{name}.expanded.txt").write_text(ascii_expanded, encoding="utf-8")
    (MERMAID_DIR / f"{name}.mmd").write_text(collapsed, encoding="utf-8")
    (MERMAID_DIR / f"{name}.expanded.mmd").write_text(expanded, encoding="utf-8")
    if is_mermaid_svg_renderer_available():
        collapsed_svg = SVG_DIR / f"{name}.svg"
        render_mermaid_svg(collapsed, collapsed_svg)
        render_mermaid_svg(expanded, SVG_DIR / f"{name}.expanded.svg", max_text_size=500_000, max_edges=5_000)
        _assert_svg_text_contains(case, collapsed_svg)
        _assert_svg_cloud_nodes(case, collapsed_svg)
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
    if case.get("reset_global_state_probe"):
        from nodes import legal_global_state_nodes

        if legal_global_state_nodes.GLOBAL_STATE_VALUE != "configured":
            raise AssertionError(
                "global-state probe did not persist its process-local state"
            )
        if legal_global_state_nodes.GLOBAL_STATE_RUNS != 1:
            raise AssertionError(
                "global-state structural examples must not execute; expected "
                f"one runtime call, got {legal_global_state_nodes.GLOBAL_STATE_RUNS}"
            )
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
    if "expected_qualified_exec_contains" in case:
        summary = _runtime_trace_lines(run_result.run_dir)[-1]
        actual = set(summary.get("qualified_exec_order", ()))
        missing = [item for item in case["expected_qualified_exec_contains"] if item not in actual]
        if missing:
            raise AssertionError(f"qualified_exec_order missing {missing!r}, got {sorted(actual)!r}")
    if "expected_runtime_exec_order" in case:
        actual = list(run_result.context.get("runtime.exec_order"))
        if actual != case["expected_runtime_exec_order"]:
            raise AssertionError(f"runtime exec_order expected {case['expected_runtime_exec_order']!r}, got {actual!r}")
    if case.get("expected_global_state_trace"):
        _assert_global_state_trace(run_result.run_dir)
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


def _assert_svg_text_contains(case: dict[str, Any], path: Path) -> None:
    expected = [str(item) for item in case.get("expected_svg_text_contains", ())]
    if not expected:
        return
    svg_text = path.read_text(encoding="utf-8", errors="ignore")
    visible = re.sub(r"<[^>]+>", " ", svg_text)
    visible = " ".join(visible.split())
    missing = [item for item in expected if item not in visible]
    if missing:
        raise AssertionError(f"SVG {path.name} missing visible text {missing!r}")


def _assert_svg_cloud_nodes(case: dict[str, Any], path: Path) -> None:
    expected = tuple(str(item) for item in case.get("expected_svg_cloud_nodes", ()))
    if not expected:
        return
    document = ET.parse(path)
    groups = [
        element
        for element in document.getroot().iter()
        if _xml_local_name(element.tag) == "g"
    ]
    for node_id in expected:
        matches = [
            group
            for group in groups
            if node_id in group.attrib.get("id", "")
        ]
        if not matches:
            raise AssertionError(
                f"SVG {path.name} has no geometry group for {node_id!r}"
            )
        cloud = next(
            (
                group
                for group in matches
                if any(_xml_local_name(child.tag) == "path" for child in group)
            ),
            None,
        )
        if cloud is None:
            raise AssertionError(
                f"SVG {path.name} node {node_id!r} is missing cloud path geometry"
            )
        if any(_xml_local_name(child.tag) == "rect" for child in cloud):
            raise AssertionError(
                f"SVG {path.name} node {node_id!r} regressed to rect geometry"
            )


def _assert_global_state_architecture(architecture: dict[str, Any]) -> None:
    workflow = architecture["workflow"]
    if workflow.get("contains_global_state") is not True:
        raise AssertionError("Architecture did not propagate contains_global_state")
    if "root_exclusive" in workflow:
        raise AssertionError("Architecture retained removed root_exclusive metadata")
    if workflow.get("execution_lock") != {
        "key": "sandbox.global-state.serial",
        "scope": "root",
    }:
        raise AssertionError(
            "Architecture root execution lock is missing or malformed: "
            f"{workflow.get('execution_lock')!r}"
        )
    nodes = {item["id"]: item for item in workflow["nodes"]}
    state = nodes["state"]
    expected = {
        "flow_kind": "global_state",
        "effect_scope": "global_state",
        "contains_global_state": True,
        "execution_lock": {
            "key": "sandbox.global-state.serial",
            "scope": "node",
        },
    }
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise AssertionError(
            f"Architecture global-state metadata expected {expected!r}, got {actual!r}"
        )


def _assert_global_state_trace(run_dir: Path) -> None:
    events = _runtime_trace_lines(run_dir)
    kinds = [str(event["kind"]) for event in events]
    required_order = (
        "lock_wait",
        "lock_acquired",
        "global_state_enter",
        "global_state_exit",
        "lock_released",
    )
    positions = [kinds.index(kind) for kind in required_order]
    if positions != sorted(positions):
        raise AssertionError(
            f"global-state lock/transition trace order is invalid: {kinds!r}"
        )
    acquisitions = [
        event["details"]
        for event in events
        if event["kind"] == "lock_acquired"
    ]
    named = [
        item
        for item in acquisitions
        if item.get("key") == "sandbox.global-state.serial"
    ]
    if len(named) != 2 or [item.get("reentrant") for item in named] != [False, True]:
        raise AssertionError(
            f"named root/node lock reentrancy is invalid: {named!r}"
        )
    run_ids = {str(item.get("run_id", "")) for item in acquisitions}
    if len(run_ids) != 1 or "" in run_ids:
        raise AssertionError(f"lock trace does not preserve one run ID: {run_ids!r}")
    if any(float(item.get("wait_ms", -1)) < 0 for item in acquisitions):
        raise AssertionError(f"lock trace has a negative wait duration: {acquisitions!r}")


def _comparable_trace_kinds(actual: list[str], expected: list[str]) -> tuple[list[str], list[str]]:
    actual_compare = list(actual)
    expected_compare = list(expected)
    lock_kinds = {"lock_wait", "lock_acquired", "lock_released"}
    if not (lock_kinds & set(expected_compare)):
        actual_compare = [kind for kind in actual_compare if kind not in lock_kinds]
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
    if (
        "expected_portable_execution" in case
        or "expected_portable_tasks" in case
        or case.get("expected_workflow_global_state")
    ):
        portable = plan.to_workflow_plan(
            workflow_id=f"sandbox.{case['name']}"
        )
        block = portable.block(portable.entry_block)
        nodes = {node.id: node for node in block.nodes}
        for node_id, expected in dict(
            case.get("expected_portable_execution", {})
        ).items():
            node = nodes[str(node_id)]
            actual = [node.completion, node.schedule, node.executor]
            if actual != list(expected):
                raise AssertionError(
                    f"portable execution {node_id} expected "
                    f"{list(expected)!r}, got {actual!r}"
                )
        actual_tasks = [
            {
                "node_id": task.node_id,
                "schedule": task.schedule,
                "executor": task.executor,
                "result_key": task.result_key,
            }
            for task in block.tasks
        ]
        if "expected_portable_tasks" in case:
            expected_tasks = list(case["expected_portable_tasks"])
            if actual_tasks != expected_tasks:
                raise AssertionError(
                    f"portable tasks expected {expected_tasks!r}, "
                    f"got {actual_tasks!r}"
                )
        if case.get("expected_workflow_global_state"):
            if portable.abi_version != "vibeflow.workflow.v5":
                raise AssertionError(
                    f"expected WorkflowPlan v5, got {portable.abi_version!r}"
                )
            if portable.contains_global_state is not True:
                raise AssertionError("WorkflowPlan did not propagate global state")
            if "root_exclusive" in portable.to_dict():
                raise AssertionError("WorkflowPlan retained root_exclusive")
            if portable.execution_lock is None or portable.execution_lock.to_dict() != {
                "key": "sandbox.global-state.serial",
                "scope": "root",
            }:
                raise AssertionError(
                    f"WorkflowPlan root lock is invalid: {portable.execution_lock!r}"
                )
            state = block.node("state")
            if state.effect_scope != "global_state":
                raise AssertionError(
                    f"WorkflowPlan state effect scope is {state.effect_scope!r}"
                )
            if state.contains_global_state is not True:
                raise AssertionError("WorkflowPlan state does not declare global state")
            if hasattr(state, "runtime_dispatch"):
                raise AssertionError("WorkflowPlan retained retired runtime_dispatch metadata")
            if state.execution_lock is None or state.execution_lock.to_dict() != {
                "key": "sandbox.global-state.serial",
                "scope": "node",
            }:
                raise AssertionError(
                    f"WorkflowPlan state lock is invalid: {state.execution_lock!r}"
                )
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
    forbidden = tuple(str(value) for value in case.get("expected_mermaid_not_contains", ()))
    present = [value for value in forbidden if value in collapsed or value in expanded]
    if present:
        raise AssertionError(f"Mermaid contained forbidden content: {present}")


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
    forbidden = tuple(str(value) for value in case.get("expected_run_mermaid_not_contains", ()))
    present = [value for value in forbidden if value in text]
    if present:
        raise AssertionError(f"run Mermaid contained forbidden content: {present}")


def _assert_ascii_contains(name: str, collapsed: str, expanded: str) -> None:
    if "TOPOLOGY FLOWCHART" not in collapsed:
        raise AssertionError("collapsed ASCII missing header")
    if "Flow edges:" not in collapsed:
        raise AssertionError("collapsed ASCII missing flow edges")
    if "nodeset" in name and "nodeset " not in expanded:
        raise AssertionError("expanded nodeset ASCII missing nodeset section")


def _assert_artifacts(run_dir: Path) -> None:
    from vibeflow.tooling.application.python.presentation.mermaid.render import (
        is_mermaid_svg_renderer_available,
    )

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
        _assert_report_has_rule(report["findings"], str(case["expect"]))
        return CaseResult(f"invalid:base_lib:{case['expect']}", "PASS"), report
    if kind == "base_lib_chain":
        report = base_lib_report or _bad_base_lib_report()
        summary = report["chain"]
        if summary.length <= int(case["expect_length_gt"]):
            raise AssertionError(f"expected deep chain > {case['expect_length_gt']}, got {summary.length}")
        from dataclasses import asdict
        return CaseResult("invalid:base_lib_chain", "PASS", payload=asdict(summary)), report
    if kind == "config":
        return _invalid_config(case), base_lib_report
    if kind == "concerns":
        return _concern_config(case), base_lib_report
    if kind == "run":
        return _invalid_run(case), base_lib_report
    if kind == "runtime_run":
        return _invalid_runtime_run(case), base_lib_report
    raise AssertionError(f"unknown invalid case kind: {kind}")


def _inspect_invalid_node(case: dict[str, Any], kind: str) -> CaseResult:
    from vibeflow.targets.python.quality.source_analysis import PurityPolicy
    from vibeflow.tooling.project.descriptor_loader import load_workflow_plugins, DescriptorLoadError
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    negative = PROJECT_DIR / "negative_plugins" / (str(case["class"]) + ".py")
    if negative.exists():
        config = negative.with_suffix(".workflow.jsonc")
        config.write_text(json.dumps({"plugins":[{"source":{"kind":"file","ref":negative.relative_to(PROJECT_DIR).as_posix()}}]}))
        try:
            load_workflow_plugins(load_workspace_config(WORKSPACE_PATH), config)
        except DescriptorLoadError as exc:
            if str(case["expect"]).lower() not in str(exc).lower():
                raise AssertionError(f"expected declaration error {case['expect']}: {exc}") from exc
            return CaseResult(f"invalid:inspect_node:{case['class']}", "PASS", str(exc))
        raise AssertionError("invalid SDK declaration was accepted")
    policy = PurityPolicy(max_source_lines=500, warn_source_lines=None)
    if kind == "inspect_node_small_source":
        policy = PurityPolicy(max_source_lines=10)
    elif kind == "inspect_node_warn":
        policy = PurityPolicy(max_source_lines=500, warn_call_chain_length=4, max_call_chain_length=99)
    violations = _node_source_report(str(case["type"]), policy=policy)
    if case.get("remaining_expect"):
        _assert_violations_have_rule(violations, case["remaining_expect"])
        assert not any(item.rule_id == case["retired_expect"] for item in violations)
    elif case.get("allowed"):
        assert not [item for item in violations if item.severity == "error"], violations
    else:
        _assert_violations_have_rule(violations, str(case["expect"]))
    return CaseResult(f"invalid:inspect_node:{case['class']}", "PASS", payload={"rules": [item.rule_id for item in violations]})


def _runtime_invalid_node(case: dict[str, Any]) -> CaseResult:
    from vibeflow.core import DataProvider, DataRequirement, EdgeSpec, GraphConfig, NodeSpec
    from vibeflow.targets.python.project import NodeRegistry
    from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor
    from vibeflow.targets.python.runtime.engine import PipelineRuntime

    RuntimeStartNode_DECLARATION = _node_declaration(NodeDescriptor(type_key='sandbox.runtime_start', display_name='Runtime Start', description='runtime test start', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(examples=({'inputs': {}, 'params': {}},)))
    class RuntimeStartNode:

        def run_pure(self, inputs, params):
            return {}

    RuntimeEndNode_DECLARATION = _node_declaration(NodeDescriptor(type_key='sandbox.runtime_end', display_name='Runtime End', description='runtime test end', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('bad.out', 'exactly_one', display_name='bad.out'),), input_semantics={'bad.out': ('bad output',)}, examples=({'inputs': {'bad.out': 1}, 'params': {}},)))
    class RuntimeEndNode:

        def run_pure(self, inputs, params):
            return {}

    cls = _load_class(PROJECT_DIR / str(case["module"]), str(case["class"]))
    registry = NodeRegistry()
    registry.register(RuntimeStartNode_DECLARATION, RuntimeStartNode)
    registry.register(RuntimeEndNode_DECLARATION, RuntimeEndNode)
    registry.register(_project_registry().descriptor(str(case["type"])), cls)
    graph = GraphConfig(
        nodes=(
            NodeSpec(id="start", type_used="sandbox.runtime_start"),
            NodeSpec(id="bad", type_used=str(case["type"]), provides=(DataProvider("bad.out", "bad.out", display_name="bad.out"),)),
            NodeSpec(id="end", type_used="sandbox.runtime_end", requires=(DataRequirement("bad.out", "exactly_one", display_name="bad.out"),)),
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
    from vibeflow.core import DataProvider, GraphConfig, NodeSpec
    from vibeflow.targets.python.project import NodeRegistry
    from vibeflow.targets.python.quality.source_analysis import PurityPolicy
    from vibeflow.targets.python.quality.workflow import validate_graph_health
    from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context

    registry = _project_registry()
    graph = GraphConfig(nodes=(NodeSpec(id="bad", type_used=str(case["type"]), provides=(DataProvider("bad.out", "bad.out", display_name="bad.out"),)),))
    policy = PurityPolicy(
        warn_dependency_chain_length=2,
        max_dependency_chain_length=4,
    )
    report = validate_graph_health(
        graph,
        registry=registry,
        source_context=collect_workflow_source_context(registry, graph),
        purity_policy=policy,
    )
    _assert_report_has_rule([item.to_dict() for item in (*report.errors, *report.warnings)], str(case["expect"]))
    return CaseResult(f"invalid:health_node:{case['class']}", "PASS", payload=report.to_dict())


def _bad_base_lib_report():
    """Review explicit library declarations through the ordinary Rule engine."""
    from vibeflow.core.descriptors.decode import decode_resource
    from vibeflow.targets.shared.quality_support.implementation import analyze_call_graph
    from vibeflow.core.rules import RuleContext, compile_ruleset, execute_rule_plan
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, build_python_source_context
    from vibeflow.targets.python.quality.source_analysis import PurityPolicy
    from vibeflow.targets.python.quality.rule_adapter import rule_resources
    from vibeflow.targets.python.project.source_membership import source_ownership
    registry = _project_registry()
    policy = PurityPolicy(max_source_lines=20, max_functions=3, max_branches=4,
                          banned_import_roots=("subprocess",))
    paths = sorted((PROJECT_DIR / "bad_base_lib").glob("*.py"))
    declarations = [decode_resource({"kind":"base_lib", "id":path.stem,
        "display_name":path.stem, "description":"One explicit negative library", "rulesets":["vibeflow.base_lib"],
        "dependencies":[item.stem for item in paths if item != path],
        "implementations":[{"language":"python", "targets":["python"], "source":{
            "kind":"file", "ref":path.relative_to(PROJECT_DIR).as_posix()}}]}) for path in paths]
    files = [PythonSourceFile.parse(str(path), "bad_base_lib." + path.stem, path.read_text()) for path in paths]
    # Include the actual registered Node entry targeted by the negative import.
    from vibeflow.tooling.application.python.project.declarations import collect_node_source_context
    nodes = collect_node_source_context(registry, registry.available())
    sources = build_python_source_context((), (*files, *nodes.files))
    owners = [*source_ownership(registry).get("source_owners", ())]
    owners.extend({"path":str(path), "kind":"base_lib", "id":path.stem, "role":"entry", "symbol":"",
                   "base_libs":[], "dependencies":[item.stem for item in paths if item != path]} for path in paths)
    rules, rulesets = rule_resources(registry, purity_policy=policy)
    findings = []
    for phase in ("import", "static"):
        plan = compile_ruleset("vibeflow.base_lib", rules=rules, rulesets=rulesets, entrypoint=phase)
        handlers = registry.rule_handler_loader(plan)
        for descriptor, source in zip(declarations, files):
            result = execute_rule_plan(plan, RuleContext(facts={"source_context":sources,
                "resource_source_file":source, "base_lib_file":source, "resource_symbol":"",
                "source_owners":owners, "purity_policy":policy}, subject={"kind":"base_lib", "id":descriptor.id,
                "descriptor":descriptor.to_dict()}, phase=phase, target="python"), handlers=handlers)
            findings.extend(item.to_dict() for item in result.findings)
    local = {source.path:source.module for source in files}
    graph = {source.module:tuple(local[item.resolved_path] for item in sources.imports
        if item.path == source.path and item.resolved_path in local) for source in files}
    return {"findings":findings, "chain":analyze_call_graph(graph,entry="bad_base_lib.deep_chain_a")}


def _invalid_config(case: dict[str, Any]) -> CaseResult:
    from vibeflow.tooling.application.python.cli.config import validate_config_path

    report = validate_config_path(CONFIG_DIR / str(case["config"]), policy_path=POLICY_PATH)
    if report.status not in {"FAIL", "ERROR"}:
        raise AssertionError(f"config case was not rejected: {report.status}")
    _assert_report_has_rule([item.to_dict() for item in (*report.errors, *report.warnings)], str(case["expect"]))
    return CaseResult(f"invalid:config:{case['config']}", "PASS", payload=report.to_dict())


def _concern_config(case: dict[str, Any]) -> CaseResult:
    from vibeflow.tooling.application.python.cli.config import validate_config_path
    report = validate_config_path(CONFIG_DIR / str(case["config"]), policy_path=POLICY_PATH)
    if report.status not in {"CONCERNS", "FAIL", "ERROR"}:
        raise AssertionError(f"concern case had status {report.status}")
    findings = [item.to_dict() for item in (*report.errors, *report.warnings)]
    _assert_report_has_rule(findings, str(case["expect"]))
    matches = [item for item in findings if item.get("rule_id") == case["expect"]]
    if not matches:
        raise AssertionError(f"concern case missing exact rule {case['expect']}")
    details = matches[0].get("details", {})
    missing = [field for field in case.get("details", ()) if field not in details]
    if missing:
        raise AssertionError(f"concern details missing {missing}: {details}")
    return CaseResult(f"invalid:concerns:{case['config']}", "PASS", payload=report.to_dict())


def _invalid_run(case: dict[str, Any]) -> CaseResult:
    from vibeflow.targets.python.runtime.options import RuntimeOptions
    from vibeflow.tooling.application.python.runner import CheckedRunError, run_checked

    try:
        runtime_options = RuntimeOptions(**case["runtime_options"]) if "runtime_options" in case else None
        run_checked(
            CONFIG_DIR / str(case["config"]),
            registry=_project_registry(),
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


def _invalid_runtime_run(case: dict[str, Any]) -> CaseResult:
    from vibeflow.targets.python.runtime.options import RuntimeOptions
    from vibeflow.tooling.application.python.runner import run_checked

    runtime_options = RuntimeOptions(**case["runtime_options"]) if "runtime_options" in case else None
    initial = case["initial_factory"]() if "initial_factory" in case else case.get("initial", {})
    try:
        run_checked(
            CONFIG_DIR / str(case["config"]),
            registry=_project_registry(),
            initial=initial,
            policy_path=POLICY_PATH,
            run_root=RUN_ROOT,
            run_id=f"expected_runtime_fail_{Path(str(case['config'])).stem}",
            runtime_options=runtime_options,
        )
    except Exception as exc:
        text = str(exc)
        if str(case["expect"]) not in text:
            raise AssertionError(f"runtime run error did not include {case['expect']}: {text}") from exc
        return CaseResult(f"invalid:runtime_run:{case['config']}", "PASS", text)
    raise AssertionError("runtime run case was not rejected")


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
