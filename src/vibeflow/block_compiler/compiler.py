"""Compile validated Core workflows into the canonical Block Compiler IR."""

from __future__ import annotations

from dataclasses import replace
from pathlib import PurePath
from typing import Mapping, Sequence

from vibeflow.block_compiler.model import (
    WORKFLOW_ABI_VERSION,
    BlockPlan,
    ConditionPlan,
    DataProviderPlan,
    DataRequirementPlan,
    ExecutionLockPlan,
    LoopCarryPlan,
    LoopCollectPlan,
    LoopOutputPlan,
    LoopPlan,
    NodeCallPlan,
    PipelineInputSpec,
    PipelineOutputSpec,
    PortablePlanError,
    RoutePlan,
    SourceRef,
    TaskPlan,
    WorkflowPlan,
    freeze_json_object,
)
from vibeflow.core.compiler import CompiledGraph, GraphCompiler as CoreGraphCompiler
from vibeflow.core.flow import (
    IO_NODE_TYPE,
    LOOP_NODE_TYPES,
    GraphConfig,
    LoopSpec,
    NodeSpec,
    STATUS_PLANNED,
)
from vibeflow.core.constants import (
    EFFECT_SCOPE_GLOBAL_STATE,
    EFFECT_SCOPE_NONE,
    FLOW_KIND_GLOBAL_STATE,
)
from vibeflow.core.models import (
    ImplementationFacts,
    TargetFeatureSet,
    ValidatedWorkflow,
)
from vibeflow.core.planned import effective_planned_behavior


def normalize_condition(expression: str) -> ConditionPlan | None:
    """Normalize exactly the condition grammar accepted by GraphConfig."""

    text = str(expression).strip()
    if not text:
        return None
    operators = [operator for operator in ("==", "!=") if operator in text]
    if len(operators) != 1:
        raise PortablePlanError(f"condition must use exactly one == or != operator: {expression}")
    operator = operators[0]
    key, literal_text = (part.strip() for part in text.split(operator, 1))
    if not key or not literal_text:
        raise PortablePlanError(f"condition must compare a key to a literal: {expression}")
    if literal_text in {"true", "false"}:
        literal: bool | str = literal_text == "true"
    elif (
        len(literal_text) >= 2
        and literal_text[0] == literal_text[-1]
        and literal_text[0] in {"'", '"'}
    ):
        literal = literal_text[1:-1]
    else:
        raise PortablePlanError(f"condition literal must be true, false, or a quoted string: {expression}")
    return ConditionPlan(key=key, operator=operator, literal=literal)


def compile_workflow(
    workflow: ValidatedWorkflow,
    implementation_facts: ImplementationFacts,
) -> WorkflowPlan:
    """Compile a validated workflow using static Target implementation facts."""

    if not isinstance(workflow, ValidatedWorkflow):
        raise TypeError("workflow must be a ValidatedWorkflow")
    if not isinstance(implementation_facts, ImplementationFacts):
        raise TypeError("implementation_facts must be ImplementationFacts")
    graph = workflow.graph
    compiled = CoreGraphCompiler().compile(
        graph,
        implementation_facts=implementation_facts,
        target_features=workflow.target_features,
        known_nodesets=set(graph.nodesets),
    )
    return compile_graph_plan(
        graph,
        compiled,
        source_by_type=_sources_from_facts(implementation_facts),
        implementation_facts=implementation_facts,
        target_features=workflow.target_features,
        compile_nested=True,
    )


