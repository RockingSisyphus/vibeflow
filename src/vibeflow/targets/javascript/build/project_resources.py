from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from vibeflow.targets.javascript.frontend.errors import ProjectBuildError
from vibeflow.targets.javascript.build.project_graph import (
    implementation_source,
    select_implementation,
)
from vibeflow.targets.javascript.build.project_paths import safe_project_path
from vibeflow.targets.javascript.frontend.schema import (
    JavascriptJsonValueError,
    PortableSchemaError,
    validate_portable_json_schema,
)
from vibeflow.core.descriptors import (
    BaseLibCatalog,
    BaseLibDescriptor,
    CapabilityDescriptor,
    CapabilityOperationDescriptor,
    DescriptorCatalogs,
    HostExtensionDescriptor,
    NodeCatalog,
    NodeDescriptor,
)
from vibeflow.core.flow import GraphConfig
from vibeflow.block_compiler import WorkflowPlan


PORT_CAPABILITY_ID = "vibeflow.port"
PORT_SCHEMA_TYPES = {
    "vibeflow.port.receive.request": {
        "type": "object",
        "required": ["port"],
        "properties": {"port": {"type": "string"}},
        "additionalProperties": False,
    },
    "vibeflow.port.receive.result": {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {}},
        "additionalProperties": False,
    },
    "vibeflow.port.send.request": {
        "type": "object",
        "required": ["port", "value"],
        "properties": {
            "port": {"type": "string"},
            "value": {},
        },
        "additionalProperties": False,
    },
    "vibeflow.port.send.result": {"type": "null"},
}


def port_capability_descriptor(
    operations: set[str],
) -> CapabilityDescriptor:
    available = {
        "receive": CapabilityOperationDescriptor(
            input_type="vibeflow.port.receive.request",
            output_type="vibeflow.port.receive.result",
            completion="suspend",
        ),
        "send": CapabilityOperationDescriptor(
            input_type="vibeflow.port.send.request",
            output_type="vibeflow.port.send.result",
            completion="immediate",
        ),
    }
    return CapabilityDescriptor(
        id=PORT_CAPABILITY_ID,
        targets=("browser", "node"),
        operations={
            name: available[name]
            for name in sorted(operations)
        },
        display_name="VibeFlow Port",
        description="Host-provided receive/send queue boundary.",
    )


def base_lib_closure(
    nodes: Mapping[str, NodeDescriptor],
    *,
    catalog: BaseLibCatalog,
    target: str,
    project_root: Path,
) -> tuple[
    tuple[BaseLibDescriptor, ...],
    Mapping[str, Mapping[str, str]],
]:
    ordered: list[BaseLibDescriptor] = []
    implementations: dict[str, Mapping[str, str]] = {}
    complete: set[str] = set()
    active: list[str] = []

    def visit(resource_id: str) -> None:
        if resource_id in complete:
            return
        if resource_id in active:
            start = active.index(resource_id)
            cycle = " -> ".join((*active[start:], resource_id))
            raise ProjectBuildError(
                "VF_AOT_BASE_LIB_CYCLE",
                f"base_lib dependency cycle: {cycle}",
            )
        descriptor = catalog.get(resource_id)
        if descriptor is None:
            raise ProjectBuildError(
                "VF_AOT_BASE_LIB_UNKNOWN",
                f"unknown required base_lib '{resource_id}'",
            )
        active.append(resource_id)
        for dependency in descriptor.dependencies:
            visit(dependency)
        active.pop()
        selected = select_implementation(
            descriptor.implementations,
            target=target,
            subject=f"base_lib '{descriptor.id}'",
        )
        _source, mapping = implementation_source(
            selected,
            project_root=project_root,
            subject=f"base_lib '{descriptor.id}'",
        )
        implementations[descriptor.id] = mapping
        complete.add(resource_id)
        ordered.append(descriptor)

    for descriptor in sorted(nodes.values(), key=lambda item: item.type_key):
        for resource_id in descriptor.base_libs:
            visit(resource_id)
    return tuple(ordered), implementations


