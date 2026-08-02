from __future__ import annotations

from typing import Any, Callable, Mapping

from vibeflow.core.contracts import (
    CARDINALITIES,
    DataProvider,
    DataRequirement,
)
from vibeflow.tooling.project.descriptor_values import (
    boolean as _boolean,
    check_fields as _check_fields,
    mapping_list as _mapping_list,
    mapping_or_empty as _mapping_or_empty,
    nullable_string as _nullable_string,
    object_list as _object_list,
    optional_string as _optional_string,
    required_mapping as _required_mapping,
    required_string as _required_string,
    string_list as _string_list,
)
from vibeflow.core.descriptors.models import (
    BaseLibDescriptor,
    CapabilityDescriptor,
    CapabilityOperationDescriptor,
    CapabilityRequirementDescriptor,
    DataSchemaDescriptor,
    DescriptorModelError,
    HostExtensionDescriptor,
    ImplementationDescriptor,
    NodeContractDescriptor,
    NodeDescriptor,
    PluginDescriptor,
    SourceLocator,
)
from vibeflow.core.config.node import normalize_node_config_spec


def parse_descriptor_manifest(
    data: Mapping[str, Any],
    *,
    expected_kind: str | None = None,
) -> (
    NodeDescriptor
    | BaseLibDescriptor
    | DataSchemaDescriptor
    | CapabilityDescriptor
    | HostExtensionDescriptor
    | PluginDescriptor
):
    """Parse one already-decoded manifest object."""

    if not isinstance(data, Mapping):
        raise DescriptorModelError(
            "descriptor manifest root must be a single object"
        )
    kind = _required_string(data.get("kind"), field="kind")
    if expected_kind is not None and kind != expected_kind:
        raise DescriptorModelError(
            f"descriptor kind '{kind}' does not match directory kind "
            f"'{expected_kind}'"
        )
    parser: dict[str, Callable[[Mapping[str, Any]], object]] = {
        "node": _parse_node,
        "base_lib": _parse_base_lib,
        "data_schema": _parse_data_schema,
        "capability": _parse_capability,
        "host_extension": _parse_host_extension,
        "plugin": _parse_plugin,
    }
    try:
        selected = parser[kind]
    except KeyError as exc:
        raise DescriptorModelError(
            "kind must be one of "
            f"{sorted(parser)}"
        ) from exc
    return selected(data)  # type: ignore[return-value]


def _parse_node(data: Mapping[str, Any]) -> NodeDescriptor:
    _check_fields(
        data,
        allowed={
            "kind",
            "type_key",
            "display_name",
            "category",
            "description",
            "version",
            "flow_kind",
            "purity",
            "author",
            "tags",
            "external",
            "contract",
            "implementations",
            "base_libs",
            "capabilities",
        },
        field="node",
    )
    raw_contract = _required_mapping(data.get("contract"), field="node.contract")
    return NodeDescriptor(
        type_key=_required_string(data.get("type_key"), field="node.type_key"),
        display_name=_required_string(
            data.get("display_name"),
            field="node.display_name",
        ),
        category=_optional_string(data.get("category")),
        description=_required_string(
            data.get("description"),
            field="node.description",
        ),
        version=_required_string(data.get("version"), field="node.version"),
        flow_kind=_required_string(
            data.get("flow_kind"),
            field="node.flow_kind",
        ),
        purity=_optional_string(data.get("purity")) or "pure",
        author=_nullable_string(data.get("author"), field="node.author"),
        tags=_string_list(data.get("tags", ()), field="node.tags"),
        external=_boolean(data.get("external", False), field="node.external"),
        contract=_parse_contract(raw_contract),
        implementations=_parse_implementations(
            data.get("implementations", ()),
            field="node.implementations",
        ),
        base_libs=_string_list(
            data.get("base_libs", ()),
            field="node.base_libs",
        ),
        capabilities=_parse_capability_requirements(
            data.get("capabilities", ()),
        ),
    )


def _parse_contract(data: Mapping[str, Any]) -> NodeContractDescriptor:
    _check_fields(
        data,
        allowed={
            "requires",
            "provides",
            "input_semantics",
            "output_semantics",
            "params_schema",
            "params_defaults",
            "output_schema",
            "examples",
        },
        field="node.contract",
    )
    params_schema = _mapping_or_empty(
        data.get("params_schema"),
        field="node.contract.params_schema",
    )
    params_defaults = _mapping_or_empty(
        data.get("params_defaults"),
        field="node.contract.params_defaults",
    )
    config_spec = normalize_node_config_spec(
        params_schema,
        params_defaults,
    )
    return NodeContractDescriptor(
        requires=_parse_requirements(data.get("requires", ())),
        provides=_parse_providers(data.get("provides", ())),
        input_semantics=_mapping_or_empty(
            data.get("input_semantics"),
            field="node.contract.input_semantics",
        ),
        output_semantics=_mapping_or_empty(
            data.get("output_semantics"),
            field="node.contract.output_semantics",
        ),
        params_schema=config_spec.schema,
        params_defaults=config_spec.defaults,
        output_schema=_mapping_or_empty(
            data.get("output_schema"),
            field="node.contract.output_schema",
        ),
        examples=_mapping_list(
            data.get("examples", ()),
            field="node.contract.examples",
        ),
    )


