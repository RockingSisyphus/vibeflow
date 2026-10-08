"""Runtime conformance tests for global-state leases and named locks."""

from __future__ import annotations
from tests.fixtures.support.declarations import node_declaration, configured_declaration

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time

import pytest

from tests.fixtures.support.strict_support import (
    PROV_SPEC,
    REQ_SPEC,
    _edge_chain,
    _node_call,
    _nodeset_config,
    _registry,
    register_node,
)
from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.core.compiler import GraphCompileError
from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.runtime import PipelineRuntime
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
from vibeflow.tooling.project.graph_config import parse_graph_config


class _GateState:
    lock = threading.Lock()
    entered = threading.Event()
    release = threading.Event()
    barrier: threading.Barrier | None = None
    active = 0
    maximum = 0

    @classmethod
    def reset(cls, *, parties: int = 0) -> None:
        cls.entered = threading.Event()
        cls.release = threading.Event()
        cls.barrier = threading.Barrier(parties) if parties else None
        cls.active = 0
        cls.maximum = 0

    @classmethod
    def run(cls, *, wait_for_release: bool = False) -> None:
        with cls.lock:
            cls.active += 1
            cls.maximum = max(cls.maximum, cls.active)
        cls.entered.set()
        try:
            if cls.barrier is not None:
                cls.barrier.wait(timeout=2)
            if wait_for_release:
                cls.release.wait(timeout=2)
            else:
                time.sleep(0.08)
        finally:
            with cls.lock:
                cls.active -= 1


class _WriterPreferenceState:
    first_entered = threading.Event()
    release_first = threading.Event()
    writer_entered = threading.Event()
    release_writer = threading.Event()
    follower_entered = threading.Event()

    @classmethod
    def reset(cls) -> None:
        cls.first_entered = threading.Event()
        cls.release_first = threading.Event()
        cls.writer_entered = threading.Event()
        cls.release_writer = threading.Event()
        cls.follower_entered = threading.Event()


class _ProtectedTaskState:
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    @classmethod
    def reset(cls) -> None:
        cls.entered = threading.Event()
        cls.release = threading.Event()
        cls.finished = threading.Event()


NormalGateNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.normal_gate', display_name='Normal Gate', description='Blocks a normal root for lock coordination tests.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.process",))

class NormalGateNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _GateState.run(wait_for_release=True)
        return {}


ParallelProbeNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.parallel_probe', display_name='Parallel Probe', description='Measures overlapping root execution.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.process",))

class ParallelProbeNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _GateState.run()
        return {}


GlobalProbeNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.global_probe', display_name='Global Probe', description='Touches ambient interpreter state for runtime lock tests.', version='0.1.0', flow_kind='global_state', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.global_state",))

class GlobalProbeNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _GateState.run()
        return {}


BlockingNormalNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.blocking_normal', display_name='Blocking Normal', description='Holds one shared root admission.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.process",))

class BlockingNormalNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _WriterPreferenceState.first_entered.set()
        _WriterPreferenceState.release_first.wait(timeout=2)
        return {}


HoldingGlobalNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.holding_global', display_name='Holding Global', description='Holds the exclusive global-state admission.', version='0.1.0', flow_kind='global_state', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.global_state",))

class HoldingGlobalNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _WriterPreferenceState.writer_entered.set()
        _WriterPreferenceState.release_writer.wait(timeout=2)
        return {}


FollowingNormalNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.following_normal', display_name='Following Normal', description='Attempts shared admission behind a waiting writer.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.process",))

class FollowingNormalNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _WriterPreferenceState.follower_entered.set()
        return {}


GlobalFailureNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.global_failure', display_name='Global Failure', description='Fails after ambient state may have changed.', version='0.1.0', flow_kind='global_state', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.global_state",))

class GlobalFailureNode:

    def run_pure(self, inputs, params):
        del inputs, params
        raise RuntimeError("global boom")


GlobalInterruptNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.global_interrupt', display_name='Global Interrupt', description='Simulates cancellation after ambient state may have changed.', version='0.1.0', flow_kind='global_state', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.global_state",))

class GlobalInterruptNode:

    def run_pure(self, inputs, params):
        del inputs, params
        raise KeyboardInterrupt("global cancelled")


GlobalNoopNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.global_noop', display_name='Global Noop', description='Marks a root as global-state protected without delaying it.', version='0.1.0', flow_kind='global_state', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.global_state",))

class GlobalNoopNode:

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


GlobalWorkerLeftNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.global_worker_left', display_name='Global Worker Left', description='Runs one managed global-state worker.', version='0.1.0', flow_kind='global_state', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('worker.left', 'worker.left', display_name='worker.left'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('worker.left', 'worker.left', display_name='worker.left'),)}), rulesets=("vibeflow.global_state",))

class GlobalWorkerLeftNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _GateState.run()
        return {"worker.left": True}


GlobalWorkerRightNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.global_worker_right', display_name='Global Worker Right', description='Runs another managed global-state worker.', version='0.1.0', flow_kind='global_state', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('worker.right', 'worker.right', display_name='worker.right'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('worker.right', 'worker.right', display_name='worker.right'),)}), rulesets=("vibeflow.global_state",))

class GlobalWorkerRightNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _GateState.run()
        return {"worker.right": True}


OrdinaryWorkerNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.ordinary_worker', display_name='Ordinary Worker', description='Runs one ordinary managed result worker.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('worker.left', 'worker.left', display_name='worker.left'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('worker.left', 'worker.left', display_name='worker.left'),)}), rulesets=("vibeflow.process",))

