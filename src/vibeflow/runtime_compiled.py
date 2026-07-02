from __future__ import annotations

import time

from .context import Context
from .runtime_errors import PipelineRuntimeError
from .runtime_helpers import elapsed_ms
from .summaries import summarize_mapping


def run_compiled_steps(runtime, context: Context) -> None:
    if runtime.runtime_options.trace == "full" or runtime.runtime_options.node_hooks:
        runtime._run_steps(context)
        return
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
            outputs = run_compiled_block(runtime, block, context)
            runtime.trace.step_count += len(block.nodes)
            node_name = block.nodes[-1]
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


def run_compiled_block(runtime, block, context: Context):
    started = time.perf_counter()
    runtime._record_runtime_event("block_enter", block.name, "block")
    runtime._call_runtime_plugins("before_block", block.name, block.nodes)
    outputs = {}
    try:
        for node_name in block.nodes:
            frame = runtime._frames[node_name]
            runtime.trace.current_node = node_name
            outputs = runtime._execute_pure_outputs(frame, {key: context.get(key) for key in frame.requires})
            for key, value in outputs.items():
                context.set(str(key), value)
            runtime._mark_node_run(frame.name)
        runtime._record_runtime_event("block_exit", block.name, "block", output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
        runtime._call_runtime_plugins("after_block", block.name, block.nodes)
        return outputs
    except Exception as exc:
        runtime._record_runtime_event("block_failed", block.name, "block", failure=str(exc), elapsed_ms=elapsed_ms(started))
        runtime._call_runtime_plugins("block_failed", block.name, block.nodes, str(exc))
        raise
