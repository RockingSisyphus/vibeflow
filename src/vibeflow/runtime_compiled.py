from __future__ import annotations

from .context import Context
from .runtime_errors import PipelineRuntimeError


def run_compiled_steps(runtime, context: Context) -> None:
    ready = list(runtime._initial_ready_nodes(context))
    queued = set(ready)
    for _ in range(runtime._plan.max_steps):
        if not ready:
            runtime.trace.stop_reason = "no_ready_nodes"
            return
        node_name = ready.pop(0)
        queued.discard(node_name)
        block = runtime._plan.block_for(node_name)
        if block is not None and runtime._requirements_available(block.nodes[0], context):
            result = block.callable(runtime, context)
            outputs = result.outputs
            node_name = result.last_node
        else:
            if not runtime._requirements_available(node_name, context):
                continue
            outputs = runtime._run_node(node_name, context)
            runtime.trace.step_count += 1
        if runtime._is_end_terminal(node_name):
            runtime.trace.stop_reason = "completed"
            return
        for edge in runtime._activated_edges(node_name, outputs, context):
            runtime._record_edge(edge)
            if edge.target not in queued:
                ready.append(edge.target)
                queued.add(edge.target)
    runtime.trace.stop_reason = "max_steps"
    raise PipelineRuntimeError(f"pipeline exceeded max_steps={runtime._plan.max_steps}")
