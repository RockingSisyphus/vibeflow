"""One ready/dispatch state machine with synchronous and asyncio execution."""
import asyncio
from vibeflow.coordination.async_support import cancel_once
from dataclasses import dataclass

from vibeflow.core.flow import JOIN_POLICY_ALL
from .errors import PipelineRuntimeError


@dataclass(eq=False)
class _Dispatch:
    limit: int
    active: int = 0


class _Schedule:
    def __init__(self, runtime, state):
        self.runtime, self.state = runtime, state
        self.ready = list(runtime._initial_ready_nodes(state))
        self.queued = set(self.ready)
        self.pending, self.active = {}, {}
        self.last = ("", {})

    def admit(self, running):
        runtime, state = self.runtime, self.state
        result = []
        for _ in range(len(self.ready)):
            name = self.ready.pop(0)
            dispatches = self.pending.get(name, ())
            if name in running or any(d.active >= d.limit for d in dispatches):
                self.ready.append(name)
                continue
            self.queued.discard(name)
            if not runtime._requirements_available(name, state):
                continue
            if runtime.trace.step_count >= runtime._plan.max_steps:
                runtime.trace.stop_reason = "max_steps"
                raise PipelineRuntimeError(f"pipeline exceeded max_steps={runtime._plan.max_steps}")
            self.pending.pop(name, None)
            for dispatch in dispatches:
                dispatch.active += 1
            self.active[name] = dispatches
            frame = runtime._frames[name]
            inputs = runtime._resolve_inputs(frame, state)
            state.last_inputs[name] = inputs
            state.inboxes[name] = []
            if frame.join_policy == JOIN_POLICY_ALL:
                for edge in frame.incoming:
                    state.active_edges.discard(edge.pair)
            runtime.trace.step_count += 1
            result.append((name, inputs))
        return result

    def complete(self, name, outputs):
        runtime, state = self.runtime, self.state
        for dispatch in self.active.pop(name, ()):
            dispatch.active -= 1
        runtime.trace.current_node = name
        self.last = (name, outputs)
        runtime._record_node_output_candidates(name, outputs, state)
        runtime._clear_conditional_outgoing(name, state)
        active = runtime._activated_edges(name, outputs, state)
        for edge in active:
            runtime._activate_edge(edge, state)
        runtime._deliver_transfer_edges(name, outputs, state)
        frame = runtime._frames[name]
        dispatch = _Dispatch(frame.max_concurrency) if len({e.target for e in frame.outgoing}) > 1 else None
        for target in runtime._scheduled_targets(name, active):
            if dispatch is not None:
                self.pending.setdefault(target, set()).add(dispatch)
            if target not in self.queued:
                self.ready.append(target)
                self.queued.add(target)
        if runtime._is_end_terminal(name):
            runtime.trace.stop_reason = "completed"


def run_graph(runtime, state):
    schedule = _Schedule(runtime, state)
    while schedule.ready:
        runtime._signal.throw_if_aborted()
        admitted = schedule.admit(())
        if not admitted:
            break
        for name, inputs in admitted:
            runtime.trace.current_node = name
            schedule.complete(name, runtime._execute_frame(runtime._frames[name], inputs))
    runtime.trace.stop_reason = runtime.trace.stop_reason or "no_ready_nodes"
    return schedule.last


async def run_graph_async(runtime, state):
    schedule = _Schedule(runtime, state)
    running = {}
    failure = None
    loop = asyncio.get_running_loop()
    def stop(reason):
        def cancel():
            for task in tuple(running.values()):
                cancel_once(task)
        loop.call_soon_threadsafe(cancel)
    unsubscribe = runtime._signal.subscribe(stop)
    try:
        while schedule.ready or running:
            runtime._signal.throw_if_aborted()
            for name, inputs in schedule.admit(running):
                running[name] = asyncio.create_task(runtime._execute_frame_async(runtime._frames[name], inputs),
                                                     name=f"vibeflow-node:{name}")
            if not running:
                break
            done, _ = await asyncio.wait(tuple(running.values()), return_when=asyncio.FIRST_COMPLETED)
            for name, task in tuple(running.items()):
                if task not in done:
                    continue
                del running[name]
                runtime.trace.current_node = name
                schedule.complete(name, task.result())
    except BaseException as error:
        failure = runtime._signal.fail(error)
    finally:
        unsubscribe()
        for task in running.values():
            cancel_once(task)
        outcomes = asyncio.gather(*running.values(), return_exceptions=True)
        while not outcomes.done():
            try:
                await asyncio.shield(outcomes)
            except asyncio.CancelledError:
                continue
        for outcome in outcomes.result():
            if isinstance(outcome, BaseException):
                runtime._signal.record_error(outcome)
    if failure is not None:
        raise runtime._signal.error
    runtime.trace.stop_reason = runtime.trace.stop_reason or "no_ready_nodes"
    return schedule.last
