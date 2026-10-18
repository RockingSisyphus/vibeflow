"""Execute ordinary graph calls; all independent ready calls may run concurrently.

Only this coordinator changes graph mailboxes and activates edges. Workers own
their Node invocation through its real return, including finally and SDK cleanup.
Each dispatch invocation owns its own admission budget; there is no task graph.
"""

from contextvars import copy_context
from dataclasses import dataclass
from queue import Queue
from threading import Thread

from vibeflow.core.flow import JOIN_POLICY_ALL

from .errors import DelegateCliExit, PipelineRuntimeError


@dataclass(eq=False)
class _Dispatch:
    limit: int
    active: int = 0


def run_graph(runtime, state):
    ready = list(runtime._initial_ready_nodes(state))
    queued = set(ready)
    running = {}
    pending_dispatches = {}
    active_dispatches = {}
    finished = Queue()
    last_node, last_outputs = "", {}
    failure = None

    def execute(name, inputs):
        try:
            outputs = runtime._execute_frame(runtime._frames[name], inputs)
            finished.put((name, outputs, None))
        except BaseException as error:
            finished.put((name, None, error))

    try:
        while ready or running:
            runtime._signal.throw_if_aborted()
            eligible = []
            for _ in range(len(ready)):
                name = ready.pop(0)
                if name in running:
                    ready.append(name)
                    continue
                dispatches = pending_dispatches.get(name, ())
                if any(dispatch.active >= dispatch.limit for dispatch in dispatches):
                    ready.append(name)
                    continue
                queued.discard(name)
                if runtime._requirements_available(name, state):
                    pending_dispatches.pop(name, None)
                    if dispatches:
                        for dispatch in dispatches:
                            dispatch.active += 1
                        active_dispatches[name] = dispatches
                    eligible.append(name)
            concurrent = bool(running) or len(eligible) > 1
            for name in eligible:
                if runtime.trace.step_count >= runtime._plan.max_steps:
                    runtime.trace.stop_reason = "max_steps"
                    raise PipelineRuntimeError(
                        f"pipeline exceeded max_steps={runtime._plan.max_steps}"
                    )
                frame = runtime._frames[name]
                runtime.trace.current_node = name
                inputs = runtime._resolve_inputs(frame, state)
                state.last_inputs[name] = inputs
                state.inboxes[name] = []
                if frame.join_policy == JOIN_POLICY_ALL:
                    for edge in frame.incoming:
                        state.active_edges.discard(edge.pair)
                runtime.trace.step_count += 1
                if concurrent:
                    context = copy_context()
                    thread = Thread(
                        target=context.run,
                        args=(execute, name, inputs),
                        name=f"vibeflow-node:{name}",
                    )
                    running[name] = thread
                    try:
                        thread.start()
                    except BaseException:
                        del running[name]
                        raise
                else:
                    running[name] = None
                    execute(name, inputs)
            if not running:
                break
            name, outputs, error = finished.get()
            thread = running.pop(name)
            if thread is not None:
                thread.join()
            for dispatch in active_dispatches.pop(name, ()):
                dispatch.active -= 1
            if error is not None:
                runtime.trace.current_node = name
                raise error
            runtime.trace.current_node = name
            last_node, last_outputs = name, outputs
            runtime._record_node_output_candidates(name, outputs, state)
            runtime._clear_conditional_outgoing(name, state)
            active = runtime._activated_edges(name, outputs, state)
            for edge in active:
                runtime._activate_edge(edge, state)
            runtime._deliver_transfer_edges(name, outputs, state)
            targets = runtime._scheduled_targets(name, active)
            frame = runtime._frames[name]
            dispatch = (
                _Dispatch(frame.max_concurrency)
                if len({edge.target for edge in frame.outgoing}) > 1
                else None
            )
            for target in targets:
                if dispatch is not None:
                    pending_dispatches.setdefault(target, set()).add(dispatch)
                if target not in queued:
                    ready.append(target)
                    queued.add(target)
            if runtime._is_end_terminal(name):
                runtime.trace.stop_reason = "completed"
        runtime.trace.stop_reason = runtime.trace.stop_reason or "no_ready_nodes"
        return last_node, last_outputs
    except BaseException as error:
        failure = error
        runtime._signal.request_stop("workflow failed")
    finally:
        # A stop signal never substitutes for a real thread exit.
        for thread in running.values():
            if thread is not None:
                thread.join()
        errors = []
        while not finished.empty():
            name, _, cleanup = finished.get()
            if cleanup is not None and getattr(cleanup, "code", "") != "VF_ABORTED":
                errors.append((name, cleanup))
        if failure is not None:
            if isinstance(failure, DelegateCliExit):
                framework = next(
                    (
                        (name, error)
                        for name, error in errors
                        if not isinstance(error, DelegateCliExit)
                    ),
                    None,
                )
                if framework is not None:
                    runtime.trace.current_node, failure = framework
                    errors = [
                        (name, error) for name, error in errors if error is not failure
                    ]
                elif any(isinstance(error, DelegateCliExit) for _, error in errors):
                    failure = PipelineRuntimeError(
                        "multiple business exits in concurrent graph branches"
                    )
            for _, cleanup in errors:
                failure.cleanup_errors = [
                    *getattr(failure, "cleanup_errors", ()), cleanup
                ]
    if failure is not None:
        raise failure
