from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vibeflow.targets.python.runtime.block_compiler import CompiledBlock, compile_blocks
from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.contracts import DataProvider, DataRequirement, provider_keys, requirement_types
from vibeflow.core.flow import (
    EdgeSpec,
    GraphConfig,
    IO_NODE_TYPE,
    IoSpec,
    LOOP_NODE_TYPES,
    LoopSpec,
    NodeSpec,
    STATUS_IMPLEMENTED,
    STATUS_PLANNED,
)
from vibeflow.core.nodeset_dependencies import nodeset_depth_violations
from vibeflow.core.constants import FLOW_KIND_GLOBAL_STATE, FLOW_KIND_PREDEFINED
from vibeflow.core.flow import ExecutionLockSpec
from vibeflow.targets.python.project.node import PureNode
from vibeflow.targets.python.project.bindings import PythonBindingPlan
from vibeflow.core.planned import (
    PLANNED_BEHAVIOR_PYTHON_STUB,
    PlannedBehavior,
    blocking_planned_behavior,
    effective_planned_behavior,
)
from vibeflow.targets.python.runtime.support.binding_builder import build_python_binding_plan
from vibeflow.targets.python.runtime.support.planned import hash_file, resolve_stub_module_path
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
from vibeflow.targets.python.runtime.options import runtime_options as normalize_runtime_options
from vibeflow.core.config.scope import (
    ConfigBindingError,
    ConfigScope,
    attach_global_config,
    merge_config_scopes,
    nested_node_config_overrides,
    node_invocation_scope,
    normalize_config_scope,
    normalize_node_config_overrides,
    scoped_node_params,
)


@dataclass(frozen=True)
class NodeFrame:
    id: str
    type_used: str
    node: PureNode | None
    requires: tuple[DataRequirement, ...]
    provides: tuple[DataProvider, ...]
    params: Mapping[str, object]
    incoming: tuple[EdgeSpec, ...]
    outgoing: tuple[EdgeSpec, ...]
    flow_kind: str
    is_terminal: bool
    is_nodeset: bool
    status: str = STATUS_IMPLEMENTED
    transfer_incoming: tuple[EdgeSpec, ...] = ()
    transfer_outgoing: tuple[EdgeSpec, ...] = ()
    is_loop: bool = False
    is_io: bool = False
    join_policy: str = ""
    nodeset_type_key: str = ""
    exports: tuple[DataProvider, ...] = ()
    loop_spec: LoopSpec = field(default_factory=LoopSpec)
    io_spec: IoSpec = field(default_factory=IoSpec)
    async_mode: str = ""
    result_key: str = ""
    execution_lock: ExecutionLockSpec | None = None
    subplan: "ExecutionPlan | None" = None
    planned_behavior: PlannedBehavior = field(default_factory=blocking_planned_behavior)
    planned_stub_module: str = ""
    planned_stub_path: str = ""
    planned_stub_hash: str = ""

    @property
    def name(self) -> str:
        return self.id

    @property
    def node_type(self) -> str:
        return self.type_used

    @property
    def nodeset_name(self) -> str:
        return self.nodeset_type_key

    @property
    def is_planned_stub(self) -> bool:
        return self.planned_behavior.kind == PLANNED_BEHAVIOR_PYTHON_STUB

    @property
    def is_planned(self) -> bool:
        return self.status == STATUS_PLANNED

    @property
    def require_types(self) -> tuple[str, ...]:
        return requirement_types(self.requires)

    @property
    def provide_keys(self) -> tuple[str, ...]:
        return provider_keys(self.provides)

    @property
    def export_keys(self) -> tuple[str, ...]:
        return provider_keys(self.exports)


