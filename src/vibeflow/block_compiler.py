from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Mapping

from .graph_config import EdgeSpec
from .node import FLOW_KIND_DECISION
from .runtime_errors import PipelineRuntimeError
from .runtime_helpers import condition_matches, elapsed_ms
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


@dataclass(frozen=True)
class _Instrumentation:
    trace: str
    node_hooks: bool
    node_events: bool
    node_failure_events: bool
    block_output_summary: bool
    record_internal_edges: bool


def compile_blocks(plan: "ExecutionPlan", runtime_options: object | None = None) -> tuple[CompiledBlock, ...]:
    # Inbox-mode runtime resolves inputs and delivers payloads through shared runtime
    # helpers. Old generated blocks used Context.get/set and are intentionally disabled.
    return ()
    instrumentation = _instrumentation(runtime_options)
    blocks: list[CompiledBlock] = []
    visited: set[str] = set()
    for name in plan.order:
        if name in visited or not _frame_compilable(plan.frames[name]):
            continue
        block_nodes = _cfg_region(name, plan.frames, plan.order)
        if len(block_nodes) > 1:
            block_name = f"block:{block_nodes[0]}"
            blocks.append(_compile_cfg_block(block_name, block_nodes, plan.frames, instrumentation))
            visited.update(block_nodes)
    return tuple(blocks)


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


def select_active_edges(edges: tuple[EdgeSpec, ...], outputs: Mapping[str, object], context: object) -> tuple[EdgeSpec, ...]:
    values = context.to_dict()
    values.update(dict(outputs))
    return tuple(edge for edge in edges if not edge.when or condition_matches(edge.when, values))


def _cfg_region(entry: str, frames: Mapping[str, "NodeFrame"], order: tuple[str, ...]) -> tuple[str, ...]:
    region: set[str] = {entry}
    pending = [entry]
    while pending:
        name = pending.pop(0)
        frame = frames[name]
        if not _outgoing_compilable(frame):
            continue
        for edge in frame.outgoing:
            target = edge.target
            if target not in frames or not _frame_compilable(frames[target]):
                continue
            if target not in region:
                region.add(target)
                pending.append(target)
    region = _prune_external_incoming(region, entry, frames)
    return tuple(name for name in order if name in region)


def _prune_external_incoming(region: set[str], entry: str, frames: Mapping[str, "NodeFrame"]) -> set[str]:
    pruned = set(region)
    changed = True
    while changed:
        changed = False
        for name in tuple(pruned):
            if name == entry:
                continue
            if any(edge.source not in pruned for edge in frames[name].incoming):
                pruned.remove(name)
                changed = True
    return pruned


def _compile_cfg_block(
    name: str,
    nodes: tuple[str, ...],
    frames: Mapping[str, "NodeFrame"],
    instrumentation: _Instrumentation,
) -> CompiledBlock:
    node_set = set(nodes)
    outgoing = {node: tuple(frames[node].outgoing) for node in nodes}
    source = _cfg_block_source(name, nodes, instrumentation)
    namespace = {
        "CompiledBlockResult": CompiledBlockResult,
        "elapsed_ms": elapsed_ms,
        "frames": dict(frames),
        "internal_targets": frozenset(nodes),
        "outgoing": outgoing,
        "now": time.perf_counter,
        "PipelineRuntimeError": PipelineRuntimeError,
        "select_active_edges": select_active_edges,
        "summarize_mapping": summarize_mapping,
    }
    exec(source, namespace)
    compiled_callable = namespace["compiled_block"]
    return CompiledBlock(
        name=name,
        entry=nodes[0],
        exits=(nodes[-1],),
        nodes=nodes,
        edge_routes={node: tuple(edge for edge in outgoing[node] if edge.target in node_set) for node in nodes},
        callable=compiled_callable,
        source=source,
        supports_full_trace=instrumentation.trace == "full",
        supports_node_hooks=instrumentation.node_hooks,
    )


def _cfg_block_source(name: str, nodes: tuple[str, ...], instrumentation: _Instrumentation) -> str:
    lines = _cfg_block_preamble_lines(name, nodes, instrumentation)
    for index, node_name in enumerate(nodes):
        lines.extend(_cfg_node_dispatch_lines(index, node_name, instrumentation))
    lines.extend(_cfg_block_failure_lines())
    return "\n".join(lines)