class OrdinaryWorkerNode:

    def run_pure(self, inputs, params):
        del inputs, params
        return {"worker.left": True}


WorkerLeftJoinNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.worker_left_join', display_name='Worker Left Join', description='Joins one ordinary worker result.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('worker.left', 'exactly_one', display_name='worker.left'),), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('worker.left', 'exactly_one', display_name='worker.left'),)}), rulesets=("vibeflow.process",))

class WorkerLeftJoinNode:

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


ProtectedSlowResultNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.protected_slow_result', display_name='Protected Slow Result', description='Waits so failure cleanup must retain an inherited lease.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('protected.result', 'protected.result', display_name='protected.result'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('protected.result', 'protected.result', display_name='protected.result'),)}), rulesets=("vibeflow.process",))

class ProtectedSlowResultNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _ProtectedTaskState.entered.set()
        try:
            _ProtectedTaskState.release.wait(timeout=2)
            return {"protected.result": True}
        finally:
            _ProtectedTaskState.finished.set()


ProtectedJoinNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.protected_join', display_name='Protected Join', description='Joins a protected result and a second branch.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('protected.result', 'exactly_one', display_name='protected.result'), DataRequirement('value.out', 'exactly_one', display_name='value.out')), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('protected.result', 'exactly_one', display_name='protected.result'), DataRequirement('value.out', 'exactly_one', display_name='value.out'))}), rulesets=("vibeflow.process",))

class ProtectedJoinNode:

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


CoordinatedFailureNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.coordinated_failure', display_name='Coordinated Failure', description='Fails only after the sibling protected worker has started.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('value.out', 'value.out', display_name='value.out'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('value.out', 'value.out', display_name='value.out'),)}), rulesets=("vibeflow.process",))

class CoordinatedFailureNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _ProtectedTaskState.entered.wait(timeout=2)
        raise RuntimeError("coordinated boom")


UnrelatedDetachedNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.unrelated_detached', display_name='Unrelated Detached', description="Waits outside a sibling node's named lock scope.", version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.process",))

class UnrelatedDetachedNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _ProtectedTaskState.entered.set()
        try:
            _ProtectedTaskState.release.wait(timeout=2)
            return {}
        finally:
            _ProtectedTaskState.finished.set()


WorkerJoinNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.worker_join', display_name='Worker Join', description='Joins both managed worker results before root completion.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('worker.left', 'exactly_one', display_name='worker.left'), DataRequirement('worker.right', 'exactly_one', display_name='worker.right')), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('worker.left', 'exactly_one', display_name='worker.left'), DataRequirement('worker.right', 'exactly_one', display_name='worker.right'))}), rulesets=("vibeflow.process",))

class WorkerJoinNode:

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


DelayedResultNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.delayed_result', display_name='Delayed Result', description='Occupies the sole managed worker before a late global task.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('late.normal', 'late.normal', display_name='late.normal'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('late.normal', 'late.normal', display_name='late.normal'),)}), rulesets=("vibeflow.process",))

class DelayedResultNode:

    def run_pure(self, inputs, params):
        del inputs, params
        time.sleep(0.08)
        return {"late.normal": True}


LateGlobalResultNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.late_global_result', display_name='Late Global Result', description='Starts only while failure cleanup drains managed work.', version='0.1.0', flow_kind='global_state', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('late.global', 'late.global', display_name='late.global'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('late.global', 'late.global', display_name='late.global'),)}), rulesets=("vibeflow.global_state",))

class LateGlobalResultNode:

    def run_pure(self, inputs, params):
        del inputs, params
        return {"late.global": True}


LateJoinNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.late_join', display_name='Late Join', description='Provides a provable join path for cleanup tasks.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('late.normal', 'exactly_one', display_name='late.normal'), DataRequirement('late.global', 'exactly_one', display_name='late.global'), DataRequirement('value.out', 'exactly_one', display_name='value.out')), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('late.normal', 'exactly_one', display_name='late.normal'), DataRequirement('late.global', 'exactly_one', display_name='late.global'), DataRequirement('value.out', 'exactly_one', display_name='value.out'))}), rulesets=("vibeflow.process",))

class LateJoinNode:

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


EarlyQuickResultNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.early_quick_result', display_name='Early Quick Result', description='Completes the branch whose terminal ends the root early.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('early.quick', 'early.quick', display_name='early.quick'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('early.quick', 'early.quick', display_name='early.quick'),)}), rulesets=("vibeflow.process",))

class EarlyQuickResultNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _ProtectedTaskState.entered.wait(timeout=2)
        return {"early.quick": True}


EarlySlowResultNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.early_slow_result', display_name='Early Slow Result', description='Keeps an unselected result branch active during early termination.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('early.slow', 'early.slow', display_name='early.slow'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('early.slow', 'early.slow', display_name='early.slow'),)}), rulesets=("vibeflow.process",))

class EarlySlowResultNode:

    def run_pure(self, inputs, params):
        del inputs, params
        _ProtectedTaskState.entered.set()
        try:
            _ProtectedTaskState.release.wait(timeout=2)
            return {"early.slow": True}
        finally:
            _ProtectedTaskState.finished.set()


EarlyQuickEndNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.early_quick_end', display_name='Early Quick End', description='Ends the root after consuming only the quick branch.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('early.quick', 'exactly_one', display_name='early.quick'),), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('early.quick', 'exactly_one', display_name='early.quick'),)}), rulesets=("vibeflow.process",))

class EarlyQuickEndNode:

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


EarlySlowEndNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.early_slow_end', display_name='Early Slow End', description='Provides the statically visible join path for the slow branch.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('early.slow', 'exactly_one', display_name='early.slow'),), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('early.slow', 'exactly_one', display_name='early.slow'),)}), rulesets=("vibeflow.process",))

class EarlySlowEndNode:

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


def _runtime(
    node_type: str,
    run_dir: Path,
    *,
    root_lock: str = "",
    node_lock: str = "",
    execution: str = "plan",
    trace: str = "full",
) -> PipelineRuntime:
    registry = _registry()
    register_node(registry, NormalGateNode_DECLARATION, NormalGateNode)
    register_node(registry, ParallelProbeNode_DECLARATION, ParallelProbeNode)
    register_node(registry, GlobalProbeNode_DECLARATION, GlobalProbeNode)
    register_node(registry, GlobalFailureNode_DECLARATION, GlobalFailureNode)
    register_node(registry, GlobalInterruptNode_DECLARATION, GlobalInterruptNode)
    register_node(registry, BlockingNormalNode_DECLARATION, BlockingNormalNode)
    register_node(registry, HoldingGlobalNode_DECLARATION, HoldingGlobalNode)
    register_node(registry, FollowingNormalNode_DECLARATION, FollowingNormalNode)
    middle = _node_call(
        "work",
        node_type,
        "Runs the execution-lock probe.",
    )
    if node_lock:
        middle["execution_lock"] = {"key": node_lock}
    pipeline = {
        "nodes": [
            _node_call("start", "test.start", "Starts the probe."),
            middle,
            _node_call("end", "test.start", "Ends the probe."),
        ],
        "edges": _edge_chain("start", "work", "end"),
    }
    if root_lock:
        pipeline["execution_lock"] = {"key": root_lock}
    return PipelineRuntime(
        parse_graph_config({"pipeline": pipeline}),
        registry=registry,
        run_dir=run_dir,
        runtime_options={"execution": execution, "trace": trace},
    )


def _events(result) -> list[dict[str, object]]:
    path = Path(result.get("runtime.trace_path"))
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_unlocked_normal_and_global_state_roots_can_overlap(
    tmp_path: Path,
) -> None:
    _GateState.reset(parties=2)
    normal_a = _runtime("test.parallel_probe", tmp_path / "normal-a")
    normal_b = _runtime("test.parallel_probe", tmp_path / "normal-b")
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(normal_a.run)
        second = executor.submit(normal_b.run)
        first.result(timeout=3)
        second.result(timeout=3)
    assert _GateState.maximum == 2

    _GateState.reset(parties=2)
    global_a = _runtime("test.global_probe", tmp_path / "global-a")
    global_b = _runtime("test.global_probe", tmp_path / "global-b")
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(global_a.run)
        second = executor.submit(global_b.run)
        first_result = first.result(timeout=3)
        second_result = second.result(timeout=3)
    assert _GateState.maximum == 2
    for result in (first_result, second_result):
        kinds = [item["kind"] for item in _events(result)]
        assert kinds.index("global_state_enter") < kinds.index("global_state_exit")
        assert not {"lock_wait", "lock_acquired", "lock_released"} & set(kinds)


@pytest.mark.parametrize("execution", ("plan", "block", "compiled"))
def test_global_state_scope_runs_under_every_python_execution_mode(
    tmp_path: Path,
    execution: str,
) -> None:
    _GateState.reset()
    runtime = _runtime(
        "test.global_probe",
        tmp_path / execution,
        execution=execution,
    )

    result = runtime.run()

    events = _events(result)
    kinds = [event["kind"] for event in events]
    assert kinds.index("global_state_enter") < kinds.index("global_state_exit")
    assert not {"lock_wait", "lock_acquired", "lock_released"} & set(kinds)
    entered = next(event for event in events if event["kind"] == "global_state_enter")
    assert entered["details"]["domain"] is None
    assert entered["details"]["scope"] is None


@pytest.mark.parametrize("trace", ("full", "boundary"))
def test_unlocked_global_state_has_no_lock_events_in_enabled_trace_modes(
    tmp_path: Path,
    trace: str,
) -> None:
    _GateState.reset()
    result = _runtime(
        "test.global_probe",
        tmp_path / trace,
        trace=trace,
    ).run()

    kinds = [event["kind"] for event in _events(result)]
    assert kinds.index("global_state_enter") < kinds.index("global_state_exit")
    assert not {"lock_wait", "lock_acquired", "lock_released"} & set(kinds)


def test_global_state_lock_events_are_suppressed_when_trace_is_off(
    tmp_path: Path,
) -> None:
    _GateState.reset()
    result = _runtime(
        "test.global_probe",
        tmp_path / "off",
        trace="off",
    ).run()

    assert result.get("runtime.event_count") == 0
    assert [event["kind"] for event in _events(result)] == [
        "runtime_summary"
    ]