@dataclass(frozen=True)
class ExecutionPlan:
    """Python plan whose binding sidecar shadows, but never drives, execution."""

    graph: GraphConfig
    compiled: CompiledGraph
    frames: Mapping[str, NodeFrame]
    order: tuple[str, ...]
    max_steps: int
    blocks: tuple[CompiledBlock, ...] = ()
    block_by_entry: Mapping[str, CompiledBlock] | None = None
    compiled_blocks: tuple[CompiledBlock, ...] = ()
    compiled_block_by_entry: Mapping[str, CompiledBlock] | None = None
    compiled_node_to_block: Mapping[str, CompiledBlock] | None = None
    python_bindings: PythonBindingPlan = field(default_factory=lambda: PythonBindingPlan(block_id="block:/"))
    contains_global_state: bool = False
    contains_execution_locks: bool = False

    def frame(self, name: str) -> NodeFrame:
        return self.frames[name]

    def block_for(self, name: str) -> CompiledBlock | None:
        return (self.compiled_block_by_entry or self.block_by_entry or {}).get(name)

    @property
    def binding_plan(self) -> PythonBindingPlan:
        return self.python_bindings

    def to_workflow_plan(
        self,
        *,
        workflow_id: str | None = None,
        source_by_type: Mapping[str, object] | None = None,
        pipeline_inputs: object | None = None,
        pipeline_outputs: object | None = None,
    ):
        """Project the Python compatibility plan into the portable IR.

        The import remains lazy so the established Python execution path does
        not acquire a dependency cycle. Non-JSON Python params fail explicitly
        in the portable planner while remaining valid for Python execution.
        """

        from vibeflow.targets.python.runtime.support.portable_adapter import (
            workflow_plan_from_execution_plan,
        )

        return workflow_plan_from_execution_plan(
            self,
            workflow_id=workflow_id,
            source_by_type=source_by_type,
            pipeline_inputs=pipeline_inputs,
            pipeline_outputs=pipeline_outputs,
        )


def build_execution_plan(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    registry: NodeRegistry,
    node_config_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    global_config: Mapping[str, Any] | ConfigScope | None = None,
    runtime_options: object | None = None,
    plugin_registry: object | None = None,
    _check_nodeset_depth: bool = True,
    _path: tuple[str, ...] = (),
) -> ExecutionPlan:
    if _check_nodeset_depth:
        options = normalize_runtime_options(runtime_options)
        violations = nodeset_depth_violations(graph, max_depth=options.nodeset_max_depth)
        if violations:
            violation = violations[0]
            raise PipelineRuntimeError(
                f"nodeset nesting depth {violation.actual_depth} exceeds configured maximum "
                f"{violation.limit}: {' -> '.join(violation.chain)}"
            )
    try:
        overrides = normalize_node_config_overrides(node_config_overrides or {})
    except ConfigBindingError as exc:
        raise PipelineRuntimeError(str(exc)) from exc
    scope = normalize_config_scope(global_config)
    frames = {
        spec.id: _frame_for(
            spec,
            graph=graph,
            compiled=compiled,
            registry=registry,
            overrides=overrides,
            global_scope=scope,
            runtime_options=runtime_options,
            path=_path,
        )
        for spec in graph.nodes
    }
    order = tuple(node.id for node in graph.nodes)
    python_bindings = build_python_binding_plan(
        frames,
        order=order,
        path=_path,
        plugin_registry=plugin_registry,
    )
    plan = ExecutionPlan(
        graph=graph,
        compiled=compiled,
        frames=frames,
        order=order,
        max_steps=graph.max_steps,
        python_bindings=python_bindings,
        contains_global_state=_frames_contain_global_state(frames),
        contains_execution_locks=_frames_contain_execution_locks(frames)
        or graph.execution_lock is not None,
    )
    _validate_execution_lock_scopes(plan)
    blocks = compile_blocks(plan, runtime_options=runtime_options)
    block_by_entry = {block.entry: block for block in blocks}
    node_to_block = {node: block for block in blocks for node in block.nodes}
    return ExecutionPlan(
        graph=graph,
        compiled=compiled,
        frames=frames,
        order=order,
        max_steps=graph.max_steps,
        python_bindings=python_bindings,
        blocks=blocks,
        block_by_entry=block_by_entry,
        compiled_blocks=blocks,
        compiled_block_by_entry=block_by_entry,
        compiled_node_to_block=node_to_block,
        contains_global_state=plan.contains_global_state,
        contains_execution_locks=plan.contains_execution_locks,
    )