def compile_graph_plan(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    workflow_id: str | None = None,
    source_by_type: Mapping[str, SourceRef] | None = None,
    compiled_by_path: Mapping[tuple[str, ...], CompiledGraph] | None = None,
    params_by_path: Mapping[tuple[str, ...], Mapping[str, object]] | None = None,
    pipeline_inputs: Sequence[PipelineInputSpec] | None = None,
    pipeline_outputs: Sequence[PipelineOutputSpec] | None = None,
    implementation_facts: ImplementationFacts | None = None,
    target_features: TargetFeatureSet | None = None,
    compile_nested: bool = False,
) -> WorkflowPlan:
    """Assemble canonical IR from a Core graph compilation."""

    resolved_inputs = _root_inputs(graph, pipeline_inputs)
    resolved_outputs = _root_outputs(graph, pipeline_outputs)
    state = _PlannerState(
        source_by_type,
        compiled_by_path=compiled_by_path,
        params_by_path=params_by_path,
        implementation_facts=implementation_facts,
        target_features=target_features,
        compile_nested=compile_nested,
    )
    root_id = _block_id(())
    state.add_graph_block(
        graph,
        compiled,
        path=(),
        kind="workflow",
        loop=None,
        active_nodesets=(),
        inherited_lock_key="",
    )
    root_block = state.blocks[0]
    _validate_protected_async_plan(tuple(state.blocks))
    return WorkflowPlan(
        abi_version=WORKFLOW_ABI_VERSION,
        workflow_id=_workflow_id(graph, workflow_id),
        source=_graph_source(graph, _workflow_id(graph, workflow_id)),
        entry_block=root_id,
        inputs=resolved_inputs,
        outputs=resolved_outputs,
        blocks=tuple(state.blocks),
        max_steps=graph.max_steps,
        entry_mode=graph.entry_mode,
        execution_lock=_execution_lock_plan(
            graph.execution_lock,
            scope="root",
        ),
        contains_global_state=root_block.contains_global_state,
    )


def legacy_workflow_spec_payload(plan: WorkflowPlan) -> dict[str, object]:
    """Return the deterministic payload consumed by the legacy JS adapter."""

    if not isinstance(plan, WorkflowPlan):
        raise TypeError("plan must be a WorkflowPlan")
    return plan.to_dict()


