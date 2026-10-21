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
from vibeflow.core.descriptors import BaseLibCatalog, BaseLibDescriptor, CapabilityDescriptor, DescriptorCatalogs, ImplementationDescriptor, NodeDescriptor
from vibeflow.core.descriptors.source_bundle import implementation_sources, source_resources
from vibeflow.core.flow import GraphConfig


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
            source_roots=catalog.source_roots,
            subject=f"base_lib '{descriptor.id}'",
        )
        implementations[descriptor.id] = mapping
        complete.add(resource_id)
        ordered.append(descriptor)

    for descriptor in sorted(nodes.values(), key=lambda item: item.id):
        for resource_id in descriptor.base_libs:
            visit(resource_id)
    return tuple(ordered), implementations


def required_capabilities(
    nodes: Mapping[str, NodeDescriptor],
    *,
    catalogs: DescriptorCatalogs,
    target: str,
) -> tuple[CapabilityDescriptor, ...]:
    selected: dict[str, CapabilityDescriptor] = {}
    for node in nodes.values():
        for requirement in node.capabilities:
            capability = catalogs.capabilities.get(requirement.id)
            if capability is None:
                raise ProjectBuildError(
                    "VF_AOT_CAPABILITY_UNKNOWN",
                    (
                        f"node '{node.id}' requires unknown capability "
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
                        f"node '{node.id}' requires unknown operations "
                        f"on capability '{capability.id}': {unknown}"
                    ),
                )
            selected[capability.id] = capability
    return tuple(selected[key] for key in sorted(selected))





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
    for entry in graph.entries.values():
        used.update(item.type for item in entry.inputs or ())
        used.update(item.type for item in entry.outputs or ())
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


