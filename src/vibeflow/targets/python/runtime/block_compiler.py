from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Mapping, Protocol

from vibeflow.core.compiler import explicit_flow_cycles
from vibeflow.core.flow import EdgeSpec
from vibeflow.targets.python.runtime.errors import DelegateCliExit
from vibeflow.targets.python.runtime.helpers import elapsed_ms
from vibeflow.targets.python.runtime.summaries import summarize_mapping

if TYPE_CHECKING:
    class ExecutionPlan(Protocol): ...
    class NodeFrame(Protocol): ...
    class PipelineRuntime(Protocol): ...


@dataclass(frozen=True)
class CompiledBlockResult:
    last_node: str
    outputs: Mapping[str, object]


@dataclass(frozen=True)
class PythonCompiledBlock:
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


CompiledBlock = PythonCompiledBlock


def compile_blocks(plan: "ExecutionPlan", runtime_options: object | None = None) -> tuple[CompiledBlock, ...]:
    blocks: list[CompiledBlock] = []
    for name in plan.order:
        frame = plan.frames[name]
        if frame.is_loop and _loop_block_compilable(frame):
            blocks.append(_compile_loop_block(frame))
        elif frame.is_nodeset and _nodeset_block_compilable(frame):
            blocks.append(_compile_nodeset_block(frame))
    if _graph_block_compilable(plan):
        blocks.append(_compile_generated_graph_block(plan))
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


def _compile_generated_graph_block(plan: "ExecutionPlan") -> CompiledBlock:
    block_name = f"graph:{plan.order[0]}"
    nodes = tuple(plan.order)
    source = _generated_graph_block_source(block_name, nodes)
    namespace = {}
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
        supports_full_trace=True,
        supports_node_hooks=True,
        kind="graph",
        mode="generated",
    )


def _compile_loop_block(frame: "NodeFrame") -> CompiledBlock:
    block_name = f"loop:{frame.id}"

    def compiled_loop_block(runtime: "PipelineRuntime", inputs: object) -> CompiledBlockResult:
        outputs = runtime._execute_loop_block(frame.id, inputs)
        return CompiledBlockResult(last_node=frame.id, outputs=outputs)

    return CompiledBlock(
        name=block_name,
        entry=frame.id,
        exits=(frame.id,),
        nodes=(frame.id,),
        edge_routes={frame.id: ()},
        callable=compiled_loop_block,
        source=_loop_block_source(frame),
        supports_full_trace=True,
        supports_node_hooks=True,
        kind="loop",
        mode="generated",
        path=(frame.id,),
    )


def _compile_nodeset_block(frame: "NodeFrame") -> CompiledBlock:
    block_name = f"nodeset:{frame.id}"

    def compiled_nodeset_block(runtime: "PipelineRuntime", inputs: object) -> CompiledBlockResult:
        outputs = runtime._execute_nodeset_block(frame.id, inputs)
        return CompiledBlockResult(last_node=frame.id, outputs=outputs)

    return CompiledBlock(
        name=block_name,
        entry=frame.id,
        exits=(frame.id,),
        nodes=(frame.id,),
        edge_routes={frame.id: ()},
        callable=compiled_nodeset_block,
        source=_nodeset_block_source(frame),
        supports_full_trace=True,
        supports_node_hooks=True,
        kind="nodeset",
        mode="generated",
        path=(frame.id,),
    )