def _frame_for(
    spec: NodeSpec,
    *,
    graph: GraphConfig,
    compiled: CompiledGraph,
    registry: NodeRegistry,
    overrides: Mapping[str, Mapping[str, Any]],
    global_scope: ConfigScope,
    runtime_options: object | None,
    path: tuple[str, ...],
) -> NodeFrame:
    schedule_edges = compiled.resolved_schedule_edges
    transfer_edges = compiled.resolved_transfer_edges
    incoming = tuple(edge for edge in schedule_edges if edge.target == spec.id)
    outgoing = tuple(edge for edge in schedule_edges if edge.source == spec.id)
    transfer_incoming = tuple(edge for edge in transfer_edges if edge.target == spec.id)
    transfer_outgoing = tuple(edge for edge in transfer_edges if edge.source == spec.id)
    is_loop = spec.type_used in LOOP_NODE_TYPES
    is_io = spec.type_used == IO_NODE_TYPE
    is_nodeset = spec.type_used in graph.nodesets and not is_loop
    nodeset_type_key = spec.type_used if is_nodeset else ""
    nodeset = (
        graph.nodesets.get(spec.loop.body)
        if is_loop
        else graph.nodesets.get(nodeset_type_key) if is_nodeset else None
    )
    flow_kind = compiled.flow_kinds.get(spec.id, "")
    planned_behavior = effective_planned_behavior(spec, nodeset)
    frame_status = (
        STATUS_PLANNED
        if spec.status == STATUS_PLANNED
        or getattr(nodeset, "status", STATUS_IMPLEMENTED) == STATUS_PLANNED
        else STATUS_IMPLEMENTED
    )
    if planned_behavior.kind == PLANNED_BEHAVIOR_PYTHON_STUB:
        return _planned_stub_frame(
            spec,
            graph=graph,
            incoming=incoming,
            outgoing=outgoing,
            transfer_incoming=transfer_incoming,
            transfer_outgoing=transfer_outgoing,
            flow_kind=flow_kind or (nodeset.flow_kind if nodeset is not None else ""),
            nodeset=nodeset,
            nodeset_type_key=nodeset_type_key,
            behavior=planned_behavior,
            overrides=overrides,
            global_scope=global_scope,
            status=frame_status,
        )
    if is_loop:
        nodeset = graph.nodesets[spec.loop.body]
        nested_overrides = nested_node_config_overrides(spec, overrides)
        subcompiled = _compile_nodeset(nodeset.graph, registry=registry, owner=f"nodeset:{nodeset.type_key}")
        caller_values = {**dict(spec.params), **dict(global_scope.values), **dict(overrides.get(spec.id, {}))}
        caller_scope = node_invocation_scope(caller_values, allow_config_override=spec.allow_config_override)
        child_scope = merge_config_scopes(normalize_config_scope(nodeset.global_config), caller_scope)
        return NodeFrame(
            id=spec.id,
            type_used=spec.type_used,
            node=None,
            requires=spec.requires,
            provides=spec.provides,
            params={},
            incoming=incoming,
            outgoing=outgoing,
            transfer_incoming=transfer_incoming,
            transfer_outgoing=transfer_outgoing,
            flow_kind=flow_kind or FLOW_KIND_PREDEFINED,
            is_terminal=False,
            is_nodeset=False,
            status=frame_status,
            is_loop=True,
            join_policy=spec.join_policy,
            nodeset_type_key=nodeset.type_key,
            exports=nodeset.provides,
            loop_spec=spec.loop,
            async_mode=spec.async_mode,
            result_key=spec.result_key,
            execution_lock=spec.execution_lock,
            subplan=build_execution_plan(
                nodeset.graph,
                subcompiled,
                registry=registry,
                node_config_overrides=nested_overrides,
                global_config=child_scope,
                runtime_options=runtime_options,
                _check_nodeset_depth=False,
                _path=(*path, spec.id),
            ),
        )
    if is_nodeset:
        nodeset = graph.nodesets[nodeset_type_key]
        nested_overrides = nested_node_config_overrides(spec, overrides)
        subcompiled = _compile_nodeset(nodeset.graph, registry=registry, owner=f"nodeset:{nodeset.type_key}")
        caller_values = {**dict(spec.params), **dict(global_scope.values), **dict(overrides.get(spec.id, {}))}
        caller_scope = node_invocation_scope(caller_values, allow_config_override=spec.allow_config_override)
        child_scope = merge_config_scopes(normalize_config_scope(nodeset.global_config), caller_scope)
        return NodeFrame(
            id=spec.id,
            type_used=spec.type_used,
            node=None,
            requires=spec.requires,
            provides=spec.provides,
            params={},
            incoming=incoming,
            outgoing=outgoing,
            transfer_incoming=transfer_incoming,
            transfer_outgoing=transfer_outgoing,
            flow_kind=flow_kind or FLOW_KIND_PREDEFINED,
            is_terminal=False,
            is_nodeset=True,
            status=frame_status,
            join_policy=spec.join_policy,
            nodeset_type_key=nodeset_type_key,
            exports=nodeset.provides,
            async_mode=spec.async_mode,
            result_key=spec.result_key,
            execution_lock=spec.execution_lock,
            subplan=build_execution_plan(
                nodeset.graph,
                subcompiled,
                registry=registry,
                node_config_overrides=nested_overrides,
                global_config=child_scope,
                runtime_options=runtime_options,
                _check_nodeset_depth=False,
                _path=(*path, spec.id),
            ),
        )
    if is_io:
        return NodeFrame(
            id=spec.id,
            type_used=spec.type_used,
            node=None,
            requires=spec.requires,
            provides=spec.provides,
            params={},
            incoming=incoming,
            outgoing=outgoing,
            transfer_incoming=transfer_incoming,
            transfer_outgoing=transfer_outgoing,
            flow_kind=flow_kind,
            is_terminal=True,
            is_nodeset=False,
            status=frame_status,
            is_io=True,
            join_policy=spec.join_policy,
            io_spec=spec.io,
            execution_lock=spec.execution_lock,
        )
    node_cls = registry.get(spec.type_used)
    node = node_cls()
    config_spec = registry.get_config_spec(spec.type_used)
    scoped_params = scoped_node_params(spec.params, global_scope, declared_keys=set(config_spec.schema))
    node_params = registry.merge_config(spec.type_used, {**scoped_params, **dict(overrides.get(spec.id, {}))})
    return NodeFrame(
        id=spec.id,
        type_used=spec.type_used,
        node=node,
        requires=spec.requires,
        provides=spec.provides,
        params=attach_global_config(node_params, global_scope.values),
        incoming=incoming,
        outgoing=outgoing,
        transfer_incoming=transfer_incoming,
        transfer_outgoing=transfer_outgoing,
        flow_kind=flow_kind,
        is_terminal=flow_kind == "terminal",
        is_nodeset=False,
        status=frame_status,
        join_policy=spec.join_policy,
        async_mode=spec.async_mode,
        result_key=spec.result_key,
        execution_lock=spec.execution_lock,
    )