def target_neutral_import_policy(*, catalogs: DescriptorCatalogs, project_root: Path, allowed_external: set[str], node_ids: frozenset[str] | None=None, plugin_ids: frozenset[str]=frozenset(), resource_inventory=()) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Describe a JS/TS source closure without selecting a platform.

    ``node_ids=None`` selects the complete registered node/base-lib catalog for
    project quality.  A concrete set selects only the workflow's implemented
    node types plus their transitive base-lib dependencies for validate/review.
    """

    owners_by_path: dict[Path, list[dict[str, Any]]] = {}

    def add_implementation(
        implementation: ImplementationDescriptor,
        *,
        kind: str,
        resource_id: str,
        default_export: str,
        flow_kind: str = "",
    ) -> None:
        if implementation.language not in {"javascript", "typescript"}:
            return
        if implementation.source.kind != "file":
            raise ProjectBuildError(
                "VF_AOT_IMPLEMENTATION_SOURCE",
                (
                    f"{kind} '{resource_id}' only accepts audited project files; "
                    f"source kind '{implementation.source.kind}' is unsupported"
                ),
            )
        for role, locator in implementation_sources(implementation):
            source = safe_project_path(project_root, locator.ref,
                subject=f"{kind} '{resource_id}' {role}", require_file=True,
                allowed_roots=catalogs.source_roots)
            owner = {"path":str(source), "kind":kind, "id":resource_id,
                     "export":(locator.export or default_export) if role == "entry" else "",
                     "role":role, "flowKind":flow_kind, "completion":getattr(implementation,"completion","immediate")}
            group = {"node":"nodes", "base_lib":"base_libs", "plugin":"plugins", "rule":"rules"}.get(kind)
            origin = catalogs.origins.get((group,resource_id))
            package_id = origin.owner.plugin_id if origin else resource_id if kind == "plugin_declaration" else ""
            package = next((item.get("package_path", "") for item in catalogs.plugin_records if item.get("id") == package_id), "")
            owner.update(pluginId=package_id, packagePath=package)
            previous = owners_by_path.setdefault(source, [])
            if owner not in previous:
                previous.append(owner)

    selected_nodes = tuple(
        descriptor
        for descriptor in catalogs.nodes
        if node_ids is None or descriptor.id in node_ids
    )
    selected_base_lib_ids: set[str]
    if node_ids is None:
        selected_base_lib_ids = {
            descriptor.id for descriptor in catalogs.base_libs
        }
    else:
        selected_base_lib_ids = set()
        visiting: list[str] = []

        def visit_base_lib(resource_id: str) -> None:
            if resource_id in selected_base_lib_ids:
                return
            if resource_id in visiting:
                start = visiting.index(resource_id)
                cycle = " -> ".join((*visiting[start:], resource_id))
                raise ProjectBuildError(
                    "VF_AOT_BASE_LIB_CYCLE",
                    f"base_lib dependency cycle: {cycle}",
                )
            descriptor = catalogs.base_libs.get(resource_id)
            if descriptor is None:
                raise ProjectBuildError(
                    "VF_AOT_BASE_LIB_UNKNOWN",
                    f"unknown required base_lib '{resource_id}'",
                )
            visiting.append(resource_id)
            for dependency in descriptor.dependencies:
                visit_base_lib(dependency)
            visiting.pop()
            selected_base_lib_ids.add(resource_id)

        dependent_resources = (*selected_nodes,

            *(item for item in catalogs.plugins if item.id in plugin_ids),
            *(item for kind,item in source_resources(catalogs) if kind == "plugin_declaration"))
        for descriptor in dependent_resources:
            for resource_id in descriptor.base_libs:
                visit_base_lib(resource_id)

    selected_base_libs = tuple(
        descriptor
        for descriptor in catalogs.base_libs
        if descriptor.id in selected_base_lib_ids
    )

    for descriptor in selected_nodes:
        for implementation in descriptor.implementations:
            add_implementation(
                implementation,
                kind="node",
                resource_id=descriptor.id,
                default_export="run",
                flow_kind=descriptor.flow_kind,
            )
    for descriptor in selected_base_libs:
        allowed_external.update(descriptor.external_packages)
        for implementation in descriptor.implementations:
            add_implementation(
                implementation,
                kind="base_lib",
                resource_id=descriptor.id,
                default_export="",
            )

    for descriptor in catalogs.plugins:
        if descriptor.id not in plugin_ids:
            continue
        allowed_external.update(descriptor.external_packages)
        for implementation in descriptor.implementations:
            add_implementation(
                implementation,
                kind="plugin",
                resource_id=descriptor.id,
                default_export="createPlugin",
            )

    for kind, descriptor in source_resources(catalogs):
        if kind == "plugin_declaration":
            for implementation in descriptor.implementations:
                add_implementation(implementation, kind=kind, resource_id=descriptor.id, default_export="plugin")
    # Contributed checker code belongs to its fixed package declaration. It is
    # ordinary extension code, never a lifecycle factory or business Node.
    for descriptor in catalogs.rules:
        origin = catalogs.origins.get(("rules",descriptor.id))
        if origin is None:
            continue
        for implementation in descriptor.implementations:
            if implementation.source.kind == "file" and (project_root/implementation.source.ref).is_file():
                add_implementation(implementation, kind="plugin_declaration",resource_id=origin.owner.plugin_id,default_export="check")

    from vibeflow.core.descriptors.contributions import resource_kind
    known_owners = []
    for entry in resource_inventory:
        descriptor = entry.descriptor
        kind = resource_kind(descriptor)
        if kind not in {"node", "base_lib"}:
            continue
        for implementation in descriptor.implementations:
            if implementation.language not in {"javascript", "typescript"}:
                continue
            for role, locator in implementation_sources(implementation):
                if locator.kind == "file":
                    known_owners.append({"path":locator.ref, "kind":kind, "id":descriptor.id,
                        "export":locator.export or "run" if role == "entry" else "", "role":role})
    owners = [
        owner
        for path in sorted(owners_by_path, key=lambda item: item.as_posix())
        for owner in owners_by_path[path]
    ]
    return (
        {
            "owners": owners,
            "known_owners": known_owners,
            "node_base_libs": {
                descriptor.id: list(descriptor.base_libs)
                for descriptor in selected_nodes
            },
            "base_lib_dependencies": {
                descriptor.id: list(descriptor.dependencies)
                for descriptor in selected_base_libs
            },

            "resource_base_libs": {kind + ":" + item.id:list(item.base_libs)
                for kind,item in source_resources(catalogs) if hasattr(item,"base_libs")},
            "plugin_contributions": {record["id"]:[{"kind":kind,"id":item.id}
                for kind,group in (("node","nodes"),("base_lib","base_libs"),("plugin","plugins"),("rule","rules"))
                for item in getattr(catalogs,group)
                if catalogs.origins.get((group,item.id)) and catalogs.origins[(group,item.id)].owner.plugin_id == record["id"]]
                for record in catalogs.plugin_records if record.get("loaded")},
            "plugin_dependencies": {
                descriptor.id: list(descriptor.dependencies)
                for descriptor in catalogs.plugins
                if descriptor.id in plugin_ids
            },
            "allowed_external_packages": sorted(allowed_external),
            "source_roots": [value for value in catalogs.source_roots if Path(value) != project_root],
        },
        tuple(sorted({str(item["path"]) for item in owners})),
    )


def driver_import_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Project-neutral owner facts in the driver request spelling."""

    fields = {
        "node_base_libs": "nodeBaseLibs",
        "base_lib_dependencies": "baseLibDependencies",

        "plugin_dependencies": "pluginDependencies",
        "resource_base_libs": "resourceBaseLibs",
        "plugin_contributions": "pluginContributions",
    }
    return {
        "owners": [dict(item) for item in policy.get("owners", ())],
        "knownOwners": [dict(item) for item in policy.get("known_owners", policy.get("knownOwners", ()))],
        **{driver: dict(policy.get(key, policy.get(driver, {})) or {})
           for key, driver in fields.items()},
        "allowedExternalPackages": list(policy.get("allowed_external_packages", policy.get("allowedExternalPackages", ()))),
        "sourceRoots": list(policy.get("source_roots", policy.get("sourceRoots", ()))),
    }



__all__ = [
    "base_lib_closure",
    "driver_import_policy",
    "required_capabilities",
    "schemas_for_types",
    "target_neutral_import_policy",
    "used_schema_types",
]