class _PlannerState:
    def __init__(
        self,
        source_by_type: Mapping[str, SourceRef] | None,
        *,
        compiled_by_path: Mapping[tuple[str, ...], CompiledGraph] | None = None,
        params_by_path: Mapping[tuple[str, ...], Mapping[str, object]] | None = None,
        implementation_facts: ImplementationFacts | None = None,
        target_features: TargetFeatureSet | None = None,
        compile_nested: bool = False,
    ) -> None:
        self.implementation_facts = implementation_facts or ImplementationFacts()
        self.source_by_type = _sources_from_facts(self.implementation_facts)
        self.source_by_type.update(_normalize_source_map(source_by_type))
        self.compiled_by_path = dict(compiled_by_path or {})
        self.params_by_path = {
            tuple(path): dict(params)
            for path, params in (params_by_path or {}).items()
        }
        self.target_features = target_features or TargetFeatureSet()
        self.compile_nested = compile_nested
        self.blocks: list[BlockPlan] = []

    def add_graph_block(
        self,
        graph: GraphConfig,
        compiled: CompiledGraph,
        *,
        path: tuple[str, ...],
        kind: str,
        loop: LoopPlan | None,
        active_nodesets: tuple[str, ...],
        inherited_lock_key: str,
    ) -> bool:
        block_scope = "root" if not path else "block"
        block_lock = _execution_lock_plan(
            graph.execution_lock,
            scope=block_scope,
        )
        active_lock_key = _nested_lock_key(
            inherited_lock_key,
            block_lock.key if block_lock is not None else "",
            subject=f"block {_block_id(path)}",
        )
        children: list[
            tuple[
                int,
                GraphConfig,
                CompiledGraph,
                tuple[str, ...],
                str,
                LoopPlan | None,
                tuple[str, ...],
                str,
            ]
        ] = []
        nodes: list[NodeCallPlan] = []
        for spec in graph.nodes:
            is_loop = spec.type_used in LOOP_NODE_TYPES
            is_nodeset = spec.type_used in graph.nodesets and not is_loop
            nodeset = graph.nodesets.get(spec.loop.body if is_loop else spec.type_used) if (is_loop or is_nodeset) else None
            behavior = effective_planned_behavior(spec, nodeset)
            planned_invocation = (
                spec.status == STATUS_PLANNED
                or getattr(nodeset, "status", "implemented") == STATUS_PLANNED
            )
            # A planned nodeset is an architecture/review declaration, not an
            # executable subtree. Its children must not influence Target
            # feature gates or root execution-domain facts.
            has_child = (
                nodeset is not None
                and not planned_invocation
                and behavior.kind != "python_stub"
            )
            child_path = (*path, spec.id)
            child_block = _block_id(child_path) if has_child else ""
            node_index = len(nodes)
            node_plan = self._graph_node(
                spec,
                compiled=compiled,
                nodeset=nodeset,
                is_loop=is_loop,
                is_nodeset=is_nodeset,
                child_block=child_block,
                planned_behavior=behavior.kind,
                call_path=child_path,
            )
            node_lock_key = (
                node_plan.execution_lock.key
                if (
                    node_plan.execution_lock is not None
                    and node_plan.status != STATUS_PLANNED
                )
                else ""
            )
            child_lock_key = _nested_lock_key(
                active_lock_key,
                node_lock_key,
                subject=f"node {'.'.join(child_path)}",
            )
            nodes.append(node_plan)
            if not has_child or nodeset is None:
                continue
            if nodeset.type_key in active_nodesets:
                chain = " -> ".join((*active_nodesets, nodeset.type_key))
                raise PortablePlanError(f"recursive nodeset reference cannot be represented as finite blocks: {chain}")
            child_compiled = self.compiled_by_path.get(child_path)
            if child_compiled is None and self.compile_nested:
                child_compiled = CoreGraphCompiler().compile(
                    nodeset.graph,
                    implementation_facts=self.implementation_facts,
                    target_features=self.target_features,
                    known_nodesets=set(nodeset.graph.nodesets),
                    owner=f"block {_block_id(child_path)}",
                )
            if child_compiled is None:
                raise PortablePlanError(
                    f"nested block {_block_id(child_path)} requires an execution plan or compiled_by_path entry"
                )
            child_kind = "loop" if is_loop else "nodeset"
            child_loop = _loop_plan(spec.loop) if is_loop else None
            children.append(
                (
                    node_index,
                    nodeset.graph,
                    child_compiled,
                    child_path,
                    child_kind,
                    child_loop,
                    (*active_nodesets, nodeset.type_key),
                    child_lock_key,
                )
            )
        block_index = len(self.blocks)
        self.blocks.append(
            _block(
                graph,
                compiled,
                path=path,
                kind=kind,
                loop=loop,
                nodes=tuple(nodes),
                execution_lock=block_lock,
            )
        )
        for (
            node_index,
            child_graph,
            child_compiled,
            child_path,
            child_kind,
            child_loop,
            child_active,
            child_lock_key,
        ) in children:
            child_contains_global_state = self.add_graph_block(
                child_graph,
                child_compiled,
                path=child_path,
                kind=child_kind,
                loop=child_loop,
                active_nodesets=child_active,
                inherited_lock_key=child_lock_key,
            )
            if child_contains_global_state:
                nodes[node_index] = replace(
                    nodes[node_index],
                    contains_global_state=True,
                )
        contains_global_state = any(
            node.contains_global_state for node in nodes
        )
        self.blocks[block_index] = _block(
            graph,
            compiled,
            path=path,
            kind=kind,
            loop=loop,
            nodes=tuple(nodes),
            execution_lock=block_lock,
            contains_global_state=contains_global_state,
        )
        return contains_global_state

    def _graph_node(
        self,
        spec: NodeSpec,
        *,
        compiled: CompiledGraph,
        nodeset: object | None,
        is_loop: bool,
        is_nodeset: bool,
        child_block: str,
        planned_behavior: str,
        call_path: tuple[str, ...],
    ) -> NodeCallPlan:
        exports = tuple(getattr(nodeset, "provides", ())) if nodeset is not None else ()
        nodeset_type_key = str(getattr(nodeset, "type_key", ""))
        flow_kind = compiled.flow_kinds.get(spec.id, spec.flow_kind)
        status = (
            STATUS_PLANNED
            if spec.status == STATUS_PLANNED
            or getattr(nodeset, "status", "implemented") == STATUS_PLANNED
            else spec.status
        )
        completion, schedule, executor = self._execution_semantics(spec)
        effect_scope = compiled.effect_scopes.get(
            spec.id,
            (
                EFFECT_SCOPE_GLOBAL_STATE
                if flow_kind == FLOW_KIND_GLOBAL_STATE
                else EFFECT_SCOPE_NONE
            ),
        )
        return NodeCallPlan(
            id=spec.id,
            type_used=spec.type_used,
            implementation=self._source(spec.type_used),
            requires=_requirements(spec.requires),
            provides=_providers(spec.provides),
            params=freeze_json_object(
                self.params_by_path.get(call_path, spec.params),
                path=f"node[{'.'.join(call_path)}].params",
            ),
            config_overrides=freeze_json_object(
                spec.node_config_overrides,
                path=f"node[{spec.id}].node_config_overrides",
            ),
            flow_kind=flow_kind,
            join_policy=spec.join_policy,
            status=status,
            planned_behavior=planned_behavior,
            async_mode=spec.async_mode,
            result_key=spec.result_key,
            is_terminal=(
                flow_kind == "terminal"
                or spec.type_used == IO_NODE_TYPE
            ),
            is_nodeset=is_nodeset,
            is_loop=is_loop,
            nodeset_type_key=nodeset_type_key,
            child_block=child_block,
            exports=_providers(exports),
            allow_config_override=spec.allow_config_override,
            display_name=spec.metadata.display_name,
            description=spec.metadata.description,
            completion=completion,
            schedule=schedule,
            executor=executor,
            io_operation=spec.io.operation,
            io_port=spec.io.port if spec.io.operation else "",
            effect_scope=effect_scope,
            runtime_dispatch=compiled.runtime_dispatches.get(spec.id),
            execution_lock=_execution_lock_plan(
                spec.execution_lock,
                scope="block" if is_nodeset or is_loop else "node",
            ),
            contains_global_state=(
                status != STATUS_PLANNED
                and flow_kind == FLOW_KIND_GLOBAL_STATE
            ),
        )

    def _source(self, type_used: str) -> SourceRef:
        return self.source_by_type.get(type_used, SourceRef(kind="catalog", ref=type_used))

    def _execution_semantics(self, spec: NodeSpec) -> tuple[str, str, str]:
        if spec.type_used == IO_NODE_TYPE:
            if spec.io.operation == "receive":
                return ("suspend", "inline", "event_loop")
            return ("immediate", "inline", "current")
        fact = self.implementation_facts.get(spec.type_used)
        completion = fact.completion if fact is not None else "immediate"
        if spec.async_mode:
            schedule = _schedule(spec.async_mode)
            executor = (
                fact.executor
                if fact is not None and fact.executor != "current"
                else _executor(spec.async_mode)
            )
            return (completion, schedule, executor)
        if fact is None:
            return (completion, "inline", "current")
        return (completion, fact.schedule, fact.executor)