def _planned_stub_frame(
    spec: NodeSpec,
    *,
    graph: GraphConfig,
    incoming: tuple[EdgeSpec, ...],
    outgoing: tuple[EdgeSpec, ...],
    transfer_incoming: tuple[EdgeSpec, ...],
    transfer_outgoing: tuple[EdgeSpec, ...],
    flow_kind: str,
    nodeset: object | None,
    nodeset_type_key: str,
    behavior: PlannedBehavior,
    overrides: Mapping[str, Mapping[str, Any]],
    global_scope: ConfigScope,
    status: str,
) -> NodeFrame:
    params = {**dict(spec.params), **dict(global_scope.values), **dict(overrides.get(spec.id, {}))}
    stub_path = ""
    stub_hash = ""
    try:
        path = resolve_stub_module_path(behavior.stub_module, graph.project_root)
        stub_path = str(path)
        if path.is_file():
            stub_hash = hash_file(path)
    except Exception:
        stub_path = behavior.stub_module
    exports = tuple(getattr(nodeset, "provides", ())) if nodeset is not None else ()
    return NodeFrame(
        id=spec.id,
        type_used=spec.type_used,
        node=None,
        requires=spec.requires,
        provides=spec.provides,
        params=attach_global_config(params, global_scope.values),
        incoming=incoming,
        outgoing=outgoing,
        transfer_incoming=transfer_incoming,
        transfer_outgoing=transfer_outgoing,
        flow_kind=flow_kind,
        is_terminal=flow_kind == "terminal",
        is_nodeset=nodeset is not None,
        status=status,
        join_policy=spec.join_policy,
        nodeset_type_key=nodeset_type_key,
        exports=exports,
        async_mode=spec.async_mode,
        result_key=spec.result_key,
        execution_lock=spec.execution_lock,
        planned_behavior=behavior,
        planned_stub_module=behavior.stub_module,
        planned_stub_path=stub_path,
        planned_stub_hash=stub_hash,
    )