def _parse_requirements(value: object) -> tuple[DataRequirement, ...]:
    items = _object_list(value, field="node.contract.requires")
    requirements: list[DataRequirement] = []
    for index, item in enumerate(items):
        field = f"node.contract.requires[{index}]"
        _check_fields(
            item,
            allowed={"type", "cardinality", "display_name"},
            field=field,
        )
        cardinality = _required_string(
            item.get("cardinality"),
            field=f"{field}.cardinality",
        )
        if cardinality not in CARDINALITIES:
            raise DescriptorModelError(
                f"{field}.cardinality must be one of "
                f"{sorted(CARDINALITIES)}"
            )
        requirements.append(
            DataRequirement(
                type=_required_string(
                    item.get("type"),
                    field=f"{field}.type",
                ),
                cardinality=cardinality,
                display_name=_optional_string(item.get("display_name")),
            )
        )
    return tuple(requirements)


def _parse_providers(value: object) -> tuple[DataProvider, ...]:
    items = _object_list(value, field="node.contract.provides")
    providers: list[DataProvider] = []
    for index, item in enumerate(items):
        field = f"node.contract.provides[{index}]"
        _check_fields(
            item,
            allowed={"key", "type", "display_name"},
            field=field,
        )
        providers.append(
            DataProvider(
                key=_required_string(
                    item.get("key"),
                    field=f"{field}.key",
                ),
                type=_required_string(
                    item.get("type"),
                    field=f"{field}.type",
                ),
                display_name=_optional_string(item.get("display_name")),
            )
        )
    return tuple(providers)


def _parse_implementations(
    value: object,
    *,
    field: str,
    default_export: str | None = None,
) -> tuple[ImplementationDescriptor, ...]:
    items = _object_list(value, field=field)
    implementations: list[ImplementationDescriptor] = []
    for index, item in enumerate(items):
        item_field = f"{field}[{index}]"
        _check_fields(
            item,
            allowed={"language", "targets", "source", "completion"},
            field=item_field,
        )
        source = _required_mapping(
            item.get("source"),
            field=f"{item_field}.source",
        )
        _check_fields(
            source,
            allowed={"kind", "ref", "export"},
            field=f"{item_field}.source",
        )
        implementations.append(
            ImplementationDescriptor(
                language=_required_string(
                    item.get("language"),
                    field=f"{item_field}.language",
                ),
                targets=_string_list(
                    item.get("targets"),
                    field=f"{item_field}.targets",
                ),
                source=SourceLocator(
                    kind=_required_string(
                        source.get("kind"),
                        field=f"{item_field}.source.kind",
                    ),
                    ref=_required_string(
                        source.get("ref"),
                        field=f"{item_field}.source.ref",
                    ),
                    export=_nullable_string(
                        source.get("export"),
                        field=f"{item_field}.source.export",
                    ) or default_export,
                ),
                completion=_optional_string(
                    item.get("completion")
                ) or "immediate",
            )
        )
    return tuple(implementations)


def _parse_capability_requirements(
    value: object,
) -> tuple[CapabilityRequirementDescriptor, ...]:
    items = _object_list(value, field="node.capabilities")
    requirements: list[CapabilityRequirementDescriptor] = []
    for index, item in enumerate(items):
        field = f"node.capabilities[{index}]"
        _check_fields(item, allowed={"id", "operations"}, field=field)
        requirements.append(
            CapabilityRequirementDescriptor(
                id=_required_string(item.get("id"), field=f"{field}.id"),
                operations=_string_list(
                    item.get("operations"),
                    field=f"{field}.operations",
                ),
            )
        )
    return tuple(requirements)


def _parse_base_lib(data: Mapping[str, Any]) -> BaseLibDescriptor:
    _check_fields(
        data,
        allowed={
            "kind",
            "id",
            "display_name",
            "description",
            "category",
            "version",
            "implementations",
            "dependencies",
            "external_packages",
        },
        field="base_lib",
    )
    return BaseLibDescriptor(
        id=_required_string(data.get("id"), field="base_lib.id"),
        display_name=_required_string(
            data.get("display_name"),
            field="base_lib.display_name",
        ),
        description=_required_string(
            data.get("description"),
            field="base_lib.description",
        ),
        category=_optional_string(data.get("category")),
        version=_optional_string(data.get("version")),
        implementations=_parse_implementations(
            data.get("implementations"),
            field="base_lib.implementations",
        ),
        dependencies=_string_list(
            data.get("dependencies", ()),
            field="base_lib.dependencies",
        ),
        external_packages=_string_list(
            data.get("external_packages", ()),
            field="base_lib.external_packages",
        ),
    )