def test_same_named_root_lock_blocks_until_holder_finishes(
    tmp_path: Path,
) -> None:
    _GateState.reset()
    lock_key = "project.shared-state"
    normal = _runtime(
        "test.normal_gate",
        tmp_path / "normal",
        root_lock=lock_key,
    )
    global_runtime = _runtime(
        "test.global_probe",
        tmp_path / "global",
        root_lock=lock_key,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        normal_future = executor.submit(normal.run)
        assert _GateState.entered.wait(timeout=2)
        _GateState.entered.clear()
        global_future = executor.submit(global_runtime.run)
        assert not _GateState.entered.wait(timeout=0.1)
        _GateState.release.set()
        normal_future.result(timeout=3)
        global_result = global_future.result(timeout=3)
    assert any(
        event["kind"] == "lock_acquired"
        and event.get("details", {}).get("mode") == "exclusive"
        and event.get("details", {}).get("wait_ms", 0) > 0
        for event in _events(global_result)
    )


def test_different_named_root_lock_bypasses_waiting_domain(
    tmp_path: Path,
) -> None:
    _WriterPreferenceState.reset()
    first = _runtime(
        "test.blocking_normal",
        tmp_path / "first-holder",
        root_lock="project.busy",
    )
    writer = _runtime(
        "test.holding_global",
        tmp_path / "waiter",
        root_lock="project.busy",
    )
    follower = _runtime(
        "test.following_normal",
        tmp_path / "independent",
        root_lock="project.independent",
    )

    with ThreadPoolExecutor(max_workers=3) as executor:
        first_future = executor.submit(first.run)
        assert _WriterPreferenceState.first_entered.wait(timeout=2)
        writer_future = executor.submit(writer.run)

        writer_trace = tmp_path / "waiter" / "runtime_trace.jsonl"
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if writer_trace.is_file() and '"lock_wait"' in writer_trace.read_text(encoding="utf-8"):
                break
            time.sleep(0.01)
        else:
            pytest.fail("same-domain root never reached its lock wait")

        follower_future = executor.submit(follower.run)
        assert _WriterPreferenceState.follower_entered.wait(timeout=2)
        follower_future.result(timeout=3)
        assert not _WriterPreferenceState.writer_entered.is_set()

        _WriterPreferenceState.release_first.set()
        assert _WriterPreferenceState.writer_entered.wait(timeout=2)

        _WriterPreferenceState.release_writer.set()
        first_future.result(timeout=3)
        writer_future.result(timeout=3)

    assert _WriterPreferenceState.follower_entered.is_set()


def test_named_locks_serialize_same_key_and_allow_different_keys(
    tmp_path: Path,
) -> None:
    _GateState.reset()
    same_a = _runtime(
        "test.parallel_probe",
        tmp_path / "same-a",
        root_lock="project.resource",
    )
    same_b = _runtime(
        "test.parallel_probe",
        tmp_path / "same-b",
        root_lock="project.resource",
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(same_a.run)
        second = executor.submit(same_b.run)
        first.result(timeout=3)
        second.result(timeout=3)
    assert _GateState.maximum == 1

    _GateState.reset(parties=2)
    different_a = _runtime(
        "test.parallel_probe",
        tmp_path / "different-a",
        root_lock="project.left",
    )
    different_b = _runtime(
        "test.parallel_probe",
        tmp_path / "different-b",
        root_lock="project.right",
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(different_a.run)
        second = executor.submit(different_b.run)
        first.result(timeout=3)
        second.result(timeout=3)
    assert _GateState.maximum == 2


def test_nested_graph_lock_is_traced_as_block_scope(tmp_path: Path) -> None:
    lock_key = "project.child-block"
    graph = parse_graph_config(
        {
            "nodesets": [
                {
                    "type_key": "test.locked_child",
                    "display_name": "Locked Child",
                    "description": "Uses a block-scoped execution lock.",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            _node_call(
                                "child_start",
                                "test.start",
                                "Starts the locked child.",
                            ),
                            _node_call(
                                "probe",
                                "test.parallel_probe",
                                "Runs inside the locked child.",
                            ),
                            _node_call(
                                "child_end",
                                "test.start",
                                "Completes the locked child.",
                            )
                        ],
                        "edges": _edge_chain(
                            "child_start",
                            "probe",
                            "child_end",
                        ),
                    },
                }
            ],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the root."),
                    _node_call(
                        "child",
                        "test.locked_child",
                        "Runs the locked child block.",
                        execution_lock={"key": lock_key},
                    ),
                    _node_call("end", "test.start", "Ends the root."),
                ],
                "edges": _edge_chain("start", "child", "end"),
            },
        }
    )

    registry = _registry()
    register_node(registry, ParallelProbeNode_DECLARATION, ParallelProbeNode)
    first_runtime = PipelineRuntime(
        graph,
        registry=registry,
        run_dir=tmp_path / "block-scope-a",
    )
    second_runtime = PipelineRuntime(
        graph,
        registry=registry,
        run_dir=tmp_path / "block-scope-b",
    )

    _GateState.reset()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_runtime.run)
        second = executor.submit(second_runtime.run)
        results = (first.result(timeout=3), second.result(timeout=3))

    assert _GateState.maximum == 1

    for result in results:
        lock_events = [
            event
            for event in _events(result)
            if event["kind"]
            in {"lock_wait", "lock_acquired", "lock_released"}
            and event.get("details", {}).get("key") == lock_key
        ]
        assert [event["kind"] for event in lock_events] == [
            "lock_wait",
            "lock_acquired",
            "lock_released",
        ]
        assert {event["details"]["scope"] for event in lock_events} == {
            "block"
        }


def test_same_named_lock_reenters_and_different_nested_key_is_rejected(
    tmp_path: Path,
) -> None:
    _GateState.reset()
    runtime = _runtime(
        "test.parallel_probe",
        tmp_path / "reentrant",
        root_lock="project.resource",
        node_lock="project.resource",
    )
    result = runtime.run()
    acquisitions = [
        event
        for event in _events(result)
        if event["kind"] == "lock_acquired"
        and event.get("details", {}).get("key") == "project.resource"
    ]
    assert len(acquisitions) == 2
    assert acquisitions[1]["details"]["reentrant"] is True

    with pytest.raises(
        GraphCompileError,
        match="GRAPH.EXECUTION_LOCK.NESTED_KEY_CONFLICT",
    ):
        _runtime(
            "test.parallel_probe",
            tmp_path / "bad-nested",
            root_lock="project.outer",
            node_lock="project.inner",
        )