def _frames_contain_global_state(frames: Mapping[str, NodeFrame]) -> bool:
    return any(
        not frame.is_planned
        and (
            frame.flow_kind == FLOW_KIND_GLOBAL_STATE
            or (
                frame.subplan is not None
                and frame.subplan.contains_global_state
            )
        )
        for frame in frames.values()
    )


def _frames_contain_execution_locks(frames: Mapping[str, NodeFrame]) -> bool:
    return any(
        not frame.is_planned
        and (
            frame.execution_lock is not None
            or (
                frame.subplan is not None
                and frame.subplan.contains_execution_locks
            )
        )
        for frame in frames.values()
    )


def _validate_execution_lock_scopes(
    plan: ExecutionPlan,
    *,
    inherited_key: str = "",
    protected: bool = False,
) -> None:
    root_key = plan.graph.execution_lock.key if plan.graph.execution_lock else ""
    active_key = _nested_lock_key(inherited_key, root_key, subject="pipeline")
    root_protected = protected or bool(root_key) or plan.contains_global_state
    for frame in plan.frames.values():
        frame_key = (
            frame.execution_lock.key
            if frame.execution_lock is not None and not frame.is_planned
            else ""
        )
        nested_key = _nested_lock_key(
            active_key,
            frame_key,
            subject=f"node '{frame.name}'",
        )
        frame_protected = root_protected or bool(frame_key)
        if frame_protected and frame.async_mode == "detached":
            raise PipelineRuntimeError(
                f"protected execution scope cannot contain detached node '{frame.name}'"
            )
        if (
            frame_protected
            and frame.async_mode == "result_key"
            and not _frame_has_static_result_consumer(plan, frame)
        ):
            raise PipelineRuntimeError(
                f"protected execution scope cannot contain unjoined result_key node '{frame.name}'"
            )
        if frame.subplan is not None:
            _validate_execution_lock_scopes(
                frame.subplan,
                inherited_key=nested_key,
                protected=frame_protected,
            )


def _frame_has_static_result_consumer(
    plan: ExecutionPlan,
    source: NodeFrame,
) -> bool:
    provider = next(
        (item for item in source.provides if item.key == source.result_key),
        None,
    )
    if provider is None:
        return False
    pending = [
        edge.target for edge in source.outgoing if not edge.when
    ]
    seen: set[str] = set()
    while pending:
        node_name = pending.pop(0)
        if node_name in seen:
            continue
        seen.add(node_name)
        candidate = plan.frames.get(node_name)
        if candidate is None:
            continue
        if any(item.type == provider.type for item in candidate.requires):
            return True
        pending.extend(
            edge.target
            for edge in candidate.outgoing
            if not edge.when and edge.target not in seen
        )
    return False


def _nested_lock_key(current: str, requested: str, *, subject: str) -> str:
    if not requested:
        return current
    if current and current != requested:
        raise PipelineRuntimeError(
            f"{subject} cannot acquire execution lock '{requested}' while "
            f"'{current}' is held"
        )
    return requested


def _compile_nodeset(graph: GraphConfig, *, registry: NodeRegistry, owner: str) -> CompiledGraph:
    from vibeflow.targets.python.project.compiler import GraphCompiler

    return GraphCompiler().compile(graph, registry=registry, owner=owner)


__all__ = ["CompiledBlock", "ExecutionPlan", "NodeFrame", "build_execution_plan"]