def _parse_data_schema(data: Mapping[str, Any]) -> DataSchemaDescriptor:
    _check_fields(
        data,
        allowed={
            "kind",
            "type_key",
            "id",
            "representation",
            "display_name",
            "description",
            "schema",
        },
        field="data_schema",
    )
    raw_type_key = data.get("type_key")
    raw_id = data.get("id")
    if raw_type_key is not None and raw_id is not None and raw_type_key != raw_id:
        raise DescriptorModelError(
            "data_schema.type_key and data_schema.id cannot disagree"
        )
    return DataSchemaDescriptor(
        type_key=_required_string(
            raw_type_key if raw_type_key is not None else raw_id,
            field="data_schema.type_key",
        ),
        representation=_optional_string(data.get("representation")) or "json",
        display_name=_optional_string(data.get("display_name")),
        description=_optional_string(data.get("description")),
        schema=_required_mapping(
            data.get("schema"),
            field="data_schema.schema",
        ),
    )


def _parse_capability(data: Mapping[str, Any]) -> CapabilityDescriptor:
    _check_fields(
        data,
        allowed={
            "kind",
            "id",
            "targets",
            "display_name",
            "description",
            "operations",
        },
        field="capability",
    )
    raw_operations = _required_mapping(
        data.get("operations"),
        field="capability.operations",
    )
    operations: dict[str, CapabilityOperationDescriptor] = {}
    for name, raw_operation in raw_operations.items():
        field = f"capability.operations.{name}"
        operation = _required_mapping(raw_operation, field=field)
        _check_fields(
            operation,
            allowed={"input_type", "output_type", "completion"},
            field=field,
        )
        operations[str(name)] = CapabilityOperationDescriptor(
            input_type=_required_string(
                operation.get("input_type"),
                field=f"{field}.input_type",
            ),
            output_type=_required_string(
                operation.get("output_type"),
                field=f"{field}.output_type",
            ),
            completion=_optional_string(
                operation.get("completion")
            ) or "immediate",
        )
    return CapabilityDescriptor(
        id=_required_string(data.get("id"), field="capability.id"),
        targets=_string_list(
            data.get("targets"),
            field="capability.targets",
        ),
        display_name=_optional_string(data.get("display_name")),
        description=_optional_string(data.get("description")),
        operations=operations,
    )


def _parse_host_extension(
    data: Mapping[str, Any],
) -> HostExtensionDescriptor:
    _check_fields(
        data,
        allowed={
            "kind",
            "id",
            "targets",
            "display_name",
            "description",
            "version",
            "implementations",
            "provides",
            "dependencies",
            "external_packages",
        },
        field="host_extension",
    )
    return HostExtensionDescriptor(
        id=_required_string(
            data.get("id"),
            field="host_extension.id",
        ),
        targets=_string_list(
            data.get("targets"),
            field="host_extension.targets",
        ),
        display_name=_optional_string(data.get("display_name")),
        description=_optional_string(data.get("description")),
        version=_optional_string(data.get("version")),
        implementations=_parse_implementations(
            data.get("implementations"),
            field="host_extension.implementations",
        ),
        provides=_string_list(
            data.get("provides", ()),
            field="host_extension.provides",
        ),
        dependencies=_string_list(
            data.get("dependencies", ()),
            field="host_extension.dependencies",
        ),
        external_packages=_string_list(
            data.get("external_packages", ()),
            field="host_extension.external_packages",
        ),
    )


def _parse_plugin(data: Mapping[str, Any]) -> PluginDescriptor:
    _check_fields(
        data,
        allowed={
            "kind",
            "id",
            "type",
            "targets",
            "display_name",
            "category",
            "description",
            "version",
            "priority",
            "implementations",
            "dependencies",
            "external_packages",
            "config",
        },
        field="plugin",
    )
    config = _mapping_or_empty(data.get("config"), field="plugin.config")
    _check_fields(
        config,
        allowed={"schema", "defaults"},
        field="plugin.config",
    )
    raw_priority = data.get("priority", 100)
    if isinstance(raw_priority, bool) or not isinstance(raw_priority, int):
        raise DescriptorModelError("plugin.priority must be an integer")
    return PluginDescriptor(
        id=_required_string(data.get("id"), field="plugin.id"),
        plugin_type=_required_string(data.get("type"), field="plugin.type"),
        targets=_string_list(data.get("targets"), field="plugin.targets"),
        display_name=_optional_string(data.get("display_name")),
        category=_optional_string(data.get("category")),
        description=_optional_string(data.get("description")),
        version=_optional_string(data.get("version")),
        priority=raw_priority,
        implementations=_parse_implementations(
            data.get("implementations"),
            field="plugin.implementations",
            default_export="createPlugin",
        ),
        dependencies=_string_list(
            data.get("dependencies", ()),
            field="plugin.dependencies",
        ),
        external_packages=_string_list(
            data.get("external_packages", ()),
            field="plugin.external_packages",
        ),
        config_schema=_mapping_or_empty(
            config.get("schema"),
            field="plugin.config.schema",
        ),
        config_defaults=_mapping_or_empty(
            config.get("defaults"),
            field="plugin.config.defaults",
        ),
    )
