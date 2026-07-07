from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Mapping

from .compiler import explicit_flow_cycles
from .graph_config import EdgeSpec
from .runtime_errors import PipelineRuntimeError
from .runtime_helpers import elapsed_ms
from .summaries import summarize_mapping

if TYPE_CHECKING:
    from .execution_plan import ExecutionPlan, NodeFrame
    from .runtime import PipelineRuntime


@dataclass(frozen=True)
class CompiledBlockResult:
    last_node: str
    outputs: Mapping[str, object]


@dataclass(frozen=True)
class CompiledBlock:
    name: str
    entry: str
    exits: tuple[str, ...]
    nodes: tuple[str, ...]
    edge_routes: Mapping[str, tuple[EdgeSpec, ...]]
    callable: Callable[["PipelineRuntime", object], CompiledBlockResult]
    source: str
    supports_full_trace: bool = False
    supports_node_hooks: bool = False
    kind: str = "graph"
    mode: str = "generated"
    path: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Instrumentation:
    trace: str
    node_hooks: bool
    node_events: bool
    node_failure_events: bool
    block_output_summary: bool
    record_internal_edges: bool


def compile_blocks(plan: "ExecutionPlan", runtime_options: object | None = None) -> tuple[CompiledBlock, ...]:
    instrumentation = _instrumentation(runtime_options)
    blocks: list[CompiledBlock] = []
    for name in plan.order:
        frame = plan.frames[name]
        if frame.is_loop and _loop_block_compilable(frame):
            blocks.append(_compile_loop_block(frame, instrumentation))
        elif frame.is_nodeset and _nodeset_block_compilable(frame):
            blocks.append(_compile_nodeset_block(frame, instrumentation))
    if _graph_block_compilable(plan):
        blocks.append(_compile_generated_graph_block(plan, instrumentation))
    return tuple(blocks)


def graph_block(plan: "ExecutionPlan") -> CompiledBlock | None:
    for block in plan.blocks:
        if block.kind == "graph":
            return block
    return None


def loop_block(plan: "ExecutionPlan", node_name: str) -> CompiledBlock | None:
    expected = f"loop:{node_name}"
    for block in plan.blocks:
        if block.kind == "loop" and block.name == expected:
            return block
    return None


def nodeset_block(plan: "ExecutionPlan", node_name: str) -> CompiledBlock | None:
    expected = f"nodeset:{node_name}"
    for block in plan.blocks:
        if block.kind == "nodeset" and block.name == expected:
            return block
    return None


def explain_block_compilation(plan: "ExecutionPlan") -> tuple[dict[str, object], ...]:
    findings: list[dict[str, object]] = []
    _collect_block_compile_findings(plan, findings=findings, path=())
    return tuple(findings)


def _instrumentation(runtime_options: object | None) -> _Instrumentation:
    trace = str(getattr(runtime_options, "trace", "full"))
    node_hooks = bool(getattr(runtime_options, "node_hooks", True))
    return _Instrumentation(
        trace=trace,
        node_hooks=node_hooks,
        node_events=trace == "full",
        node_failure_events=trace == "full" or node_hooks,
        block_output_summary=trace == "full" or node_hooks,
        record_internal_edges=trace == "full",
    )


def _compile_generated_graph_block(plan: "ExecutionPlan", instrumentation: _Instrumentation) -> CompiledBlock:
    block_name = f"graph:{plan.order[0]}"
    nodes = tuple(plan.order)
    source = _generated_graph_block_source(block_name, nodes, instrumentation)
    namespace = {
        "CompiledBlockResult": CompiledBlockResult,
        "elapsed_ms": elapsed_ms,
        "frames": dict(plan.frames),
        "now": time.perf_counter,
        "PipelineRuntimeError": PipelineRuntimeError,
        "summarize_mapping": summarize_mapping,
    }
    exec(source, namespace)
    compiled_block = namespace["compiled_block"]

    return CompiledBlock(
        name=block_name,
        entry=nodes[0],
        exits=(nodes[-1],),
        nodes=nodes,
        edge_routes={node: tuple(plan.frames[node].outgoing) for node in nodes},
        callable=compiled_block,
        source=source,
        supports_full_trace=instrumentation.trace == "full",
        supports_node_hooks=instrumentation.node_hooks,
        kind="graph",
        mode="generated",
    )


def _compile_loop_block(frame: "NodeFrame", instrumentation: _Instrumentation) -> CompiledBlock:
    block_name = f"loop:{frame.name}"

    def compiled_loop_block(runtime: "PipelineRuntime", inputs: object) -> CompiledBlockResult:
        outputs = runtime._execute_loop_block(frame.name, inputs)
        return CompiledBlockResult(last_node=frame.name, outputs=outputs)

    return CompiledBlock(
        name=block_name,
        entry=frame.name,
        exits=(frame.name,),
        nodes=(frame.name,),
        edge_routes={frame.name: ()},
        callable=compiled_loop_block,
        source=_loop_block_source(frame, instrumentation),
        supports_full_trace=instrumentation.trace == "full",
        supports_node_hooks=instrumentation.node_hooks,
        kind="loop",
        mode="generated",
        path=(frame.name,),
    )


