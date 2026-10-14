"""Workflow-owned execution records and notification-based task control."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass
from threading import Condition, Event, Lock, Thread
from typing import Mapping, TypedDict
from types import MappingProxyType
from uuid import uuid4
from traceback import extract_tb

from .errors import PipelineRuntimeError, DelegateCliExit


class TaskRef(TypedDict):
    run_id: str
    task_id: str


class TaskOutcome(TypedDict, total=False):
    task: TaskRef
    status: str
    outputs: dict
    error: dict


class StopAck(TypedDict):
    task: TaskRef
    state: str


class TaskContractError(PipelineRuntimeError):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code


class TaskCancelled(PipelineRuntimeError):
    code = "VF_ABORTED"


class CancellationSignal:
    """Cooperative signal; cancelling never means the execution has exited."""
    def __init__(self):
        self._event = Event()
        self._lock = Lock()
        self._listeners = set()
        self._callback_errors = []
        self.reason = None

    @property
    def aborted(self):
        return self._event.is_set()

    def is_set(self):
        return self.aborted

    def wait(self, timeout=None):
        return self._event.wait(timeout)

    def throw_if_aborted(self):
        if self.aborted:
            raise TaskCancelled("VF_ABORTED: task cancellation requested")

    def request_stop(self, reason=None):
        with self._lock:
            if self.aborted:
                return
            self.reason = reason
            self._event.set()
            listeners = tuple(self._listeners)
            self._listeners.clear()
        for listener in listeners:
            try:
                listener(reason)
            except Exception as error:
                with self._lock:
                    self._callback_errors.append(error)

    def subscribe(self, listener):
        with self._lock:
            aborted = self.aborted
            if not aborted:
                self._listeners.add(listener)
        if aborted:
            try:
                listener(self.reason)
            except Exception as error:
                with self._lock:
                    self._callback_errors.append(error)
        def remove():
            with self._lock:
                self._listeners.discard(listener)
        return remove


@dataclass
class _Task:
    ref: dict
    parent: str | None
    signal: CancellationSignal | None
    outcome: dict | None = None
    observed: bool = False
    exit_order: int = 0
    phase: str = "queued"
    manager_path: tuple = ()
    trace: object = None
    trace_path: tuple = ()


def _structured_error(exc, path, seen=None):
    seen = set() if seen is None else seen
    if id(exc) in seen:
        return {"message":str(exc), "exception_type":type(exc).__name__}
    seen.add(id(exc))
    frames = extract_tb(exc.__traceback__)
    source = frames[-1] if frames else None
    return {"code": "VF_TASK_BUSINESS_EXIT" if isinstance(exc,DelegateCliExit) else getattr(exc, "code", "VF_TASK_FAILED"),
            "message": f"task requested delegated exit code {exc.exit_code}" if isinstance(exc,DelegateCliExit) else str(exc),
            **({"exit_code":exc.exit_code, "exit_source":exc.source} if isinstance(exc,DelegateCliExit) else {}),
            "node_path": ".".join(path), "exception_type": type(exc).__name__,
            "source_location": {"path": source.filename, "line": source.lineno} if source else {},
            **({"errors": [_structured_error(error,path,seen) for error in exc.exceptions]} if isinstance(exc,BaseExceptionGroup) else {}),
            **({"cause": _structured_error(exc.__cause__,path,seen)} if exc.__cause__ is not None else {}),
            **({"task_errors": exc.task_errors} if hasattr(exc,"task_errors") else {}),
            **({"cleanup_error": _structured_error(exc.cleanup_error,path,seen)} if hasattr(exc,"cleanup_error") else {}),
            **({"cleanup_errors": [_structured_error(error,path,seen) for error in exc.cleanup_errors]} if hasattr(exc,"cleanup_errors") else {}),
            **({"context": _structured_error(exc.__context__,path,seen)} if exc.__context__ is not None and not exc.__suppress_context__ else {})}


def _has_manager(plan):
    return any(frame.flow_kind == "task_manager" or
               frame.subplan is not None and _has_manager(frame.subplan)
               for frame in plan.frames.values())


class TaskRegistry:
    def __init__(self, owner=None):
        self._owner = owner
        self.run_id = str(uuid4())
        self._condition = Condition()
        self._records = {}
        self._pools = {}
        self._controls = []
        self._next_id = 0
        self._exit_order = 0
        self._closing = False

    def _emit(self, kind, task, details):
        if self._owner is not None:
            self._owner._record_runtime_event(kind,".".join(task.manager_path),"task",
                details={"task":dict(task.ref),**details})

    def select(self, refs):
        if not isinstance(refs, (list, tuple)):
            raise TaskContractError("VF_TASK_REF_INVALID", "expected task reference array")
        selected, seen = [], set()
        with self._condition:
            for ref in refs:
                if not isinstance(ref, Mapping) or ref.get("run_id") != self.run_id:
                    raise TaskContractError("VF_TASK_REF_INVALID", "foreign workflow task reference")
                task_id = ref.get("task_id")
                if not isinstance(task_id, str) or task_id not in self._records:
                    raise TaskContractError("VF_TASK_REF_INVALID", "unknown or consumed task reference")
                if task_id not in seen:
                    seen.add(task_id)
                    selected.append(self._records[task_id])
        return selected

    def start(self, runtime, frame, key, inputs):
        runtime._signal.throw_if_aborted()
        if self._closing:
            raise TaskCancelled("VF_ABORTED: workflow is stopping")
        if not isinstance(key, str) or key not in frame.task_plans:
            raise TaskContractError("VF_TASK_TARGET_UNKNOWN", f"undeclared task slot '{key}'")
        if not isinstance(inputs, Mapping):
            raise TaskContractError("VF_TASK_INPUT_INVALID", "task inputs must be a mapping")
        plan = frame.task_plans[key]
        with self._condition:
            self._next_id += 1
            ref = {"run_id": self.run_id, "task_id": str(self._next_id)}
            task = _Task(ref, runtime._current_task, CancellationSignal(),
                         manager_path=(*runtime._trace_path_prefix,frame.id))
            self._records[ref["task_id"]] = task
        signal = task.signal
        unsubscribe = runtime._signal.subscribe(signal.request_stop)
        child = type(runtime)._from_plan(runtime, plan)
        child._signal, child._current_task = signal, ref["task_id"]
        child._owns_task_scope = True
        retained_locks = runtime._retain_task_execution_locks()
        child._trace_path_prefix = (*runtime._trace_path_prefix, frame.id, "tasks", key, f"task_{ref['task_id']}")
        execution_context = copy_context()
        def execute():
            with self._condition:
                if task.outcome is not None:
                    return  # Executor startup failed before this queued call entered.
                if task.phase == "queued":
                    task.phase = "running"
            failure, outputs = None, {}
            try:
                signal.throw_if_aborted()
                child._run_observed(dict(inputs))
                outputs = dict(child._task_outputs)
                signal.throw_if_aborted()
            except BaseException as exc:
                failure = _structured_error(exc, child._trace_path_prefix)
            try:
                self.drain(ref["task_id"])
            except BaseException as exc:
                cleanup = _structured_error(exc, child._trace_path_prefix)
                if failure is None:
                    failure = cleanup
                else:
                    failure.setdefault("cleanup_errors", []).append(cleanup)
            for cleanup_action in (lambda: self.close_context(child),
                                   lambda: runtime._release_task_execution_locks(retained_locks), unsubscribe):
                try:
                    cleanup_action()
                except BaseException as exc:
                    cleanup = _structured_error(exc, child._trace_path_prefix)
                    if failure is None:
                        failure = cleanup
                    else:
                        failure.setdefault("cleanup_errors", []).append(cleanup)
            with self._condition:
                task.trace, task.trace_path = child.trace, child._trace_path_prefix
                self._exit_order += 1
                task.exit_order = self._exit_order
                outcome = {"task": dict(ref), "status":
                    ("cancelled" if failure["code"] == "VF_ABORTED" and not failure.get("cleanup_error") and not failure.get("cleanup_errors") else "failed") if failure else "succeeded"}
                outcome["error" if failure else "outputs"] = failure or outputs
                task.signal = None
                task.phase = "exited"
                try:
                    self._emit("task_exited", task, {"status":outcome["status"]})
                except BaseException as error:
                    outcome = {"task":dict(ref), "status":"failed",
                                    "error":_structured_error(error,task.manager_path)}
                task.outcome = outcome
                self._condition.notify_all()
        try:
            self._emit("task_started", task, {"key":key})
        except BaseException as error:
            runtime._release_task_execution_locks(retained_locks)
            unsubscribe()
            with self._condition:
                task.signal, task.phase = None, "exited"
                task.outcome = {"task":dict(ref), "status":"failed", "error":_structured_error(error,task.manager_path)}
                self._condition.notify_all()
            raise
        thread = None
        # Publishing and starting are atomic with respect to execute(). An
        # executor may enqueue before reporting a failed thread startup.
        with self._condition:
            try:
                if _has_manager(plan):
                    # Control waits never occupy the bounded pool they supervise.
                    thread = Thread(target=execution_context.run, args=(execute,), name="vibeflow-task-manager")
                    self._controls = [control for control in self._controls if control.ident is None or control.is_alive()]
                    self._controls.append(thread)
                    thread.start()
                else:
                    pool = self._pools.get(runtime)
                    if pool is None:
                        pool = self._pools[runtime] = ThreadPoolExecutor(
                            max_workers=runtime.runtime_options.async_max_workers,
                            thread_name_prefix="vibeflow-task")
                    pool.submit(execution_context.run, execute)
            except BaseException as error:
                if thread is not None:
                    self._controls.remove(thread)
                task.phase, task.signal, task.observed = "exited", None, True
                task.outcome = {"task":dict(ref), "status":"failed", "error":_structured_error(error,task.manager_path)}
                runtime._release_task_execution_locks(retained_locks)
                unsubscribe()
                self._condition.notify_all()
                self._emit("task_exited",task,{"status":"failed"})
                raise
        return dict(ref)

    def request_stop(self, refs, reason=None):
        tasks = self.select(refs)
        acks = []
        for task in tasks:
            with self._condition:
                signal = task.signal
                if signal is not None:
                    task.phase = "stopping"
            if signal is not None:
                signal.request_stop(reason)
            acks.append({"task": dict(task.ref), "state": "stop_requested" if signal else "already_exited"})
        return acks

    def wait_any(self, refs, signal):
        tasks = self.select(refs)
        if not tasks:
            return None
        def notify(_):
            with self._condition:
                self._condition.notify_all()
        unsubscribe = signal.subscribe(notify)
        try:
            with self._condition:
                while True:
                    self._check_pending(tasks)
                    finished = [task for task in tasks if task.outcome is not None]
                    if finished:
                        task = min(finished, key=lambda item: item.exit_order)
                        return self._deliver([task])[0]
                    signal.throw_if_aborted()
                    self._condition.wait()
        finally:
            unsubscribe()

    def wait_all_exited(self, refs):
        tasks = self.select(refs)
        with self._condition:
            while True:
                self._check_pending(tasks)
                if all(task.outcome is not None for task in tasks):
                    return self._deliver(tasks)
                self._condition.wait()

    def _check_pending(self, tasks):
        if any(self._records.get(task.ref["task_id"]) is not task for task in tasks):
            raise TaskContractError("VF_TASK_REF_INVALID", "task result was already consumed")

    def _retire(self, task):
        if task.trace is not None and self._owner is not None:
            self._owner.trace.merge_child(task.trace_path, task.trace)
            task.trace = None
        task.observed = True
        self._records.pop(task.ref["task_id"], None)

    def _deliver(self, tasks):
        # Called under the completion lock: validate the whole batch before
        # transferring any results, so overlapping waits cannot lose a subset.
        self._check_pending(tasks)
        outcomes = [dict(task.outcome) for task in tasks]
        for task in tasks:
            self._retire(task)
        self._condition.notify_all()
        return outcomes

    def drain(self, parent):
        with self._condition:
            if parent is None:
                self._closing = True
            children = [task for task in self._records.values() if task.parent == parent]
        if parent is None and any(task.outcome is None for task in children):
            from .observation import current_observation
            observer = current_observation()
            if observer is not None:
                observer.transition("stopping")
        # A receiver may consume a completed child while this owner drains.
        # Hold record objects, not references requiring another registry lookup.
        for task in children:
            with self._condition:
                signal = task.signal
                if signal is not None:
                    task.phase = "stopping"
            if signal is not None:
                signal.request_stop("owner exiting")
        with self._condition:
            self._condition.wait_for(lambda: all(task.outcome is not None for task in children))
            failures = [task.outcome["error"] for task in children
                        if task.outcome["status"] == "failed" and not task.observed]
            for task in children:
                if self._records.get(task.ref["task_id"]) is task:
                    self._retire(task)
            self._condition.notify_all()
        if failures:
            error = PipelineRuntimeError("VF_TASK_UNOBSERVED: " + "; ".join(item["message"] for item in failures))
            error.task_errors = failures
            raise error

    def close_context(self, runtime):
        with self._condition:
            pool = self._pools.pop(runtime, None)
        if pool is not None:
            pool.shutdown(wait=True)

    def close(self):
        for pool in self._pools.values():
            pool.shutdown(wait=True)
        for thread in self._controls:
            thread.join()
        self._pools.clear()
        self._controls.clear()
        self._owner = None


class TaskController:
    def __init__(self, runtime, frame, context):
        if frame.flow_kind != "task_manager" or context._frame is not frame or context._runtime is not runtime:
            raise TaskContractError("VF_TASK_CONTROL_FORBIDDEN", "task control requires the active manager context")
        self._runtime, self._frame, self._context = runtime, frame, context

    def _assert_active(self, starting=False):
        if not self._context._active:
            raise TaskContractError("VF_TASK_CONTEXT_EXITED", "Node invocation has exited")
        if starting and self._context._stopping:
            raise TaskCancelled("VF_ABORTED: Node invocation is stopping")

    def start(self, key, inputs):
        self._assert_active(starting=True)
        return self._runtime._tasks.start(self._runtime, self._frame, key, inputs)

    def wait_any(self, refs):
        self._assert_active()
        return self._runtime._tasks.wait_any(refs, self._runtime._signal)

    def request_stop(self, refs, reason=None):
        self._assert_active()
        return self._runtime._tasks.request_stop(refs, reason)

    def wait_all_exited(self, refs):
        self._assert_active()
        return self._runtime._tasks.wait_all_exited(refs)


class NodeRunContext:
    def __init__(self, runtime, frame):
        allowed = {}
        descriptor = runtime.registry.descriptor(frame.type_used)
        for requirement in descriptor.capabilities:
            supplied = runtime._capabilities.get(requirement.id)
            if not isinstance(supplied, Mapping):
                raise TaskContractError("VF_CAPABILITY_MISSING", f"capability '{requirement.id}' was not supplied")
            operations = requirement.operations or tuple(supplied)
            if any(not callable(supplied.get(operation)) for operation in operations):
                raise TaskContractError("VF_CAPABILITY_MISSING", f"capability '{requirement.id}' is missing a declared operation")
            allowed[requirement.id] = MappingProxyType({operation:supplied[operation] for operation in operations})
        self.capabilities = MappingProxyType(allowed)
        self._runtime, self._frame = runtime, frame
        self._active, self._stopping = True, False
        self.signal = CancellationSignal()
        self._unsubscribe = runtime._signal.subscribe(self.signal.request_stop)

    def close(self):
        self._stopping = True
        try:
            self.signal.request_stop("Node exiting")
            if self.signal._callback_errors:
                raise ExceptionGroup("Node cancellation cleanup failed", self.signal._callback_errors)
        finally:
            self._active = False
            self._unsubscribe()

    def trace(self, kind, details=None):
        self._runtime._record_runtime_event(kind, self._frame.id, self._frame.type_used, details=details)

    @property
    def tasks(self):
        if self._frame.flow_kind != "task_manager":
            raise TaskContractError("VF_TASK_CONTROL_FORBIDDEN", "task control requires task_manager")
        return TaskController(self._runtime, self._frame, self)
