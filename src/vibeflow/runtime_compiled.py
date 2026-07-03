from __future__ import annotations

from .runtime_errors import PipelineRuntimeError


def run_compiled_steps(runtime, state) -> None:
    ready = list(runtime._initial_ready_nodes(state))
    queued = set(ready)
    for _ in range(runtime._plan.max_steps):
        if not ready:
            runtime.trace.stop_reason = "no_ready_nodes"
            return
        node_name = ready.pop(0)
        queued.discard(node_name)
        if not runtime._requirements_available(node_name, state):
            continue
        outputs = runtime._run_node(node_name, state)
        runtime.trace.step_count += 1
        if runtime._is_end_terminal(node_name):
            runtime.trace.stop_reason = "completed"
            return
        runtime._clear_conditional_outgoing(node_name, state)
        for edge in runtime._activated_edges(node_name, outputs, state):
            runtime._activate_edge(edge, state)
            runtime._deliver_outputs(edge, outputs, state)
            if edge.target not in queued:
                ready.append(edge.target)
                queued.add(edge.target)
    runtime.trace.stop_reason = "max_steps"
    raise PipelineRuntimeError(f"pipeline exceeded max_steps={runtime._plan.max_steps}")