def required_capabilities(
    nodes: Mapping[str, NodeDescriptor],
    *,
    catalogs: DescriptorCatalogs,
    target: str,
    io_operations: set[str] | None = None,
) -> tuple[CapabilityDescriptor, ...]:
    selected: dict[str, CapabilityDescriptor] = {}
    for node in nodes.values():
        for requirement in node.capabilities:
            capability = catalogs.capabilities.get(requirement.id)
            if capability is None:
                raise ProjectBuildError(
                    "VF_AOT_CAPABILITY_UNKNOWN",
                    (
                        f"node '{node.type_key}' requires unknown capability "
                        f"'{requirement.id}'"
                    ),
                )
            if target not in capability.targets:
                raise ProjectBuildError(
                    "VF_AOT_CAPABILITY_TARGET",
                    (
                        f"capability '{capability.id}' does not support "
                        f"target '{target}'"
                    ),
                )
            unknown = sorted(
                set(requirement.operations) - set(capability.operations)
            )
            if unknown:
                raise ProjectBuildError(
                    "VF_AOT_CAPABILITY_OPERATION",
                    (
                        f"node '{node.type_key}' requires unknown operations "
                        f"on capability '{capability.id}': {unknown}"
                    ),
                )
            selected[capability.id] = capability
    if io_operations:
        selected[PORT_CAPABILITY_ID] = port_capability_descriptor(
            io_operations
        )
    return tuple(selected[key] for key in sorted(selected))


def host_extension_closure(
    enabled: tuple[str, ...],
    *,
    catalogs: DescriptorCatalogs,
    target: str,
    project_root: Path,
    configurations: Mapping[str, Mapping[str, Any]] | None = None,
    planned: frozenset[str] = frozenset(),
) -> tuple[Mapping[str, Any], ...]:
    ordered: list[Mapping[str, Any]] = []
    complete: set[str] = set()
    active: list[str] = []
    extension_config = configurations or {}

    def visit(extension_id: str) -> None:
        if extension_id in complete:
            return
        if extension_id in planned:
            raise ProjectBuildError(
                "VF_AOT_HOST_EXTENSION_PLANNED_DEPENDENCY",
                (
                    f"implemented host_extension depends on planned "
                    f"host_extension '{extension_id}'"
                ),
            )
        if extension_id in active:
            start = active.index(extension_id)
            cycle = " -> ".join((*active[start:], extension_id))
            raise ProjectBuildError(
                "VF_AOT_HOST_EXTENSION_CYCLE",
                f"host_extension dependency cycle: {cycle}",
            )
        descriptor = catalogs.host_extensions.get(extension_id)
        if descriptor is None:
            raise ProjectBuildError(
                "VF_AOT_HOST_EXTENSION_UNKNOWN",
                f"unknown host_extension '{extension_id}'",
            )
        if target not in descriptor.targets:
            raise ProjectBuildError(
                "VF_AOT_HOST_EXTENSION_TARGET",
                (
                    f"host_extension '{extension_id}' does not support "
                    f"target '{target}'"
                ),
            )
        active.append(extension_id)
        for dependency in descriptor.dependencies:
            visit(dependency)
        active.pop()
        for capability_id in descriptor.provides:
            capability = (
                port_capability_descriptor({"receive", "send"})
                if capability_id == PORT_CAPABILITY_ID
                else catalogs.capabilities.get(capability_id)
            )
            if capability is None:
                raise ProjectBuildError(
                    "VF_AOT_HOST_EXTENSION_CAPABILITY",
                    (
                        f"host_extension '{extension_id}' provides unknown "
                        f"capability '{capability_id}'"
                    ),
                )
            if target not in capability.targets:
                raise ProjectBuildError(
                    "VF_AOT_HOST_EXTENSION_CAPABILITY",
                    (
                        f"host_extension '{extension_id}' provides capability "
                        f"'{capability_id}' unsupported on target '{target}'"
                    ),
                )
        selected = select_implementation(
            descriptor.implementations,
            target=target,
            subject=f"host_extension '{descriptor.id}'",
        )
        if selected.completion != "immediate":
            raise ProjectBuildError(
                "VF_AOT_HOST_EXTENSION_FACTORY",
                (
                    f"host_extension '{descriptor.id}' factory must use "
                    "completion='immediate'; start/stop may still return Promise"
                ),
            )
        _source, mapping = implementation_source(
            selected,
            project_root=project_root,
            subject=f"host_extension '{descriptor.id}'",
        )
        ordered.append(
            {
                "id": descriptor.id,
                "module": mapping["module"],
                "export": mapping["export"],
                "dependencies": list(descriptor.dependencies),
                "provides": list(descriptor.provides),
                "config": dict(extension_config.get(descriptor.id, {})),
                "external_packages": list(
                    descriptor.external_packages
                ),
            }
        )
        complete.add(extension_id)

    for extension_id in enabled:
        visit(extension_id)
    return tuple(ordered)