def _cfg_block_preamble_lines(name: str, nodes: tuple[str, ...], instrumentation: _Instrumentation) -> list[str]:
    lines = [
        "def compiled_block(runtime, context):",
        "    started = now()",
        f"    block_name = {name!r}",
        f"    block_nodes = {nodes!r}",
        "    runtime._record_runtime_event('block_enter', block_name, 'block')",
        "    runtime._call_runtime_plugins('before_block', block_name, block_nodes)",
        "    outputs = {}",
        "    steps = 0",
        "    counted = False",
        f"    current = {nodes[0]!r}",
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
            "        while True:",
            "            if runtime.trace.step_count + steps >= runtime._plan.max_steps:",
            "                runtime.trace.stop_reason = 'max_steps'",
            "                raise PipelineRuntimeError(f'pipeline exceeded max_steps={runtime._plan.max_steps}')",
        ]
    )
    return lines


def _cfg_node_dispatch_lines(index: int, node_name: str, instrumentation: _Instrumentation) -> list[str]:
    prefix = "if" if index == 0 else "elif"
    lines = [
        f"            {prefix} current == {node_name!r}:",
        f"                frame = frames[{node_name!r}]",
        f"                runtime.trace.current_node = {node_name!r}",
    ]
    lines.extend(_cfg_node_execution_lines(instrumentation))
    lines.extend(_cfg_node_context_lines(instrumentation))
    lines.extend(_cfg_node_route_lines(node_name, instrumentation))
    return lines


def _cfg_node_execution_lines(instrumentation: _Instrumentation) -> list[str]:
    if instrumentation.node_events or instrumentation.node_failure_events:
        lines = [
            "                node_started = now()",
            "                inputs = {}",
            "                try:",
            "                    inputs = {key: context.get(key) for key in frame.requires}",
        ]
        if instrumentation.node_hooks:
            lines.append("                    runtime._call_runtime_plugins('before_node', frame.name, frame.node_type, summarize_mapping(inputs))")
        lines.extend(
            [
                "                    execute = runtime._execute_pure_outputs",
                "                    outputs = execute(frame, inputs)",
                "                except Exception as exc:",
            ]
        )
        if instrumentation.node_failure_events:
            lines.extend(
                [
                    "                    runtime._record_runtime_event(",
                    "                        'node_failed',",
                    "                        frame.name,",
                    "                        frame.node_type,",
                    "                        input_summary=summarize_mapping(inputs),",
                    "                        failure=str(exc),",
                    "                        elapsed_ms=elapsed_ms(node_started),",
                    "                    )",
                ]
            )
        if instrumentation.node_hooks:
            lines.extend(
                [
                    "                    runtime._call_runtime_plugins('node_failed', frame.name, frame.node_type, str(exc))",
                ]
            )
        return [*lines, "                    raise"]
    return [
        "                inputs = {key: context.get(key) for key in frame.requires}",
        "                execute = runtime._execute_pure_outputs",
        "                outputs = execute(frame, inputs)",
    ]


def _cfg_node_context_lines(instrumentation: _Instrumentation) -> list[str]:
    lines = [
        "                for key, value in outputs.items():",
        "                    context.set(str(key), value)",
        "                runtime._mark_node_run(frame.name)",
    ]
    if instrumentation.node_events:
        lines.extend(_cfg_node_success_event_lines())
    if instrumentation.node_hooks:
        lines.append("                runtime._call_runtime_plugins('after_node', frame.name, frame.node_type, summarize_mapping(outputs))")
    return lines


def _cfg_node_route_lines(node_name: str, instrumentation: _Instrumentation) -> list[str]:
    lines = [
        "                steps += 1",
        f"                active_edges = select_active_edges(outgoing[{node_name!r}], outputs, context)",
        "                if len(active_edges) != 1:",
        f"                    return finish({node_name!r})",
        "                edge = active_edges[0]",
        "                if edge.target not in internal_targets:",
        f"                    return finish({node_name!r})",
    ]
    if instrumentation.record_internal_edges:
        lines.append("                runtime._record_edge(edge)")
    lines.extend(
        [
            "                current = edge.target",
            "                continue",
        ]
    )
    return lines


def _cfg_node_success_event_lines() -> list[str]:
    return [
        "                runtime._record_runtime_event(",
        "                    'node',",
        "                    frame.name,",
        "                    frame.node_type,",
        "                    input_summary=summarize_mapping(inputs),",
        "                    output_summary=summarize_mapping(outputs),",
        "                    elapsed_ms=elapsed_ms(node_started),",
        "                )",
    ]


def _cfg_block_failure_lines() -> list[str]:
    return [
        "            raise PipelineRuntimeError(f'compiled block reached unknown node: {current}')",
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
        "",
    ]


def _frame_compilable(frame: "NodeFrame") -> bool:
    return not frame.async_mode and not frame.is_nodeset and not frame.is_planned_stub


def _outgoing_compilable(frame: "NodeFrame") -> bool:
    return frame.flow_kind == FLOW_KIND_DECISION or len(frame.outgoing) <= 1