def _block(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    path: tuple[str, ...],
    kind: str,
    loop: LoopPlan | None,
    nodes: tuple[NodeCallPlan, ...],
    execution_lock: ExecutionLockPlan | None = None,
    contains_global_state: bool = False,
) -> BlockPlan:
    routes = _routes(compiled)
    incoming = {route.target for route in routes if route.schedule}
    outgoing = {route.source for route in routes if route.schedule}
    terminal_by_id = {node.id: node.is_terminal for node in nodes}
    entries = tuple(node_id for node_id in compiled.order if node_id not in incoming and terminal_by_id.get(node_id, False))
    exits = tuple(node_id for node_id in compiled.order if node_id not in outgoing and terminal_by_id.get(node_id, False))
    return BlockPlan(
        id=_block_id(path),
        kind=kind,
        path=path,
        source=_graph_source(graph, _block_id(path)),
        inputs=_legacy_inputs(graph),
        outputs=_legacy_outputs(graph),
        nodes=nodes,
        routes=routes,
        order=compiled.order,
        entries=entries,
        exits=exits,
        max_steps=graph.max_steps,
        tasks=tuple(
            TaskPlan(
                id=f"{_block_id(path)}:task:{node.id}",
                node_id=node.id,
                schedule=node.schedule,
                executor=node.executor,
                result_key=node.result_key,
            )
            for node in nodes
            if node.schedule != "inline"
        ),
        loop=loop,
        execution_lock=(
            execution_lock
            if execution_lock is not None
            else _execution_lock_plan(
                graph.execution_lock,
                scope="root" if not path else "block",
            )
        ),
        contains_global_state=contains_global_state,
    )


