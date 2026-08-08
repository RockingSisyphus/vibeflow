"""Runtime conformance tests for global-state leases and named locks."""

from __future__ import annotations

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
from vibeflow.targets.python.project import NodeContract, NodeInfo
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


class NormalGateNode:
    NODE_INFO = NodeInfo(
        "test.normal_gate",
        "Normal Gate",
        "test",
        "Blocks a normal root for lock coordination tests.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        del inputs, params
        _GateState.run(wait_for_release=True)
        return {}


class ParallelProbeNode:
    NODE_INFO = NodeInfo(
        "test.parallel_probe",
        "Parallel Probe",
        "test",
        "Measures overlapping root execution.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        del inputs, params
        _GateState.run()
        return {}


class GlobalProbeNode:
    NODE_INFO = NodeInfo(
        "test.global_probe",
        "Global Probe",
        "test",
        "Touches ambient interpreter state for runtime lock tests.",
        "0.1.0",
        "global_state",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        del inputs, params
        _GateState.run()
        return {}


class BlockingNormalNode:
    NODE_INFO = NodeInfo(
        "test.blocking_normal",
        "Blocking Normal",
        "test",
        "Holds one shared root admission.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        del inputs, params
        _WriterPreferenceState.first_entered.set()
        _WriterPreferenceState.release_first.wait(timeout=2)
        return {}


class HoldingGlobalNode:
    NODE_INFO = NodeInfo(
        "test.holding_global",
        "Holding Global",
        "test",
        "Holds the exclusive global-state admission.",
        "0.1.0",
        "global_state",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        del inputs, params
        _WriterPreferenceState.writer_entered.set()
        _WriterPreferenceState.release_writer.wait(timeout=2)
        return {}


class FollowingNormalNode:
    NODE_INFO = NodeInfo(
        "test.following_normal",
        "Following Normal",
        "test",
        "Attempts shared admission behind a waiting writer.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        del inputs, params
        _WriterPreferenceState.follower_entered.set()
        return {}


class GlobalFailureNode:
    NODE_INFO = NodeInfo(
        "test.global_failure",
        "Global Failure",
        "test",
        "Fails after ambient state may have changed.",
        "0.1.0",
        "global_state",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        del inputs, params
        raise RuntimeError("global boom")


class GlobalInterruptNode:
    NODE_INFO = NodeInfo(
        "test.global_interrupt",
        "Global Interrupt",
        "test",
        "Simulates cancellation after ambient state may have changed.",
        "0.1.0",
        "global_state",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        del inputs, params
        raise KeyboardInterrupt("global cancelled")


class GlobalNoopNode:
    NODE_INFO = NodeInfo(
        "test.global_noop",
        "Global Noop",
        "test",
        "Marks a root as global-state protected without delaying it.",
        "0.1.0",
        "global_state",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


class GlobalWorkerLeftNode:
    NODE_INFO = NodeInfo(
        "test.global_worker_left",
        "Global Worker Left",
        "test",
        "Runs one managed global-state worker.",
        "0.1.0",
        "global_state",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("worker.left", "worker.left", display_name="worker.left"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        _GateState.run()
        return {"worker.left": True}


class GlobalWorkerRightNode:
    NODE_INFO = NodeInfo(
        "test.global_worker_right",
        "Global Worker Right",
        "test",
        "Runs another managed global-state worker.",
        "0.1.0",
        "global_state",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("worker.right", "worker.right", display_name="worker.right"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        _GateState.run()
        return {"worker.right": True}


class OrdinaryWorkerNode:
    NODE_INFO = NodeInfo(
        "test.ordinary_worker",
        "Ordinary Worker",
        "test",
        "Runs one ordinary managed result worker.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("worker.left", "worker.left", display_name="worker.left"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        return {"worker.left": True}


class WorkerLeftJoinNode:
    NODE_INFO = NodeInfo(
        "test.worker_left_join",
        "Worker Left Join",
        "test",
        "Joins one ordinary worker result.",
        "0.1.0",
        "terminal",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("worker.left", "exactly_one", display_name="worker.left"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


class ProtectedSlowResultNode:
    NODE_INFO = NodeInfo(
        "test.protected_slow_result",
        "Protected Slow Result",
        "test",
        "Waits so failure cleanup must retain an inherited lease.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("protected.result", "protected.result", display_name="protected.result"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        _ProtectedTaskState.entered.set()
        try:
            _ProtectedTaskState.release.wait(timeout=2)
            return {"protected.result": True}
        finally:
            _ProtectedTaskState.finished.set()


class ProtectedJoinNode:
    NODE_INFO = NodeInfo(
        "test.protected_join",
        "Protected Join",
        "test",
        "Joins a protected result and a second branch.",
        "0.1.0",
        "terminal",
    )
    CONTRACT = NodeContract(
        requires=(
            DataRequirement("protected.result", "exactly_one", display_name="protected.result"),
            DataRequirement("value.out", "exactly_one", display_name="value.out"),
        ),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


class CoordinatedFailureNode:
    NODE_INFO = NodeInfo(
        "test.coordinated_failure",
        "Coordinated Failure",
        "test",
        "Fails only after the sibling protected worker has started.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("value.out", "value.out", display_name="value.out"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        _ProtectedTaskState.entered.wait(timeout=2)
        raise RuntimeError("coordinated boom")


class UnrelatedDetachedNode:
    NODE_INFO = NodeInfo(
        "test.unrelated_detached",
        "Unrelated Detached",
        "test",
        "Waits outside a sibling node's named lock scope.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        del inputs, params
        _ProtectedTaskState.entered.set()
        try:
            _ProtectedTaskState.release.wait(timeout=2)
            return {}
        finally:
            _ProtectedTaskState.finished.set()


class WorkerJoinNode:
    NODE_INFO = NodeInfo(
        "test.worker_join",
        "Worker Join",
        "test",
        "Joins both managed worker results before root completion.",
        "0.1.0",
        "terminal",
    )
    CONTRACT = NodeContract(
        requires=(
            DataRequirement("worker.left", "exactly_one", display_name="worker.left"),
            DataRequirement("worker.right", "exactly_one", display_name="worker.right"),
        ),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


class DelayedResultNode:
    NODE_INFO = NodeInfo(
        "test.delayed_result",
        "Delayed Result",
        "test",
        "Occupies the sole managed worker before a late global task.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("late.normal", "late.normal", display_name="late.normal"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        time.sleep(0.08)
        return {"late.normal": True}


class LateGlobalResultNode:
    NODE_INFO = NodeInfo(
        "test.late_global_result",
        "Late Global Result",
        "test",
        "Starts only while failure cleanup drains managed work.",
        "0.1.0",
        "global_state",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("late.global", "late.global", display_name="late.global"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        return {"late.global": True}


class LateJoinNode:
    NODE_INFO = NodeInfo(
        "test.late_join",
        "Late Join",
        "test",
        "Provides a provable join path for cleanup tasks.",
        "0.1.0",
        "terminal",
    )
    CONTRACT = NodeContract(
        requires=(
            DataRequirement("late.normal", "exactly_one", display_name="late.normal"),
            DataRequirement("late.global", "exactly_one", display_name="late.global"),
            DataRequirement("value.out", "exactly_one", display_name="value.out"),
        ),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


class EarlyQuickResultNode:
    NODE_INFO = NodeInfo(
        "test.early_quick_result",
        "Early Quick Result",
        "test",
        "Completes the branch whose terminal ends the root early.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("early.quick", "early.quick", display_name="early.quick"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        _ProtectedTaskState.entered.wait(timeout=2)
        return {"early.quick": True}


class EarlySlowResultNode:
    NODE_INFO = NodeInfo(
        "test.early_slow_result",
        "Early Slow Result",
        "test",
        "Keeps an unselected result branch active during early termination.",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("early.slow", "early.slow", display_name="early.slow"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        _ProtectedTaskState.entered.set()
        try:
            _ProtectedTaskState.release.wait(timeout=2)
            return {"early.slow": True}
        finally:
            _ProtectedTaskState.finished.set()


class EarlyQuickEndNode:
    NODE_INFO = NodeInfo(
        "test.early_quick_end",
        "Early Quick End",
        "test",
        "Ends the root after consuming only the quick branch.",
        "0.1.0",
        "terminal",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("early.quick", "exactly_one", display_name="early.quick"),),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        return {}


class EarlySlowEndNode:
    NODE_INFO = NodeInfo(
        "test.early_slow_end",
        "Early Slow End",
        "test",
        "Provides the statically visible join path for the slow branch.",
        "0.1.0",
        "terminal",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("early.slow", "exactly_one", display_name="early.slow"),),
    )

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
    register_node(registry, "test.normal_gate", NormalGateNode)
    register_node(registry, "test.parallel_probe", ParallelProbeNode)
    register_node(registry, "test.global_probe", GlobalProbeNode)
    register_node(registry, "test.global_failure", GlobalFailureNode)
    register_node(registry, "test.global_interrupt", GlobalInterruptNode)
    register_node(registry, "test.blocking_normal", BlockingNormalNode)
    register_node(registry, "test.holding_global", HoldingGlobalNode)
    register_node(registry, "test.following_normal", FollowingNormalNode)
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
    register_node(registry, "test.parallel_probe", ParallelProbeNode)
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
    register_node(registry, "test.global_worker_left", GlobalWorkerLeftNode)
    register_node(registry, "test.global_worker_right", GlobalWorkerRightNode)
    register_node(registry, "test.worker_join", WorkerJoinNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts both workers."),
                    _node_call(
                        "left",
                        "test.global_worker_left",
                        "Runs the left worker.",
                        provides=[PROV_SPEC("worker.left")],
                        result_key="worker.left",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "right",
                        "test.global_worker_right",
                        "Runs the right worker.",
                        provides=[PROV_SPEC("worker.right")],
                        result_key="worker.right",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "join",
                        "test.worker_join",
                        "Joins both workers.",
                        requires=[
                            REQ_SPEC("worker.left"),
                            REQ_SPEC("worker.right"),
                        ],
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
    register_node(registry, "test.global_worker_left", GlobalWorkerLeftNode)
    register_node(registry, "test.global_worker_right", GlobalWorkerRightNode)
    register_node(registry, "test.worker_join", WorkerJoinNode)
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
                            provides=[PROV_SPEC("worker.left")],
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
                            provides=[PROV_SPEC("worker.right")],
                            result_key="worker.right",
                            **{"async": "result_key"},
                        ),
                        "execution_lock": {"key": right_key},
                    },
                    _node_call(
                        "join",
                        "test.worker_join",
                        "Joins both locked workers.",
                        requires=[
                            REQ_SPEC("worker.left"),
                            REQ_SPEC("worker.right"),
                        ],
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
    register_node(registry, "test.ordinary_worker", OrdinaryWorkerNode)
    register_node(registry, "test.worker_left_join", WorkerLeftJoinNode)
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
                        provides=[PROV_SPEC("worker.left")],
                        result_key="worker.left",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "join",
                        "test.worker_left_join",
                        "Joins the ordinary task.",
                        requires=[REQ_SPEC("worker.left")],
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

    class DynamicNestedRuntimeNode:
        NODE_INFO = NodeInfo(
            "test.dynamic_nested_runtime",
            "Dynamic Nested Runtime",
            "test",
            "Attempts to acquire another user domain through a nested runtime.",
            "0.1.0",
            "process",
        )
        CONTRACT = NodeContract()

        def run_pure(self, inputs, params):
            del inputs, params
            child.run()
            return {}

    registry = _registry()
    register_node(
        registry,
        "test.dynamic_nested_runtime",
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
    register_node(registry, "test.global_noop", GlobalNoopNode)
    register_node(
        registry,
        "test.protected_slow_result",
        ProtectedSlowResultNode,
    )
    register_node(registry, "test.protected_join", ProtectedJoinNode)
    register_node(
        registry,
        "test.coordinated_failure",
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
                                provides=[PROV_SPEC("protected.result")],
                                result_key="protected.result",
                                **{"async": "result_key"},
                            ),
                            _node_call(
                                "aa_bad",
                                "test.coordinated_failure",
                                "Fails before the result can join.",
                                provides=[PROV_SPEC("value.out")],
                                result_key="value.out",
                                **{"async": "result_key"},
                            ),
                            _node_call(
                                "join",
                                "test.protected_join",
                                "Would join both child branches.",
                                requires=[
                                    REQ_SPEC("protected.result"),
                                    REQ_SPEC("value.out"),
                                ],
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
                        provides=[PROV_SPEC("protected.result")],
                    ),
                    _node_call(
                        "end",
                        "test.out_end",
                        "Consumes the child result.",
                        requires=[REQ_SPEC("protected.result")],
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
    register_node(registry, "test.early_quick_result", EarlyQuickResultNode)
    register_node(registry, "test.early_slow_result", EarlySlowResultNode)
    register_node(registry, "test.early_quick_end", EarlyQuickEndNode)
    register_node(registry, "test.early_slow_end", EarlySlowEndNode)
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
                        provides=[PROV_SPEC("early.quick")],
                        result_key="early.quick",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "slow",
                        "test.early_slow_result",
                        "Runs the result branch left behind by early exit.",
                        provides=[PROV_SPEC("early.slow")],
                        result_key="early.slow",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "quick_end",
                        "test.early_quick_end",
                        "Ends after the quick branch.",
                        requires=[REQ_SPEC("early.quick")],
                    ),
                    _node_call(
                        "slow_end",
                        "test.early_slow_end",
                        "Makes the slow join statically reachable.",
                        requires=[REQ_SPEC("early.slow")],
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
    register_node(registry, "test.parallel_probe", ParallelProbeNode)
    register_node(
        registry,
        "test.unrelated_detached",
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
    register_node(registry, "test.delayed_result", DelayedResultNode)
    register_node(
        registry,
        "test.late_global_result",
        LateGlobalResultNode,
    )
    register_node(registry, "test.late_join", LateJoinNode)
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
                        provides=[PROV_SPEC("late.normal")],
                        result_key="late.normal",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "bb_late_global",
                        "test.late_global_result",
                        "Runs after the main failure begins.",
                        provides=[PROV_SPEC("late.global")],
                        result_key="late.global",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "zz_bad",
                        "test.runtime_fail",
                        "Fails before the queued global task starts.",
                        provides=[PROV_SPEC("value.out")],
                        config={"fail": True},
                        result_key="value.out",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "join",
                        "test.late_join",
                        "Would join every result.",
                        requires=[
                            REQ_SPEC("late.normal"),
                            REQ_SPEC("late.global"),
                            REQ_SPEC("value.out"),
                        ],
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
