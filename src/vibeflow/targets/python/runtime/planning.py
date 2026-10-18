from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vibeflow.targets.python.runtime.block_compiler import CompiledBlock
from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.contracts import DataProvider, DataRequirement, provider_keys, requirement_types
from vibeflow.core.flow import EdgeSpec, GraphConfig, IoSpec, LoopSpec, ExecutionLockSpec, STATUS_IMPLEMENTED, STATUS_PLANNED
from vibeflow.targets.python.nodetypes.protocols import PureNode
from vibeflow.targets.python.project.bindings import PythonBindingPlan
from vibeflow.core.planned import PLANNED_BEHAVIOR_PYTHON_STUB, PlannedBehavior, blocking_planned_behavior
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.core.config.scope import ConfigScope


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
    effect_scope: str = "unconstrained"
    transfer_incoming: tuple[EdgeSpec, ...] = ()
    transfer_outgoing: tuple[EdgeSpec, ...] = ()
    is_loop: bool = False
    is_io: bool = False
    join_policy: str = ""
    nodeset_type_key: str = ""
    exports: tuple[DataProvider, ...] = ()
    loop_spec: LoopSpec = field(default_factory=LoopSpec)
    io_spec: IoSpec = field(default_factory=IoSpec)
    execution_lock: ExecutionLockSpec | None = None
    subplan: "ExecutionPlan | None" = None
    accepts_context: bool = False
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
    workflow_plan: object | None = None
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
        """Expose the prepared common plan with native call parameters.

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
    _contracts_resolved: bool = False,
    _path: tuple[str, ...] = (),
) -> ExecutionPlan:
    from vibeflow.targets.python.runtime.preparation import prepare_python_workflow, bind_python_workflow
    if not _contracts_resolved:
        from vibeflow.targets.python.project.compiler import GraphCompiler
        compilation = GraphCompiler().compile_with_findings(graph, registry=registry, plugin_registry=plugin_registry)
        graph, compiled = compilation.workflow.graph, compilation.compiled_graph
    if getattr(registry, "_loaders", {}):
        from vibeflow.targets.python.project.sources import collect_workflow_source_context
        collect_workflow_source_context(registry, graph)
    prepared = prepare_python_workflow(graph, compiled, registry=registry,
        global_config=global_config, node_config_overrides=node_config_overrides)
    return bind_python_workflow(prepared, registry=registry, runtime_options=runtime_options, plugin_registry=plugin_registry)


__all__ = ["CompiledBlock", "ExecutionPlan", "NodeFrame", "build_execution_plan"]
