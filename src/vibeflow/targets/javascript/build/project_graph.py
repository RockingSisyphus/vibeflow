from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from vibeflow.targets.javascript.frontend.errors import ProjectBuildError
from vibeflow.targets.javascript.build.project_paths import safe_project_path
from vibeflow.targets.javascript.frontend.schema import (
    JavascriptJsonValueError,
    PortableSchemaError,
    validate_portable_json_schema,
)
from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.core.descriptors import (
    BaseLibCatalog,
    ImplementationDescriptor,
    NodeCatalog,
    NodeDescriptor,
)
from vibeflow.core.flow import (
    GraphConfig,
    IO_NODE_TYPE,
    LOOP_NODE_TYPES,
    STATUS_PLANNED,
    NodeSpec,
)
from vibeflow.core.planned import effective_planned_behavior
from vibeflow.core.config.node import (
    NodeConfigError,
    merge_node_config,
    normalize_node_config_spec,
)
from vibeflow.block_compiler import SourceRef
from vibeflow.core.config.scope import (
    ConfigScope,
    attach_global_config,
    merge_config_scopes,
    nested_node_config_overrides,
    node_invocation_scope,
    normalize_config_scope,
    scoped_node_params,
)


@dataclass
class PreparationState:
    target: str
    project_root: Path
    catalog: NodeCatalog
    base_libs: BaseLibCatalog
    compile_graph: Callable[[GraphConfig, set[str], str], CompiledGraph]
    compiled_by_path: dict[tuple[str, ...], CompiledGraph]
    params_by_path: dict[tuple[str, ...], Mapping[str, object]]
    source_by_type: dict[str, SourceRef]
    implementations: dict[str, object]
    used_nodes: dict[str, NodeDescriptor]
    used_types: set[str]
    used_io_operations: set[str]


def prepare_graph(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    state: PreparationState,
    path: tuple[str, ...],
    overrides: Mapping[str, Mapping[str, object]],
    global_scope: ConfigScope,
    active_nodesets: tuple[str, ...],
) -> None:
    del compiled
    require_explicit_inputs(graph, path=path)
    state.used_types.update(item.type for item in graph.inputs)
    state.used_types.update(item.type for item in graph.outputs)
    for spec in graph.nodes:
        call_path = (*path, spec.id)
        state.used_types.update(item.type for item in spec.requires)
        state.used_types.update(item.type for item in spec.provides)
        if spec.status == STATUS_PLANNED:
            raise ProjectBuildError(
                "VF_AOT_PLANNED_NODE",
                "planned nodes cannot target JavaScript",
                call_path,
            )
        if spec.type_used == IO_NODE_TYPE:
            state.used_io_operations.add(spec.io.operation)
            state.params_by_path[call_path] = {}
            continue
        is_loop = spec.type_used in LOOP_NODE_TYPES
        is_nodeset = spec.type_used in graph.nodesets and not is_loop
        if is_loop or is_nodeset:
            nodeset_key = spec.loop.body if is_loop else spec.type_used
            nodeset = graph.nodesets.get(nodeset_key)
            if nodeset is None:
                raise ProjectBuildError(
                    "VF_AOT_NODESET",
                    f"unknown nodeset '{nodeset_key}'",
                    call_path,
                )
            behavior = effective_planned_behavior(spec, nodeset)
            if nodeset.status == STATUS_PLANNED or behavior.kind != "blocking":
                raise ProjectBuildError(
                    "VF_AOT_PLANNED_NODE",
                    (
                        f"nodeset '{nodeset_key}' uses unsupported planned "
                        f"behavior '{behavior.kind}'"
                    ),
                    call_path,
                )
            if not is_loop:
                _check_contract(
                    spec,
                    requires=nodeset.requires,
                    provides=nodeset.provides,
                    path=call_path,
                    subject=f"nodeset '{nodeset_key}'",
                )
            if nodeset_key in active_nodesets:
                chain = " -> ".join((*active_nodesets, nodeset_key))
                raise ProjectBuildError(
                    "VF_AOT_NODESET_RECURSION",
                    f"recursive nodeset calls cannot target AOT: {chain}",
                    call_path,
                )
            state.params_by_path[call_path] = {}
            child_overrides = nested_node_config_overrides(spec, overrides)
            caller_values = {
                **dict(spec.params),
                **dict(global_scope.values),
                **dict(overrides.get(spec.id, {})),
            }
            caller_scope = node_invocation_scope(
                caller_values,
                allow_config_override=spec.allow_config_override,
            )
            child_scope = merge_config_scopes(
                normalize_config_scope(nodeset.global_config),
                caller_scope,
            )
            child_compiled = state.compile_graph(
                nodeset.graph,
                set(nodeset.graph.nodesets),
                f"nodeset:{nodeset.type_key}",
            )
            state.compiled_by_path[call_path] = child_compiled
            prepare_graph(
                nodeset.graph,
                child_compiled,
                state=state,
                path=call_path,
                overrides=child_overrides,
                global_scope=child_scope,
                active_nodesets=(*active_nodesets, nodeset_key),
            )
            continue

        descriptor = state.catalog.get(spec.type_used)
        if descriptor is None:
            raise ProjectBuildError(
                "VF_AOT_NODE_UNKNOWN",
                f"node type '{spec.type_used}' has no descriptor",
                call_path,
            )
        _check_contract(
            spec,
            requires=descriptor.contract.requires,
            provides=descriptor.contract.provides,
            path=call_path,
            subject=f"node descriptor '{descriptor.type_key}'",
        )
        _validate_node_output_schemas(descriptor, path=call_path)
        implementation = select_implementation(
            descriptor.implementations,
            target=state.target,
            subject=f"node '{descriptor.type_key}'",
            path=call_path,
        )
        source_ref, implementation_mapping = implementation_source(
            implementation,
            project_root=state.project_root,
            subject=f"node '{descriptor.type_key}'",
            path=call_path,
        )
        implementation_mapping = {
            **implementation_mapping,
            "params_schema": dict(descriptor.contract.params_schema),
            "params_defaults": dict(descriptor.contract.params_defaults),
            "output_schema": dict(descriptor.contract.output_schema),
        }
        previous = state.implementations.get(descriptor.type_key)
        if previous is not None and previous != implementation_mapping:
            raise ProjectBuildError(
                "VF_AOT_IMPLEMENTATION_CONFLICT",
                f"node '{descriptor.type_key}' resolved inconsistently",
                call_path,
            )
        state.source_by_type[descriptor.type_key] = source_ref
        state.implementations[descriptor.type_key] = implementation_mapping
        state.used_nodes[descriptor.type_key] = descriptor
        state.used_types.update(
            item.type for item in descriptor.contract.requires
        )
        state.used_types.update(
            item.type for item in descriptor.contract.provides
        )
        state.params_by_path[call_path] = _effective_params(
            spec,
            descriptor,
            overrides=overrides,
            global_scope=global_scope,
            path=call_path,
        )


