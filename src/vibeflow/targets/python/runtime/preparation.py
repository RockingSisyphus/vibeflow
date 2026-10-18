"""Prepare a portable workflow, then bind it to Python runtime objects."""
from __future__ import annotations

from dataclasses import dataclass, replace
from inspect import signature
from typing import Mapping

from vibeflow.block_compiler import WorkflowPlan, compile_graph_plan
from vibeflow.block_compiler.compiler import _block_id
from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.config.scope import normalize_config_scope, scoped_node_params
from vibeflow.core.flow import GraphConfig, IO_NODE_TYPE, LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.core.models import TargetFeatureSet
from vibeflow.core.planned import effective_planned_behavior
from vibeflow.core.graph_calls import graph_call_subjects
from vibeflow.core.config.concurrency import business_config, scheduling_config
from vibeflow.targets.python.project.compiler import GraphCompiler


@dataclass(frozen=True)
class PreparedPythonWorkflow:
    """Immutable structure plus native binding inputs; never live Node instances."""
    workflow: WorkflowPlan
    graphs: Mapping[str, GraphConfig]
    compiled: Mapping[str, CompiledGraph]
    globals: Mapping[str, Mapping[str, object]]
    overrides: Mapping[str, Mapping[str, Mapping[str, object]]]


def prepare_python_workflow(graph, compiled, *, registry, global_config=None, node_config_overrides=None):
    from vibeflow.targets.python.project.compiler import _adapt_implementation_facts
    from vibeflow.core.config.scope import normalize_node_config_overrides
    from vibeflow.targets.python.runtime.errors import PipelineRuntimeError

    try:
        overrides = normalize_node_config_overrides(node_config_overrides or {})
    except ValueError as error:
        raise PipelineRuntimeError(str(error)) from error
    facts = _adapt_implementation_facts(graph, source=registry, nodesets=set(graph.nodesets))
    graphs, compilations, globals_by_block, parameters, overrides_by_block = {}, {}, {}, {}, {}
    subjects = graph_call_subjects(graph, global_config=global_config, node_config_overrides=overrides)
    for subject in subjects:
        if subject.declaration_only:
            continue
        path = subject.call_path
        artifact = None if not path else GraphCompiler().compile_with_findings(
            subject.graph, registry=registry, owner=subject.owner, call_path=path)
        current = artifact.workflow.graph if artifact is not None else graph
        current_compiled = artifact.compiled_graph if artifact is not None else compiled
        key = _block_id(path)
        graphs[key], compilations[path] = current, current_compiled
        scope = normalize_config_scope(subject.global_config)
        globals_by_block[key] = scope.values
        local_overrides = dict(subject.overrides)
        overrides_by_block[key] = local_overrides
        for spec in current.nodes:
            nodeset = current.nodesets.get(spec.loop.body if spec.type_used in LOOP_NODE_TYPES else spec.type_used)
            if effective_planned_behavior(spec, nodeset).kind == 'python_stub':
                parameters[(*path, spec.id)] = {**spec.params, **local_overrides.get(spec.id, {})}
                continue
            composite = spec.type_used in current.nodesets or spec.type_used in LOOP_NODE_TYPES
            if composite or spec.type_used == IO_NODE_TYPE:
                parameters[(*path, spec.id)] = scheduling_config(
                    {**spec.params, **local_overrides.get(spec.id, {})}
                )
                continue
            if spec.status == STATUS_PLANNED:
                parameters[(*path, spec.id)] = {**spec.params, **local_overrides.get(spec.id, {})}
                continue
            config_spec = registry.get_config_spec(spec.type_used)
            scoped = scoped_node_params(spec.params, scope, declared_keys=set(config_spec.schema))
            parameters[(*path, spec.id)] = registry.merge_config(spec.type_used,
                {**scoped, **local_overrides.get(spec.id, {})})
    try:
        workflow = compile_graph_plan(graph, compiled, implementation_facts=facts,
            compiled_by_path=compilations, params_by_path=parameters,
            target_features=TargetFeatureSet(target='python', features=frozenset({'execution_locks', 'global_state'})),
        )
    except ValueError as exc:
        raise PipelineRuntimeError(str(exc)) from exc
    return PreparedPythonWorkflow(workflow, graphs,
        {_block_id(path): value for path, value in compilations.items()}, globals_by_block, overrides_by_block)