def test_failure_reports_possible_state_change_and_releases_the_lease(
    tmp_path: Path,
) -> None:
    lock_key = "project.failure"
    failing = _runtime(
        "test.global_failure",
        tmp_path / "failure",
        root_lock=lock_key,
    )

    with pytest.raises(RuntimeError, match="global boom"):
        failing.run()

    failure_events = [
        json.loads(line)
        for line in (tmp_path / "failure" / "runtime_trace.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    kinds = [event["kind"] for event in failure_events]
    assert kinds.index("global_state_may_have_changed") < kinds.index(
        "lock_released"
    )

    # A second exclusive root completing proves the process-wide coordinator
    # did not retain the failed run's lease.
    _GateState.reset()
    recovered = _runtime(
        "test.global_probe",
        tmp_path / "recovered",
        root_lock=lock_key,
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(recovered.run).result(timeout=3)


def test_base_exception_cancellation_reports_state_change_and_releases_lease(
    tmp_path: Path,
) -> None:
    lock_key = "project.interrupt"
    interrupted = _runtime(
        "test.global_interrupt",
        tmp_path / "interrupted",
        root_lock=lock_key,
    )

    with pytest.raises(KeyboardInterrupt, match="global cancelled"):
        interrupted.run()

    kinds = [
        event["kind"]
        for event in [
            json.loads(line)
            for line in (tmp_path / "interrupted" / "runtime_trace.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
    ]
    assert kinds.index("global_state_may_have_changed") < kinds.index(
        "lock_released"
    )

    _GateState.reset()
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(
            _runtime(
                "test.global_probe",
                tmp_path / "after-interrupt",
                root_lock=lock_key,
            ).run
        ).result(timeout=3)


def test_global_state_root_keeps_joined_managed_workers_parallel(
    tmp_path: Path,
) -> None:
    registry = _registry()
    register_node(registry, GlobalWorkerLeftNode_DECLARATION, GlobalWorkerLeftNode)
    register_node(registry, GlobalWorkerRightNode_DECLARATION, GlobalWorkerRightNode)
    register_node(registry, WorkerJoinNode_DECLARATION, WorkerJoinNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts both workers."),
                    _node_call(
                        "left",
                        "test.global_worker_left",
                        "Runs the left worker.",

                        result_key="worker.left",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "right",
                        "test.global_worker_right",
                        "Runs the right worker.",

                        result_key="worker.right",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "join",
                        "test.worker_join",
                        "Joins both workers.",

                        join_policy="all",
                    ),
                ],
                "edges": [
                    {"from": "start", "to": "left"},
                    {"from": "start", "to": "right"},
                    {"from": "left", "to": "join"},
                    {"from": "right", "to": "join"},
                ],
            }
        }
    )
    runtime = PipelineRuntime(graph, registry=registry, run_dir=tmp_path / "parallel")

    _GateState.reset(parties=2)
    result = runtime.run()

    assert _GateState.maximum == 2
    kinds = [event["kind"] for event in _events(result)]
    assert kinds.count("async_result_join") == 2
    assert "lock_released" not in kinds
    assert kinds[-1] == "runtime_summary"


@pytest.mark.parametrize(
    ("left_key", "right_key", "expected_maximum"),
    (
        ("project.shared", "project.shared", 1),
        ("project.left", "project.right", 2),
    ),
)
def test_parallel_sibling_node_locks_use_logical_scope_reentrancy(
    tmp_path: Path,
    left_key: str,
    right_key: str,
    expected_maximum: int,
) -> None:
    registry = _registry()
    register_node(registry, GlobalWorkerLeftNode_DECLARATION, GlobalWorkerLeftNode)
    register_node(registry, GlobalWorkerRightNode_DECLARATION, GlobalWorkerRightNode)
    register_node(registry, WorkerJoinNode_DECLARATION, WorkerJoinNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts both workers."),
                    {
                        **_node_call(
                            "left",
                            "test.global_worker_left",
                            "Runs the left locked worker.",

                            result_key="worker.left",
                            **{"async": "result_key"},
                        ),
                        "execution_lock": {"key": left_key},
                    },
                    {
                        **_node_call(
                            "right",
                            "test.global_worker_right",
                            "Runs the right locked worker.",

                            result_key="worker.right",
                            **{"async": "result_key"},
                        ),
                        "execution_lock": {"key": right_key},
                    },
                    _node_call(
                        "join",
                        "test.worker_join",
                        "Joins both locked workers.",

                        join_policy="all",
                    ),
                ],
                "edges": [
                    {"from": "start", "to": "left"},
                    {"from": "start", "to": "right"},
                    {"from": "left", "to": "join"},
                    {"from": "right", "to": "join"},
                ],
            }
        }
    )
    runtime = PipelineRuntime(
        graph,
        registry=registry,
        run_dir=tmp_path / f"{left_key}-{right_key}",
    )

    _GateState.reset(parties=2 if expected_maximum == 2 else 0)
    runtime.run()

    assert _GateState.maximum == expected_maximum