def used_schema_types(
    graph: GraphConfig,
    nodes: Mapping[str, NodeDescriptor],
    capabilities: tuple[CapabilityDescriptor, ...],
) -> set[str]:
    used = {item.type for item in graph.inputs}
    used.update(item.type for item in graph.outputs)
    for descriptor in nodes.values():
        used.update(item.type for item in descriptor.contract.requires)
        used.update(item.type for item in descriptor.contract.provides)
    for capability in capabilities:
        for operation in capability.operations.values():
            used.add(operation.input_type)
            used.add(operation.output_type)
    return used


def schemas_for_types(
    type_keys: set[str],
    *,
    catalogs: DescriptorCatalogs,
) -> dict[str, Mapping[str, Any]]:
    schemas: dict[str, Mapping[str, Any]] = {}
    missing: list[str] = []
    for type_key in sorted(type_keys):
        descriptor = catalogs.schemas.get(type_key)
        if descriptor is None:
            builtin = PORT_SCHEMA_TYPES.get(type_key)
            if builtin is not None:
                schemas[type_key] = dict(builtin)
            else:
                missing.append(type_key)
            continue
        payload = descriptor.to_dict()
        schema = dict(payload["schema"])
        try:
            validate_portable_json_schema(
                schema,
                path=f"data_schema[{type_key!r}]",
            )
        except (JavascriptJsonValueError, PortableSchemaError) as exc:
            raise ProjectBuildError(
                getattr(exc, "code", "VF_AOT_SCHEMA_UNSUPPORTED"),
                str(exc),
            ) from exc
        schemas[type_key] = schema
    if missing:
        raise ProjectBuildError(
            "VF_AOT_SCHEMA_MISSING",
            f"JSON data schemas are required for AOT types: {missing}",
        )
    return schemas