def _routes(compiled: CompiledGraph) -> tuple[RoutePlan, ...]:
    schedule_edges = compiled.resolved_schedule_edges
    transfer_edges = compiled.resolved_transfer_edges
    schedule_pairs = {edge.pair for edge in schedule_edges}
    transfer_pairs = {edge.pair for edge in transfer_edges}
    explicit_pairs = {edge.pair for edge in compiled.explicit_edges}
    mainline_pairs = {edge.pair for edge in compiled.mainline_edges}
    bypass_pairs = {edge.pair for edge in compiled.data_bypass_edges}
    async_pairs = {edge.pair for edge in compiled.async_edges}
    return tuple(
        RoutePlan(
            source=edge.source,
            target=edge.target,
            condition=normalize_condition(edge.when),
            schedule=edge.pair in schedule_pairs,
            transfer=edge.pair in transfer_pairs,
            explicit=edge.pair in explicit_pairs,
            mainline=edge.pair in mainline_pairs,
            data_bypass=edge.pair in bypass_pairs,
            asynchronous=edge.pair in async_pairs,
        )
        for edge in compiled.effective_edges
    )


def _loop_plan(spec: LoopSpec) -> LoopPlan:
    stop_when = (
        ConditionPlan(key=spec.stop_when.source, operator="==", literal=spec.stop_when.equals)
        if spec.stop_when.source
        else None
    )
    return LoopPlan(
        body_type_key=spec.body,
        max_iterations=spec.max_iterations,
        stop_after=spec.stop_after or None,
        stop_when=stop_when,
        carry=tuple(LoopCarryPlan(item.source, item.target, item.update) for item in spec.carry),
        collect=tuple(LoopCollectPlan(item.source, item.target, item.mode) for item in spec.collect),
        outputs=tuple(LoopOutputPlan(item.source, item.target) for item in spec.outputs),
    )


def _schedule(async_mode: str) -> str:
    if async_mode == "result_key":
        return "deferred"
    if async_mode == "detached":
        return "detached"
    return "inline"


def _executor(async_mode: str) -> str:
    return "thread" if async_mode else "current"


def _execution_lock_plan(
    spec: object | None,
    *,
    scope: str,
) -> ExecutionLockPlan | None:
    if spec is None:
        return None
    return ExecutionLockPlan(
        key=str(getattr(spec, "key", "")),
        scope=scope,
    )


def _nested_lock_key(parent: str, child: str, *, subject: str) -> str:
    if parent and child and parent != child:
        raise PortablePlanError(
            f"{subject} nests execution_lock key '{child}' inside "
            f"incompatible key '{parent}'; nested locks must reuse one key"
        )
    return child or parent


def _validate_protected_async_plan(
    blocks: tuple[BlockPlan, ...],
) -> None:
    if not blocks:
        return
    root_protected = blocks[0].execution_lock is not None
    blocks_by_path = {block.path: block for block in blocks}
    for block in blocks:
        block_protected = root_protected or _block_has_protected_ancestor(
            block,
            blocks_by_path=blocks_by_path,
        )
        for node in block.nodes:
            if node.status == STATUS_PLANNED:
                continue
            protected = block_protected or node.execution_lock is not None
            if not protected or not node.async_mode:
                continue
            if node.async_mode == "detached":
                raise PortablePlanError(
                    f"protected block '{block.id}' cannot detach node "
                    f"'{node.id}' while execution_lock is active"
                )
            if (
                node.async_mode == "result_key"
                and not _plan_has_static_result_consumer(block, node)
            ):
                raise PortablePlanError(
                    f"protected block '{block.id}' async result_key node "
                    f"'{node.id}' has no statically provable scheduled "
                    "consumer path"
                )


def _block_has_protected_ancestor(
    block: BlockPlan,
    *,
    blocks_by_path: Mapping[tuple[str, ...], BlockPlan],
) -> bool:
    if block.execution_lock is not None:
        return True
    for length in range(1, len(block.path) + 1):
        parent_path = block.path[: length - 1]
        parent = blocks_by_path.get(parent_path)
        if parent is None:
            continue
        if parent.execution_lock is not None:
            return True
        try:
            invocation = parent.node(block.path[length - 1])
        except KeyError:
            continue
        if invocation.execution_lock is not None:
            return True
    return False


def _plan_has_static_result_consumer(
    block: BlockPlan,
    source: NodeCallPlan,
) -> bool:
    result_provider = next(
        (item for item in source.provides if item.key == source.result_key),
        None,
    )
    if result_provider is None:
        return False
    adjacency: dict[str, set[str]] = {}
    for route in block.routes:
        if route.schedule and route.condition is None:
            adjacency.setdefault(route.source, set()).add(route.target)
    nodes_by_id = {node.id: node for node in block.nodes}
    pending = list(sorted(adjacency.get(source.id, ())))
    seen: set[str] = set()
    while pending:
        node_id = pending.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        candidate = nodes_by_id.get(node_id)
        if candidate is not None and any(
            requirement.type == result_provider.type
            for requirement in candidate.requires
        ):
            return True
        pending.extend(
            target
            for target in sorted(adjacency.get(node_id, ()))
            if target not in seen
        )
    return False