def test_ordinary_async_hooks_keep_scheduler_thread_and_join_order(
    tmp_path: Path,
) -> None:
    registry = _registry()
    register_node(registry, OrdinaryWorkerNode_DECLARATION, OrdinaryWorkerNode)
    register_node(registry, WorkerLeftJoinNode_DECLARATION, WorkerLeftJoinNode)
    calls: list[tuple[str, str, str]] = []

    class HookPlugin:
        name = "thread_probe"

        def before_node(self, name, node_type, input_summary):
            del node_type, input_summary
            calls.append(("before", name, threading.current_thread().name))

        def after_node(self, name, node_type, output_summary):
            del node_type, output_summary
            calls.append(("after", name, threading.current_thread().name))

    plugins = PluginRegistry()
    plugins.register(HookPlugin(), plugin_type="runtime")
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the worker."),
                    _node_call(
                        "worker",
                        "test.ordinary_worker",
                        "Runs an ordinary result task.",

                        result_key="worker.left",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "join",
                        "test.worker_left_join",
                        "Joins the ordinary task.",

                    ),
                ],
                "edges": _edge_chain("start", "worker", "join"),
            }
        }
    )

    PipelineRuntime(
        graph,
        registry=registry,
        plugin_registry=plugins,
        run_dir=tmp_path / "ordinary-hooks",
    ).run()

    worker_calls = [item for item in calls if item[1] == "worker"]
    assert [item[0] for item in worker_calls] == ["before", "after"]
    assert all(item[2] == threading.current_thread().name for item in worker_calls)


def test_trace_failures_do_not_leak_acquired_domains(
    tmp_path: Path,
) -> None:
    acquisition_failure = _runtime(
        "test.parallel_probe",
        tmp_path / "acquisition-failure",
        root_lock="project.acquire-trace",
    )
    acquisition_record = acquisition_failure._record_runtime_event

    def fail_acquired(kind, node_name, node_type, **kwargs):
        if kind == "lock_acquired":
            raise OSError("trace acquire failed")
        return acquisition_record(kind, node_name, node_type, **kwargs)

    acquisition_failure._record_runtime_event = fail_acquired
    with pytest.raises(OSError, match="trace acquire failed"):
        acquisition_failure.run()

    # Reacquiring the same key proves the coordinator released the grant even
    # though lock-acquired trace persistence failed.
    _GateState.reset()
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(
            _runtime(
                "test.global_probe",
                tmp_path / "after-acquisition-failure",
                root_lock="project.acquire-trace",
            ).run
        ).result(timeout=3)

    release_failure = _runtime(
        "test.parallel_probe",
        tmp_path / "release-failure",
        root_lock="project.trace",
    )
    release_record = release_failure._record_runtime_event

    def fail_named_release(kind, node_name, node_type, **kwargs):
        details = kwargs.get("details") or {}
        if kind == "lock_released" and details.get("key") == "project.trace":
            raise OSError("trace release failed")
        return release_record(kind, node_name, node_type, **kwargs)

    release_failure._record_runtime_event = fail_named_release
    with pytest.raises(OSError, match="trace release failed"):
        release_failure.run()

    # The named key remains reusable even when its release trace fails.
    _GateState.reset()
    named = _runtime(
        "test.parallel_probe",
        tmp_path / "after-release-named",
        root_lock="project.trace",
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(named.run).result(timeout=3)


def test_state_change_warning_trace_failure_still_releases_domains(
    tmp_path: Path,
) -> None:
    lock_key = "project.warning-trace"
    failing = _runtime(
        "test.global_failure",
        tmp_path / "warning-failure",
        root_lock=lock_key,
    )
    original_record = failing._record_runtime_event

    def fail_warning(kind, node_name, node_type, **kwargs):
        if kind == "global_state_may_have_changed":
            raise OSError("state warning trace failed")
        return original_record(kind, node_name, node_type, **kwargs)

    failing._record_runtime_event = fail_warning
    with pytest.raises(OSError, match="state warning trace failed"):
        failing.run()

    assert failing._execution_scope_is_protected() is False
    recovered = _runtime(
        "test.global_probe",
        tmp_path / "warning-recovered",
        root_lock=lock_key,
    )
    _GateState.reset()
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(recovered.run).result(timeout=3)


@pytest.mark.parametrize(
    "failing_event",
    ("global_state_enter", "global_state_exit"),
)
def test_global_state_scope_trace_failures_release_node_lock_and_context(
    tmp_path: Path,
    failing_event: str,
) -> None:
    lock_key = "project.global-trace"
    failing = _runtime(
        "test.global_probe",
        tmp_path / failing_event,
        node_lock=lock_key,
    )
    original_record = failing._record_runtime_event

    def fail_scope_trace(kind, node_name, node_type, **kwargs):
        if kind == failing_event:
            raise OSError(f"{failing_event} trace failed")
        return original_record(kind, node_name, node_type, **kwargs)

    failing._record_runtime_event = fail_scope_trace
    with pytest.raises(OSError, match=f"{failing_event} trace failed"):
        failing.run()

    assert failing._execution_scope_is_protected() is False

    # Completing with the same user-named domain proves it was not stranded by
    # scope trace persistence failing before or during cleanup.
    recovered = _runtime(
        "test.global_probe",
        tmp_path / f"{failing_event}-recovered",
        root_lock=lock_key,
    )
    _GateState.reset()
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(recovered.run).result(timeout=3)


def test_dynamic_nested_runtime_rejects_a_different_user_lock_and_releases(
    tmp_path: Path,
) -> None:
    outer_key = "project.dynamic-outer"
    inner_key = "project.dynamic-inner"
    child = _runtime(
        "test.parallel_probe",
        tmp_path / "dynamic-child",
        root_lock=inner_key,
    )

    DynamicNestedRuntimeNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.dynamic_nested_runtime', display_name='Dynamic Nested Runtime', description='Attempts to acquire another user domain through a nested runtime.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(), rulesets=("vibeflow.process",))

    class DynamicNestedRuntimeNode:

        def run_pure(self, inputs, params):
            del inputs, params
            child.run()
            return {}

    registry = _registry()
    register_node(
        registry,
        DynamicNestedRuntimeNode_DECLARATION,
        DynamicNestedRuntimeNode,
    )
    graph = parse_graph_config(
        {
            "pipeline": {
                "execution_lock": {"key": outer_key},
                "nodes": [
                    _node_call("start", "test.start", "Starts the outer run."),
                    _node_call(
                        "nested",
                        "test.dynamic_nested_runtime",
                        "Starts a dynamically-created child runtime.",
                    ),
                    _node_call("end", "test.start", "Ends the outer run."),
                ],
                "edges": _edge_chain("start", "nested", "end"),
            }
        }
    )
    outer = PipelineRuntime(
        graph,
        registry=registry,
        run_dir=tmp_path / "dynamic-outer",
    )

    with pytest.raises(
        PipelineRuntimeError,
        match=(
            f"cannot acquire execution lock '{inner_key}' while user lock "
            f"'{outer_key}' is held"
        ),
    ):
        outer.run()

    assert outer._execution_scope_is_protected() is False

    # Reacquiring A proves it was released after the fail-fast path.
    recovered = _runtime(
        "test.global_probe",
        tmp_path / "dynamic-recovered",
        root_lock=outer_key,
    )
    _GateState.reset()
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(recovered.run).result(timeout=3)