def run_graph_block(runtime, state, name, nodes):
    """Generated blocks add observation around the same graph coordinator."""
    from .scheduler import run_graph
    started = time.perf_counter()
    runtime._record_runtime_event("block_enter", name, "block")
    runtime._call_runtime_plugins("before_block", name, nodes)
    try:
        last_node, outputs = run_graph(runtime, state)
        summary = {"output_summary": summarize_mapping(outputs)} if runtime.runtime_options.trace == "full" or runtime.runtime_options.node_hooks else {}
        runtime._record_runtime_event("block_exit", name, "block", elapsed_ms=elapsed_ms(started), **summary)
        runtime._call_runtime_plugins("after_block", name, nodes)
        return CompiledBlockResult(last_node=last_node, outputs=outputs)
    except DelegateCliExit:
        raise
    except BaseException as error:
        runtime._record_runtime_event("block_failed", name, "block", failure=str(error), elapsed_ms=elapsed_ms(started))
        try:
            runtime._call_runtime_plugins("block_failed", name, nodes, str(error))
        except BaseException as cleanup:
            error.cleanup_errors = [*getattr(error,"cleanup_errors",()),cleanup]
        raise


def _generated_graph_block_source(name: str, nodes: tuple[str, ...]) -> str:
    return "\n".join([
        "def compiled_block(runtime, state):",
        "    from vibeflow.targets.python.runtime.block_compiler import run_graph_block",
        "    return run_graph_block(runtime, state, 'graph:' + runtime._plan.order[0], runtime._plan.order)",
    ])


def _loop_block_source(frame: "NodeFrame") -> str:
    return "\n".join(
        [
            "def compiled_loop_block(runtime, inputs):",
            f"    # structured LoopBlock for {frame.id!r}",
            f"    # body: {frame.loop_spec.body!r}",
            f"    # max_iterations: {frame.loop_spec.max_iterations!r}",
            f"    # stop: {_loop_stop_text(frame)!r}",
            f"    outputs = runtime._execute_loop_block({frame.id!r}, inputs)",
            f"    return CompiledBlockResult(last_node={frame.id!r}, outputs=outputs)",
            "# runtime trace and hooks are selected per invocation",
        ]
    )


def _nodeset_block_source(frame: "NodeFrame") -> str:
    return "\n".join(
        [
            "def compiled_nodeset_block(runtime, inputs):",
            f"    # generated nodeset block for {frame.id!r}",
            f"    # body: {frame.nodeset_type_id!r}",
            f"    outputs = runtime._execute_nodeset_block({frame.id!r}, inputs)",
            f"    return CompiledBlockResult(last_node={frame.id!r}, outputs=outputs)",
            "# runtime trace and hooks are selected per invocation",
        ]
    )


def _graph_block_compilable(plan: "ExecutionPlan") -> bool:
    if not plan.order:
        return False
    nodes_by_name = {node.id: node for node in plan.graph.nodes}
    if explicit_flow_cycles(nodes_by_name, plan.compiled.resolved_schedule_edges):
        return False
    for name in plan.order:
        frame = plan.frames[name]
        if frame.is_planned_stub:
            return False
        if frame.is_nodeset and not _nodeset_block_compilable(frame):
            return False
        if frame.is_loop and not _loop_block_compilable(frame):
            return False
    return True


def _nodeset_block_compilable(frame: "NodeFrame") -> bool:
    if not frame.is_nodeset or frame.subplan is None or frame.is_planned_stub:
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
    nodes_by_name = {node.id: node for node in plan.graph.nodes}
    cycles = explicit_flow_cycles(nodes_by_name, plan.compiled.resolved_schedule_edges)
    if cycles:
        return "explicit_flow_cycle"
    for name in plan.order:
        frame = plan.frames[name]
        if frame.is_planned_stub:
            return f"{name}:planned_stub"
        if frame.is_nodeset:
            reason = _nodeset_block_reason(frame)
            if reason:
                return f"{name}:{reason}"
        if frame.is_loop:
            reason = _loop_block_reason(frame)
            if reason:
                return f"{name}:{reason}"
    return ""


def _nodeset_block_reason(frame: "NodeFrame") -> str:
    if not frame.is_nodeset:
        return "not_nodeset"
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


__all__ = ["CompiledBlock", "CompiledBlockResult", "PythonCompiledBlock", "compile_blocks", "explain_block_compilation", "graph_block", "loop_block", "nodeset_block"]