def _compile_nodeset_block(frame: "NodeFrame", instrumentation: _Instrumentation) -> CompiledBlock:
    block_name = f"nodeset:{frame.name}"

    def compiled_nodeset_block(runtime: "PipelineRuntime", inputs: object) -> CompiledBlockResult:
        outputs = runtime._execute_nodeset_block(frame.name, inputs)
        return CompiledBlockResult(last_node=frame.name, outputs=outputs)

    return CompiledBlock(
        name=block_name,
        entry=frame.name,
        exits=(frame.name,),
        nodes=(frame.name,),
        edge_routes={frame.name: ()},
        callable=compiled_nodeset_block,
        source=_nodeset_block_source(frame, instrumentation),
        supports_full_trace=instrumentation.trace == "full",
        supports_node_hooks=instrumentation.node_hooks,
        kind="nodeset",
        mode="generated",
        path=(frame.name,),
    )


def _generated_graph_block_source(name: str, nodes: tuple[str, ...], instrumentation: _Instrumentation) -> str:
    lines = [
        "def compiled_block(runtime, state):",
        f"    # generated ready-queue graph block: {name}",
        f"    # nodes: {nodes!r}",
        "    started = now()",
        f"    block_name = {name!r}",
        f"    block_nodes = {nodes!r}",
        "    runtime._record_runtime_event('block_enter', block_name, 'block')",
        "    runtime._call_runtime_plugins('before_block', block_name, block_nodes)",
        "    ready = list(runtime._initial_ready_nodes(state))",
        "    queued = set(ready)",
        "    outputs = {}",
        "    last_node = ''",
        "    steps = 0",
        "    counted = False",
        "    def finish(last_node):",
        "        nonlocal counted",
        "        if not counted:",
        "            runtime.trace.step_count += steps",
        "            counted = True",
    ]
    if instrumentation.block_output_summary:
        lines.extend(
            [
                "        runtime._record_runtime_event(",
                "            'block_exit',",
                "            block_name,",
                "            'block',",
                "            output_summary=summarize_mapping(outputs),",
                "            elapsed_ms=elapsed_ms(started),",
                "        )",
            ]
        )
    else:
        lines.extend(
            [
                "        runtime._record_runtime_event(",
                "            'block_exit',",
                "            block_name,",
                "            'block',",
                "            elapsed_ms=elapsed_ms(started),",
                "        )",
            ]
        )
    lines.extend(
        [
            "        runtime._call_runtime_plugins('after_block', block_name, block_nodes)",
            "        return CompiledBlockResult(last_node=last_node, outputs=outputs)",
            "    try:",
            "        for _ in range(runtime._plan.max_steps):",
            "            if not ready:",
            "                runtime.trace.stop_reason = 'no_ready_nodes'",
            "                return finish(last_node)",
            "            current = ready.pop(0)",
            "            queued.discard(current)",
            "            if current not in frames:",
            "                raise PipelineRuntimeError(f'compiled block reached unknown node: {current}')",
            "            if not runtime._requirements_available(current, state):",
            "                continue",
            "            frame = frames[current]",
            "            outputs = runtime._run_compiled_frame(frame, state)",
            "            last_node = current",
            "            steps += 1",
            "            if runtime._is_end_terminal(current):",
            "                runtime.trace.stop_reason = 'completed'",
            "                return finish(current)",
            "            runtime._clear_conditional_outgoing(current, state)",
            "            active_edges = runtime._activated_edges(current, outputs, state)",
            "            active_pairs = {edge.pair for edge in active_edges}",
            "            for edge in active_edges:",
            "                runtime._activate_edge(edge, state)",
            "                runtime._deliver_outputs(edge, outputs, state)",
            "                if edge.target not in queued:",
            "                    ready.append(edge.target)",
            "                    queued.add(edge.target)",
            "            runtime._deliver_transfer_only_edges(current, outputs, state, active_pairs)",
            "        runtime.trace.stop_reason = 'max_steps'",
            "        raise PipelineRuntimeError(f'pipeline exceeded max_steps={runtime._plan.max_steps}')",
            "    except Exception as exc:",
            "        if not counted:",
            "            runtime.trace.step_count += steps",
            "            counted = True",
            "        runtime._record_runtime_event(",
            "            'block_failed',",
            "            block_name,",
            "            'block',",
            "            failure=str(exc),",
            "            elapsed_ms=elapsed_ms(started),",
            "        )",
            "        runtime._call_runtime_plugins('block_failed', block_name, block_nodes, str(exc))",
            "        raise",
            f"# trace={instrumentation.trace!r} node_hooks={instrumentation.node_hooks!r}",
        ]
    )
    return "\n".join(lines)


def _loop_block_source(frame: "NodeFrame", instrumentation: _Instrumentation) -> str:
    return "\n".join(
        [
            "def compiled_loop_block(runtime, inputs):",
            f"    # structured LoopBlock for {frame.name!r}",
            f"    # body: {frame.loop_spec.body!r}",
            f"    # max_iterations: {frame.loop_spec.max_iterations!r}",
            f"    # stop: {_loop_stop_text(frame)!r}",
            f"    outputs = runtime._execute_loop_block({frame.name!r}, inputs)",
            f"    return CompiledBlockResult(last_node={frame.name!r}, outputs=outputs)",
            f"# trace={instrumentation.trace!r} node_hooks={instrumentation.node_hooks!r}",
        ]
    )