def test_inherited_root_protection_drains_nested_failure_tasks_before_release(
    tmp_path: Path,
) -> None:
    lock_key = "project.nested-protected"
    registry = _registry()
    register_node(registry, GlobalNoopNode_DECLARATION, GlobalNoopNode)
    register_node(
        registry,
        ProtectedSlowResultNode_DECLARATION,
        ProtectedSlowResultNode,
    )
    register_node(registry, ProtectedJoinNode_DECLARATION, ProtectedJoinNode)
    register_node(
        registry,
        CoordinatedFailureNode_DECLARATION,
        CoordinatedFailureNode,
    )
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "test.protected_child",
                    provides=["protected.result"],
                    pipeline={
                        "nodes": [
                            _node_call(
                                "start",
                                "test.start",
                                "Starts child branches.",
                            ),
                            _node_call(
                                "bb_slow",
                                "test.protected_slow_result",
                                "Runs a protected child result task.",

                                result_key="protected.result",
                                **{"async": "result_key"},
                            ),
                            _node_call(
                                "aa_bad",
                                "test.coordinated_failure",
                                "Fails before the result can join.",

                                result_key="value.out",
                                **{"async": "result_key"},
                            ),
                            _node_call(
                                "join",
                                "test.protected_join",
                                "Would join both child branches.",

                                join_policy="all",
                            ),
                        ],
                        "edges": [
                            {"from": "start", "to": "aa_bad"},
                            {"from": "start", "to": "bb_slow"},
                            {"from": "aa_bad", "to": "join"},
                            {"from": "bb_slow", "to": "join"},
                        ],
                        "outputs": [REQ_SPEC("protected.result")],
                    },
                )
            ],
            "pipeline": {
                "execution_lock": {"key": lock_key},
                "nodes": [
                    _node_call("start", "test.start", "Starts the root."),
                    _node_call(
                        "global",
                        "test.global_noop",
                        "Acquires the root global-state domain.",
                    ),
                    _node_call(
                        "child",
                        "test.protected_child",
                        "Runs the failing child block.",

                    ),
                    _node_call(
                        "end",
                        "test.out_end",
                        "Consumes the child result.",

                    ),
                ],
                "edges": _edge_chain("start", "global", "child", "end"),
            },
        }
    )
    outer = PipelineRuntime(
        graph,
        registry=registry,
        run_dir=tmp_path / "nested-protected",
    )
    competitor = _runtime(
        "test.following_normal",
        tmp_path / "nested-competitor",
        root_lock=lock_key,
    )
    _ProtectedTaskState.reset()
    _WriterPreferenceState.reset()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outer_future = executor.submit(outer.run)
        assert _ProtectedTaskState.entered.wait(timeout=2)
        competitor_future = executor.submit(competitor.run)
        assert not _WriterPreferenceState.follower_entered.wait(timeout=0.1)
        assert not outer_future.done()

        _ProtectedTaskState.release.set()
        with pytest.raises(RuntimeError, match="coordinated boom"):
            outer_future.result(timeout=3)
        competitor_future.result(timeout=3)

    assert _ProtectedTaskState.finished.is_set()
    assert _WriterPreferenceState.follower_entered.is_set()