def _sources_from_facts(
    facts: ImplementationFacts,
) -> dict[str, SourceRef]:
    return {
        fact.type_key: SourceRef(
            kind=fact.source_kind or "catalog",
            ref=fact.source_ref or fact.type_key,
            export=fact.source_export,
        )
        for fact in facts.nodes
    }


def _normalize_source_map(
    values: Mapping[str, SourceRef] | None,
) -> dict[str, SourceRef]:
    sources: dict[str, SourceRef] = {}
    for type_key, source in (values or {}).items():
        if not isinstance(type_key, str) or not type_key.strip():
            raise PortablePlanError(
                "implementation source keys must be non-empty strings"
            )
        if not isinstance(source, SourceRef):
            raise PortablePlanError(
                f"implementation source for '{type_key}' must be a SourceRef"
            )
        sources[type_key] = source
    return sources


def _providers(items: Sequence[object]) -> tuple[DataProviderPlan, ...]:
    return tuple(
        DataProviderPlan(
            key=str(getattr(item, "key", "")),
            type=str(getattr(item, "type", "")),
            display_name=str(getattr(item, "display_name", "")),
        )
        for item in items
    )


def _requirements(items: Sequence[object]) -> tuple[DataRequirementPlan, ...]:
    return tuple(
        DataRequirementPlan(
            type=str(getattr(item, "type", "")),
            cardinality=str(getattr(item, "cardinality", "")),
            display_name=str(getattr(item, "display_name", "")),
        )
        for item in items
    )


def _legacy_inputs(graph: GraphConfig) -> tuple[PipelineInputSpec, ...]:
    return tuple(
        PipelineInputSpec(
            key=item.key,
            type=item.type,
            required=getattr(item, "required", None),
            display_name=item.display_name,
        )
        for item in graph.inputs
    )


def _legacy_outputs(graph: GraphConfig) -> tuple[PipelineOutputSpec, ...]:
    return tuple(
        PipelineOutputSpec(
            type=item.type,
            cardinality=item.cardinality,
            as_key=str(getattr(item, "public_name", "") or getattr(item, "alias", "") or item.type),
            display_name=item.display_name,
        )
        for item in graph.outputs
    )


def _root_inputs(
    graph: GraphConfig,
    supplied: Sequence[PipelineInputSpec] | None,
) -> tuple[PipelineInputSpec, ...]:
    values = tuple(supplied) if supplied is not None else _legacy_inputs(graph)
    expected = tuple((item.key, item.type) for item in graph.inputs)
    actual = tuple((item.key, item.type) for item in values)
    if actual != expected:
        raise PortablePlanError("portable pipeline inputs must match GraphConfig input key/type order")
    return values


def _root_outputs(
    graph: GraphConfig,
    supplied: Sequence[PipelineOutputSpec] | None,
) -> tuple[PipelineOutputSpec, ...]:
    values = tuple(supplied) if supplied is not None else _legacy_outputs(graph)
    expected = tuple((item.type, item.cardinality) for item in graph.outputs)
    actual = tuple((item.type, item.cardinality) for item in values)
    if actual != expected:
        raise PortablePlanError("portable pipeline outputs must match GraphConfig output type/cardinality order")
    return values


def _workflow_id(graph: GraphConfig, supplied: str | None) -> str:
    if supplied is not None and supplied.strip():
        return supplied.strip()
    if graph.source_path:
        return PurePath(graph.source_path).stem
    return graph.root_id or "workflow"


def _graph_source(graph: GraphConfig, fallback: str) -> SourceRef:
    if graph.source_path:
        return SourceRef(kind="config", ref=graph.source_path)
    if graph.root_path:
        return SourceRef(kind="config_root", ref=graph.root_path)
    return SourceRef(kind="graph", ref=fallback)


def _block_id(path: tuple[str, ...]) -> str:
    if not path:
        return "block:/"
    escaped = (part.replace("~", "~0").replace("/", "~1") for part in path)
    return "block:/" + "/".join(escaped)