def _nodeset_block_source(frame: "NodeFrame", instrumentation: _Instrumentation) -> str:
    return "\n".join(
        [
            "def compiled_nodeset_block(runtime, inputs):",
            f"    # generated nodeset block for {frame.name!r}",
            f"    # body: {frame.nodeset_type_key!r}",
            f"    outputs = runtime._execute_nodeset_block({frame.name!r}, inputs)",
            f"    return CompiledBlockResult(last_node={frame.name!r}, outputs=outputs)",
            f"# trace={instrumentation.trace!r} node_hooks={instrumentation.node_hooks!r}",
        ]
    )


def _graph_block_compilable(plan: "ExecutionPlan") -> bool:
    if not plan.order:
        return False
    nodes_by_name = {node.name: node for node in plan.graph.nodes}
    if explicit_flow_cycles(nodes_by_name, plan.graph.edges):
        return False
    for name in plan.order:
        frame = plan.frames[name]
        if frame.is_planned_stub:
            return False
        if frame.is_nodeset and not frame.async_mode and not _nodeset_block_compilable(frame):
            return False
        if frame.is_loop and frame.async_mode:
            return False
        if frame.is_loop and not _loop_block_compilable(frame):
            return False
    return True


def _nodeset_block_compilable(frame: "NodeFrame") -> bool:
    if not frame.is_nodeset or frame.subplan is None or frame.async_mode or frame.is_planned_stub:
        return False
    return graph_block(frame.subplan) is not None


def _loop_block_compilable(frame: "NodeFrame") -> bool:
    if not frame.is_loop or frame.subplan is None:
        return False
    return graph_block(frame.subplan) is not None


def _collect_block_compile_findings(plan: "ExecutionPlan", *, findings: list[dict[str, object]], path: tuple[str, ...]) -> None:
    graph_reason = _graph_block_reason(plan)
    findings.append(
        {
            "path": ".".join(path) if path else "pipeline",
            "kind": "graph",
            "compiled": graph_reason == "",
            "reason": graph_reason,
        }
    )
    for name in plan.order:
        frame = plan.frames[name]
        node_path = (*path, name)
        if frame.is_nodeset:
            reason = _nodeset_block_reason(frame)
            findings.append(
                {
                    "path": ".".join(node_path),
                    "kind": "nodeset",
                    "compiled": reason == "",
                    "reason": reason,
                }
            )
        elif frame.is_loop:
            reason = _loop_block_reason(frame)
            findings.append(
                {
                    "path": ".".join(node_path),
                    "kind": "loop",
                    "compiled": reason == "",
                    "reason": reason,
                }
            )
        if frame.subplan is not None:
            _collect_block_compile_findings(frame.subplan, findings=findings, path=node_path)


def _graph_block_reason(plan: "ExecutionPlan") -> str:
    if not plan.order:
        return "empty_graph"
    nodes_by_name = {node.name: node for node in plan.graph.nodes}
    cycles = explicit_flow_cycles(nodes_by_name, plan.graph.edges)
    if cycles:
        return "explicit_flow_cycle"
    for name in plan.order:
        frame = plan.frames[name]
        if frame.is_planned_stub:
            return f"{name}:planned_stub"
        if frame.is_nodeset and not frame.async_mode:
            reason = _nodeset_block_reason(frame)
            if reason:
                return f"{name}:{reason}"
        if frame.is_loop:
            if frame.async_mode:
                return f"{name}:async_loop={frame.async_mode}"
            reason = _loop_block_reason(frame)
            if reason:
                return f"{name}:{reason}"
    return ""


def _nodeset_block_reason(frame: "NodeFrame") -> str:
    if not frame.is_nodeset:
        return "not_nodeset"
    if frame.async_mode:
        return f"async_mode={frame.async_mode}"
    if frame.is_planned_stub:
        return "planned_stub"
    if frame.subplan is None:
        return "missing_subplan"
    if graph_block(frame.subplan) is None:
        child_reason = _graph_block_reason(frame.subplan)
        return f"body_not_graph_compiled:{child_reason or 'unknown'}"
    return ""


def _loop_block_reason(frame: "NodeFrame") -> str:
    if not frame.is_loop:
        return "not_loop"
    if frame.async_mode:
        return f"async_mode={frame.async_mode}"
    if frame.subplan is None:
        return "missing_subplan"
    if graph_block(frame.subplan) is None:
        child_reason = _graph_block_reason(frame.subplan)
        return f"body_not_graph_compiled:{child_reason or 'unknown'}"
    return ""


def _loop_stop_text(frame: "NodeFrame") -> str:
    spec = frame.loop_spec
    if spec.stop_after:
        return f"stop_after: {spec.stop_after}"
    if spec.stop_when.source:
        return f"stop_when: {spec.stop_when.source} == {str(spec.stop_when.equals).lower()}"
    return "unset"