def bind_python_workflow(prepared, *, registry, runtime_options=None, plugin_registry=None, block_loader=None, instantiate=True, source_hash_for_path=None):
    """Instantiate the existing runtime frames from the common plan.

    ``block_loader`` binds saved generated functions during AOT loading; it
    never recompiles or inspects the source workflow.
    """
    from vibeflow.targets.python.runtime.planning import ExecutionPlan, NodeFrame
    from vibeflow.targets.python.runtime.block_compiler import compile_blocks
    from vibeflow.targets.python.runtime.support.binding_builder import build_python_binding_plan
    from vibeflow.targets.python.runtime.support.planned import resolve_stub_module_path, hash_file
    from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
    from vibeflow.core.config.scope import attach_global_config

    def bind(block_id):
        block = prepared.workflow.block(block_id)
        graph = prepared.graphs[block_id]
        specs = {node.id: node for node in graph.nodes}
        compiled = prepared.compiled[block_id]
        frames = {}
        for call in block.nodes:
            spec = specs[call.id]
            nodeset = graph.nodesets.get(call.nodeset_type_key)
            behavior = effective_planned_behavior(spec, nodeset)
            implementation = None
            accepts_context = False
            if instantiate and not (call.is_nodeset or call.is_loop or spec.type_used == IO_NODE_TYPE or behavior.kind == 'python_stub'):
                implementation_type = registry.get(call.type_used)
                implementation = implementation_type()
                accepts_context = len(signature(implementation.run_pure).parameters) == 3
            stub_path, stub_hash = '', ''
            if behavior.kind == 'python_stub':
                path = resolve_stub_module_path(behavior.stub_module, graph.project_root)
                stub_path = str(path)
                # Source preparation records this advisory metadata once. AOT
                # binding uses its relocated file without hashing at startup.
                if source_hash_for_path is not None:
                    stub_hash = source_hash_for_path(path)
                elif block_loader is None and path.is_file():
                    stub_hash = hash_file(path)
            params = call.params.to_value()
            if behavior.kind == 'python_stub':
                params = business_config({**spec.params, **prepared.globals[block_id], **prepared.overrides[block_id].get(call.id,{})})
            bound_params = params if (call.is_nodeset or call.is_loop or spec.type_used == IO_NODE_TYPE) and behavior.kind != 'python_stub' else attach_global_config(params, prepared.globals[block_id])
            frames[call.id] = NodeFrame(
                id=call.id, type_used=call.type_used, node=implementation,
                requires=spec.requires, provides=spec.provides,
                params=bound_params, max_concurrency=call.max_concurrency,
                incoming=tuple(e for e in compiled.resolved_schedule_edges if e.target == call.id),
                outgoing=tuple(e for e in compiled.resolved_schedule_edges if e.source == call.id),
                transfer_incoming=tuple(e for e in compiled.resolved_transfer_edges if e.target == call.id),
                transfer_outgoing=tuple(e for e in compiled.resolved_transfer_edges if e.source == call.id),
                flow_kind=call.flow_kind, is_terminal=call.is_terminal,
                is_nodeset=call.is_nodeset, is_loop=call.is_loop, is_io=spec.type_used == IO_NODE_TYPE,
                status=call.status, effect_scope='unconstrained' if behavior.kind == 'python_stub' else call.effect_scope, join_policy=call.join_policy,
                nodeset_type_key=call.nodeset_type_key, exports=tuple(getattr(nodeset,'provides',())),
                loop_spec=spec.loop, io_spec=spec.io, execution_lock=spec.execution_lock,
                subplan=bind(call.child_block) if call.child_block else None,
                accepts_context=accepts_context, planned_behavior=behavior,
                planned_stub_module=behavior.stub_module, planned_stub_path=stub_path, planned_stub_hash=stub_hash)
        bindings = build_python_binding_plan(frames, order=block.order, path=block.path,
            plugin_registry=plugin_registry if block_id == prepared.workflow.entry_block else None)
        plan = ExecutionPlan(graph=graph, compiled=compiled, frames=frames, order=block.order,
            max_steps=block.max_steps, python_bindings=bindings, workflow_plan=prepared.workflow,
            contains_global_state=block.contains_global_state,
            contains_execution_locks=bool(block.execution_lock) or any(
                not frame.is_planned and (frame.execution_lock or (frame.subplan and frame.subplan.contains_execution_locks)
                ) for frame in frames.values()))
        blocks = block_loader(plan, block_id) if block_loader is not None else compile_blocks(plan, runtime_options)
        entries = {item.entry:item for item in blocks}
        return replace(plan, blocks=blocks, block_by_entry=entries, compiled_blocks=blocks,
            compiled_block_by_entry=entries, compiled_node_to_block={name:item for item in blocks for name in item.nodes})

    return bind(prepared.workflow.entry_block)