def _effective_params(
    spec: NodeSpec,
    descriptor: NodeDescriptor,
    *,
    overrides: Mapping[str, Mapping[str, object]],
    global_scope: ConfigScope,
    path: tuple[str, ...],
) -> Mapping[str, object]:
    try:
        config_spec = normalize_node_config_spec(
            descriptor.contract.params_schema,
            descriptor.contract.params_defaults,
        )
        local = scoped_node_params(
            spec.params,
            global_scope,
            declared_keys=set(config_spec.schema),
        )
        merged = merge_node_config(
            config_spec,
            {**local, **dict(overrides.get(spec.id, {}))},
        )
        return attach_global_config(merged, global_scope.values)
    except NodeConfigError as exc:
        raise ProjectBuildError(
            "VF_AOT_PARAMS",
            f"invalid effective params for '{spec.type_used}': {exc}",
            path,
        ) from exc


def _check_contract(
    spec: NodeSpec,
    *,
    requires: tuple[DataRequirement, ...],
    provides: tuple[DataProvider, ...],
    path: tuple[str, ...],
    subject: str,
) -> None:
    mismatches: list[str] = []
    if tuple(spec.requires) != tuple(requires):
        mismatches.append("requires")
    if tuple(spec.provides) != tuple(provides):
        mismatches.append("provides")
    if mismatches:
        raise ProjectBuildError(
            "VF_AOT_CONTRACT_INVALID",
            (
                f"graph call does not match {subject}: "
                f"{', '.join(mismatches)}"
            ),
            path,
        )


def select_implementation(
    implementations: tuple[ImplementationDescriptor, ...],
    *,
    target: str,
    subject: str,
    path: tuple[str, ...] = (),
) -> ImplementationDescriptor:
    selected = [
        item
        for item in implementations
        if target in item.targets
        and item.language in {"javascript", "typescript"}
    ]
    if not selected:
        available = sorted(
            {
                target_name
                for item in implementations
                for target_name in item.targets
            }
        )
        raise ProjectBuildError(
            "VF_AOT_TARGET_IMPLEMENTATION_MISSING",
            (
                f"{subject} has no JS/TS implementation for "
                f"target '{target}'; available targets: {available}"
            ),
            path,
        )
    if len(selected) > 1:
        raise ProjectBuildError(
            "VF_AOT_CONTRACT_INVALID",
            (
                f"{subject} declares more than one JS/TS implementation for "
                f"target '{target}'"
            ),
            path,
        )
    return selected[0]


def implementation_source(
    implementation: ImplementationDescriptor,
    *,
    project_root: Path,
    subject: str,
    path: tuple[str, ...] = (),
) -> tuple[SourceRef, dict[str, str]]:
    source = implementation.source
    if source.kind != "file":
        raise ProjectBuildError(
            "VF_AOT_IMPLEMENTATION_SOURCE",
            (
                f"{subject} uses source kind '{source.kind}', but the first "
                "JS/TS AOT release only accepts audited project files"
            ),
            path,
        )
    resolved = safe_project_path(
        project_root,
        source.ref,
        subject=f"{subject} source",
        require_file=True,
    )
    module = str(resolved)
    export = source.export or "run"
    return (
        SourceRef(kind=source.kind, ref=module, export=export),
        {
            "module": module,
            "export": export,
            "language": implementation.language,
            "completion": implementation.completion,
        },
    )


def _validate_node_output_schemas(
    descriptor: NodeDescriptor,
    *,
    path: tuple[str, ...],
) -> None:
    for provider_key, schema in descriptor.contract.output_schema.items():
        try:
            validate_portable_json_schema(
                schema,
                path=(
                    f"node[{descriptor.type_key!r}]"
                    f".output_schema[{provider_key!r}]"
                ),
            )
        except (JavascriptJsonValueError, PortableSchemaError) as exc:
            raise ProjectBuildError(
                getattr(exc, "code", "VF_AOT_SCHEMA_UNSUPPORTED"),
                str(exc),
                path,
            ) from exc


def require_explicit_inputs(
    graph: GraphConfig,
    *,
    path: tuple[str, ...],
) -> None:
    ambiguous = [item.key for item in graph.inputs if item.required is None]
    if ambiguous:
        raise ProjectBuildError(
            "VF_AOT_INPUT_REQUIRED",
            (
                "JS AOT pipeline inputs must explicitly declare required: "
                f"{ambiguous}"
            ),
            path,
        )


__all__ = [
    "PreparationState",
    "implementation_source",
    "prepare_graph",
    "require_explicit_inputs",
    "select_implementation",
]