def enriched_payload(
    plan: WorkflowPlan,
    *,
    schemas: Mapping[str, Mapping[str, Any]],
    capabilities: tuple[CapabilityDescriptor, ...],
    nodes: Mapping[str, NodeDescriptor],
    implementations: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    payload = plan.to_dict()
    payload["schemas"] = {
        key: dict(value) for key, value in sorted(schemas.items())
    }
    payload["capabilities"] = [
        {
            "id": capability.id,
            "operations": {
                name: operation.to_dict()
                for name, operation in sorted(capability.operations.items())
            },
        }
        for capability in capabilities
    ]
    for block in payload["blocks"]:
        loop = block.get("loop")
        if isinstance(loop, dict):
            if loop.get("stop_after") is None:
                loop.pop("stop_after", None)
            condition = loop.get("stop_when")
            if isinstance(condition, Mapping):
                loop["stop_when"] = {
                    "from": str(condition.get("key", "")),
                    "equals": bool(condition.get("literal", True)),
                }
        for node in block["nodes"]:
            if node.get("type_used") == "vibeflow.io":
                operation = str(node.get("io_operation", ""))
                node["implementation"] = None
                node["completion"] = (
                    "suspend" if operation == "receive" else "immediate"
                )
                node["executor"] = (
                    "event_loop" if operation == "receive" else "current"
                )
                node["capabilities"] = [
                    {
                        "id": PORT_CAPABILITY_ID,
                        "operations": [operation],
                    }
                ]
                continue
            if node.get("is_nodeset") or node.get("is_loop"):
                node["implementation"] = None
                continue
            descriptor = nodes.get(str(node.get("type_used", "")))
            if descriptor is None:
                continue
            implementation = implementations.get(descriptor.type_key, {})
            completion = str(
                implementation.get("completion", "immediate")
                or "immediate"
            )
            node["completion"] = completion
            if node.get("schedule") != "inline" or completion == "suspend":
                node["executor"] = "event_loop"
            else:
                node["executor"] = "current"
            node["capabilities"] = [
                requirement.to_dict()
                for requirement in descriptor.capabilities
            ]
        task_by_node = {
            str(task.get("node_id", "")): task
            for task in block.get("tasks", [])
            if isinstance(task, dict)
        }
        for node in block["nodes"]:
            task = task_by_node.get(str(node.get("id", "")))
            if task is not None:
                task["executor"] = str(
                    node.get("executor", "event_loop")
                )
    return payload


def import_policy(
    *,
    nodes: Mapping[str, NodeDescriptor],
    base_libs: tuple[BaseLibDescriptor, ...],
    node_catalog: NodeCatalog,
    base_lib_catalog: BaseLibCatalog,
    target: str,
    project_root: Path,
    allowed_external: set[str],
    implementations: Mapping[str, Mapping[str, str]],
    host_extensions: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    owners: list[dict[str, Any]] = []
    owner_by_path: dict[Path, tuple[str, str]] = {}

    def add_owner(path: Path, *, kind: str, resource_id: str) -> None:
        resolved = path.resolve()
        previous = owner_by_path.get(resolved)
        current = (kind, resource_id)
        if previous is not None and previous != current:
            raise ProjectBuildError(
                "VF_AOT_IMPORT_OWNER",
                (
                    f"source '{resolved}' is claimed by both "
                    f"{previous[0]} '{previous[1]}' and {kind} '{resource_id}'"
                ),
            )
        owner_by_path[resolved] = current

    for descriptor in node_catalog:
        for implementation in descriptor.implementations:
            if (
                target not in implementation.targets
                or implementation.language not in {"javascript", "typescript"}
                or implementation.source.kind != "file"
            ):
                continue
            source = safe_project_path(
                project_root,
                implementation.source.ref,
                subject=f"node '{descriptor.type_key}' source",
            )
            if source.is_file():
                add_owner(source, kind="node", resource_id=descriptor.type_key)
    for descriptor in base_lib_catalog:
        for implementation in descriptor.implementations:
            if (
                target not in implementation.targets
                or implementation.language not in {"javascript", "typescript"}
                or implementation.source.kind != "file"
            ):
                continue
            source = safe_project_path(
                project_root,
                implementation.source.ref,
                subject=f"base_lib '{descriptor.id}' source",
            )
            if source.is_file():
                add_owner(source, kind="base_lib", resource_id=descriptor.id)
    for extension in host_extensions:
        source = Path(str(extension["module"]))
        if source.is_file():
            add_owner(
                source,
                kind="host_extension",
                resource_id=str(extension["id"]),
            )
    for path, (kind, resource_id) in sorted(
        owner_by_path.items(),
        key=lambda item: item[0].as_posix(),
    ):
        owner: dict[str, Any] = {
            "path": str(path),
            "kind": kind,
            "id": resource_id,
        }
        if kind == "node":
            selected = implementations.get(resource_id)
            if (
                selected is not None
                and Path(str(selected.get("module", ""))).resolve() == path
            ):
                owner["export"] = str(selected.get("export", "run"))
                owner["completion"] = str(
                    selected.get("completion", "immediate")
                )
        elif kind == "host_extension":
            selected = next(
                (
                    extension
                    for extension in host_extensions
                    if str(extension.get("id", "")) == resource_id
                    and Path(
                        str(extension.get("module", ""))
                    ).resolve() == path
                ),
                None,
            )
            if selected is not None:
                owner["export"] = str(
                    selected.get("export", "createHostExtension")
                )
                # host_extension_closure rejects any descriptor whose factory
                # is not declared immediate. Carry that contract into the
                # TypeScript policy so the source implementation is verified.
                owner["completion"] = "immediate"
        owners.append(owner)
    return {
        "owners": owners,
        "node_base_libs": {
            key: list(descriptor.base_libs)
            for key, descriptor in sorted(nodes.items())
        },
        "base_lib_dependencies": {
            str(getattr(descriptor, "id")): list(
                getattr(descriptor, "dependencies")
            )
            for descriptor in base_libs
        },
        "host_extension_dependencies": {
            str(extension["id"]): [
                str(item)
                for item in extension.get("dependencies", ())
            ]
            for extension in host_extensions
        },
        "allowed_external_packages": sorted(allowed_external),
    }


__all__ = [
    "base_lib_closure",
    "enriched_payload",
    "import_policy",
    "host_extension_closure",
    "required_capabilities",
    "schemas_for_types",
    "used_schema_types",
]