def test_early_terminal_fails_closed_and_retains_lock_until_result_finishes(
    tmp_path: Path,
) -> None:
    lock_key = "project.early-terminal"
    registry = _registry()
    register_node(registry, EarlyQuickResultNode_DECLARATION, EarlyQuickResultNode)
    register_node(registry, EarlySlowResultNode_DECLARATION, EarlySlowResultNode)
    register_node(registry, EarlyQuickEndNode_DECLARATION, EarlyQuickEndNode)
    register_node(registry, EarlySlowEndNode_DECLARATION, EarlySlowEndNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "execution_lock": {"key": lock_key},
                "nodes": [
                    _node_call("start", "test.start", "Starts both branches."),
                    _node_call(
                        "quick",
                        "test.early_quick_result",
                        "Completes the selected result branch.",

                        result_key="early.quick",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "slow",
                        "test.early_slow_result",
                        "Runs the result branch left behind by early exit.",

                        result_key="early.slow",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "quick_end",
                        "test.early_quick_end",
                        "Ends after the quick branch.",

                    ),
                    _node_call(
                        "slow_end",
                        "test.early_slow_end",
                        "Makes the slow join statically reachable.",

                    ),
                ],
                "edges": [
                    {"from": "start", "to": "quick"},
                    {"from": "start", "to": "slow"},
                    {"from": "quick", "to": "quick_end"},
                    {"from": "slow", "to": "slow_end"},
                ],
            }
        }
    )
    outer = PipelineRuntime(
        graph,
        registry=registry,
        run_dir=tmp_path / "early-terminal",
        runtime_options={"async_max_workers": 2},
    )
    competitor = _runtime(
        "test.following_normal",
        tmp_path / "early-terminal-competitor",
        root_lock=lock_key,
    )
    _ProtectedTaskState.reset()
    _WriterPreferenceState.reset()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outer_future = executor.submit(outer.run)
        if not _ProtectedTaskState.entered.wait(timeout=2):
            outer_future.result(timeout=0)
            pytest.fail("slow protected task did not start")
        competitor_future = executor.submit(competitor.run)
        assert not _WriterPreferenceState.follower_entered.wait(timeout=0.1)
        assert not outer_future.done()

        _ProtectedTaskState.release.set()
        with pytest.raises(
            PipelineRuntimeError,
            match=(
                "protected async task reached cleanup without its scheduled join"
            ),
        ):
            outer_future.result(timeout=3)
        competitor_future.result(timeout=3)

    assert _ProtectedTaskState.finished.is_set()
    assert _WriterPreferenceState.follower_entered.is_set()


def test_unrelated_detached_sibling_does_not_inherit_node_lock_protection(
    tmp_path: Path,
) -> None:
    registry = _registry()
    register_node(registry, ParallelProbeNode_DECLARATION, ParallelProbeNode)
    register_node(
        registry,
        UnrelatedDetachedNode_DECLARATION,
        UnrelatedDetachedNode,
    )
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts both branches."),
                    {
                        **_node_call(
                            "locked",
                            "test.parallel_probe",
                            "Uses a call-site execution lock.",
                        ),
                        "execution_lock": {"key": "project.localized"},
                    },
                    _node_call(
                        "background",
                        "test.unrelated_detached",
                        "Runs outside the sibling lock scope.",
                        **{"async": "detached"},
                    ),
                    _node_call("end", "test.start", "Ends the main branch."),
                ],
                "edges": [
                    {"from": "start", "to": "locked"},
                    {"from": "start", "to": "background"},
                    {"from": "locked", "to": "end"},
                ],
            }
        }
    )
    runtime = PipelineRuntime(
        graph,
        registry=registry,
        run_dir=tmp_path / "localized-protection",
        runtime_options={"async_flush_timeout": 0.01},
    )
    _ProtectedTaskState.reset()
    _GateState.reset()

    started = time.monotonic()
    try:
        runtime.run()
        elapsed = time.monotonic() - started
        assert _ProtectedTaskState.entered.is_set()
        assert not _ProtectedTaskState.finished.is_set()
        assert elapsed < 0.5
    finally:
        _ProtectedTaskState.release.set()
        assert _ProtectedTaskState.finished.wait(timeout=2)


def test_failure_warning_includes_global_task_started_during_final_drain(
    tmp_path: Path,
) -> None:
    lock_key = "project.late-drain"
    registry = _registry()
    register_node(registry, DelayedResultNode_DECLARATION, DelayedResultNode)
    register_node(
        registry,
        LateGlobalResultNode_DECLARATION,
        LateGlobalResultNode,
    )
    register_node(registry, LateJoinNode_DECLARATION, LateJoinNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "execution_lock": {"key": lock_key},
                "nodes": [
                    _node_call("start", "test.start", "Starts queued work."),
                    _node_call(
                        "aa_slow",
                        "test.delayed_result",
                        "Occupies the worker.",

                        result_key="late.normal",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "bb_late_global",
                        "test.late_global_result",
                        "Runs after the main failure begins.",

                        result_key="late.global",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "zz_bad",
                        "test.runtime_fail",
                        "Fails before the queued global task starts.",

                        config={"fail": True},
                        result_key="value.out",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "join",
                        "test.late_join",
                        "Would join every result.",

                        join_policy="all",
                    ),
                ],
                "edges": [
                    {"from": "start", "to": "aa_slow"},
                    {"from": "start", "to": "bb_late_global"},
                    {"from": "start", "to": "zz_bad"},
                    {"from": "aa_slow", "to": "join"},
                    {"from": "bb_late_global", "to": "join"},
                    {"from": "zz_bad", "to": "join"},
                ],
            }
        }
    )
    runtime = PipelineRuntime(
        graph,
        registry=registry,
        run_dir=tmp_path / "late-drain",
        runtime_options={"async_max_workers": 1},
    )

    with pytest.raises(RuntimeError, match="boom"):
        runtime.run()

    events = [
        json.loads(line)
        for line in (tmp_path / "late-drain" / "runtime_trace.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    kinds = [event["kind"] for event in events]
    assert kinds.count("global_state_may_have_changed") == 1
    assert kinds.index("global_state_enter") < kinds.index(
        "global_state_may_have_changed"
    )
    assert kinds.index("global_state_may_have_changed") < kinds.index(
        "lock_released"
    )
