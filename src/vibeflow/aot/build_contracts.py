from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from vibeflow.aot.emitter import schema_to_typescript
from vibeflow.aot.errors import AotBuildError
from vibeflow.aot.model import WorkflowSpec
from vibeflow.aot.schema import (
    JavascriptJsonValueError,
    PortableSchemaError,
    validate_javascript_json_value,
    validate_portable_json_schema,
)
from vibeflow.aot.templates import ABORT_SIGNAL_DECLARATION


def validate_schema_subset(
    workflow: WorkflowSpec,
    *,
    implementation_by_type: Mapping[str, object],
) -> None:
    try:
        validate_javascript_json_value(
            workflow.to_dict(),
            path="workflow",
        )
        visited: set[int] = set()

        def visit(plan: WorkflowSpec) -> None:
            if id(plan) in visited:
                return
            visited.add(id(plan))
            for type_key, schema in plan.schemas.items():
                validate_portable_json_schema(
                    schema,
                    path=f"schemas[{type_key!r}]",
                )
            for input_spec in plan.inputs:
                if input_spec.schema is not None:
                    validate_portable_json_schema(
                        input_spec.schema,
                        path=f"inputs[{input_spec.key!r}].schema",
                    )
            for output_spec in plan.outputs:
                if output_spec.schema is not None:
                    validate_portable_json_schema(
                        output_spec.schema,
                        path=f"outputs[{output_spec.alias!r}].schema",
                    )
            for node in plan.nodes:
                if node.subplan is not None:
                    visit(node.subplan)

        visit(workflow)
        for type_key, raw in implementation_by_type.items():
            if not isinstance(raw, Mapping):
                continue
            output_schemas = raw.get("output_schema")
            if not isinstance(output_schemas, Mapping):
                continue
            for provider_key, schema in output_schemas.items():
                validate_portable_json_schema(
                    schema,
                    path=(
                        f"implementations[{str(type_key)!r}]"
                        f".output_schema[{str(provider_key)!r}]"
                    ),
                )
    except (JavascriptJsonValueError, PortableSchemaError) as exc:
        raise AotBuildError(
            getattr(exc, "code", "VF_AOT_SCHEMA_UNSUPPORTED"),
            str(exc),
        ) from exc


def node_contract_check(
    workflow: WorkflowSpec,
    implementations: Mapping[str, object],
) -> str:
    module_bindings: dict[str, str] = {}
    lines = [
        ABORT_SIGNAL_DECLARATION.rstrip(),
        (
            "type Envelope<T> = Readonly<{ key: string; type: string; "
            "value: T; source_node: string }>;"
        ),
    ]
    checks: list[str] = []
    check_index = 0
    capability_descriptors = _capability_descriptors(workflow)

    def visit(plan: WorkflowSpec) -> None:
        nonlocal check_index
        for node in plan.nodes:
            if node.implementation is not None:
                module, exported = _node_implementation(
                    node.type_used,
                    node.implementation.module,
                    node.implementation.export,
                    implementations,
                )
                namespace = module_bindings.setdefault(
                    module,
                    f"__vf_contract_module_{len(module_bindings)}",
                )
                input_members = []
                for requirement in node.requires:
                    value_type = schema_to_typescript(
                        plan.schemas.get(
                            requirement.type,
                            workflow.schemas.get(requirement.type),
                        )
                    )
                    if requirement.cardinality == "all":
                        envelope_type = f"readonly Envelope<{value_type}>[]"
                    elif requirement.cardinality == "optional_one":
                        envelope_type = f"Envelope<{value_type}> | null"
                    else:
                        envelope_type = f"Envelope<{value_type}>"
                    input_members.append(
                        f"readonly {json.dumps(requirement.type)}: {envelope_type}"
                    )
                implementation_metadata = _implementation_metadata(
                    implementations.get(node.type_used)
                )
                output_schemas = implementation_metadata.get("output_schema")
                output_schema_mapping = (
                    output_schemas
                    if isinstance(output_schemas, Mapping)
                    else {}
                )
                output_members = [
                    (
                        f"readonly {json.dumps(provider.key)}: "
                        f"{schema_to_typescript(_provider_schema(
                            provider.key,
                            provider.type,
                            output_schema_mapping,
                            plan,
                            workflow,
                        ))}"
                    )
                    for provider in node.provides
                ]
                input_type = (
                    "{ " + "; ".join(input_members) + " }"
                    if input_members
                    else "Readonly<Record<never, never>>"
                )
                output_type = (
                    "{ " + "; ".join(output_members) + " }"
                    if output_members
                    else "Readonly<Record<never, never>>"
                )
                params_type = _node_params_type(
                    node.params,
                    implementation_metadata,
                )
                context_type = _node_context_type(
                    node,
                    capability_descriptors=capability_descriptors,
                    workflow=workflow,
                )
                checks.extend(
                    [
                        (
                            f"const __vf_checked_{check_index}: ("
                            f"inputs: {input_type}, "
                            f"params: {params_type}, "
                            f"context: {context_type}"
                            f") => {output_type} | Promise<{output_type}> = "
                            f"{namespace}[{json.dumps(exported)}];"
                        ),
                        f"void __vf_checked_{check_index};",
                    ]
                )
                check_index += 1
            if node.subplan is not None:
                visit(node.subplan)

    visit(workflow)
    imports = [
        f"import * as {namespace} from {json.dumps(module)};"
        for module, namespace in module_bindings.items()
    ]
    return "\n".join([*imports, *lines, *checks, ""])


def _implementation_metadata(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _provider_schema(
    provider_key: str,
    type_key: str,
    output_schemas: Mapping[str, Any],
    plan: WorkflowSpec,
    workflow: WorkflowSpec,
) -> Mapping[str, Any] | None:
    contract_schema = output_schemas.get(provider_key)
    if isinstance(contract_schema, Mapping):
        return contract_schema
    return plan.schemas.get(type_key, workflow.schemas.get(type_key))


def _node_params_type(
    params: Mapping[str, Any],
    implementation: Mapping[str, Any],
) -> str:
    raw_schema = implementation.get("params_schema")
    params_schema = raw_schema if isinstance(raw_schema, Mapping) else {}
    keys = sorted({str(key) for key in params} | {str(key) for key in params_schema})
    if not keys:
        return "Readonly<Record<never, never>>"
    members: list[str] = []
    for key in keys:
        schema = params_schema.get(key)
        value_type = (
            schema_to_typescript(schema)
            if isinstance(schema, Mapping)
            else _json_value_typescript(params.get(key))
        )
        optional = "" if key in params else "?"
        members.append(
            f"readonly {json.dumps(key)}{optional}: {value_type}"
        )
    return "{ " + "; ".join(members) + " }"


def _json_value_typescript(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        members = [
            (
                f"readonly {json.dumps(str(key))}: "
                f"{_json_value_typescript(item)}"
            )
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        ]
        return "{ " + "; ".join(members) + " }"
    if isinstance(value, (tuple, list)):
        item_types = sorted({_json_value_typescript(item) for item in value})
        item_type = " | ".join(item_types) if item_types else "never"
        return f"readonly ({item_type})[]"
    return "unknown"


def _capability_descriptors(
    workflow: WorkflowSpec,
) -> Mapping[str, Any]:
    descriptors: dict[str, Any] = {}

    def visit(plan: WorkflowSpec) -> None:
        for descriptor in plan.capabilities:
            descriptors.setdefault(descriptor.id, descriptor)
        for node in plan.nodes:
            if node.subplan is not None:
                visit(node.subplan)

    visit(workflow)
    return descriptors


def _node_context_type(
    node: Any,
    *,
    capability_descriptors: Mapping[str, Any],
    workflow: WorkflowSpec,
) -> str:
    capability_members: list[str] = []
    for requirement in sorted(node.capabilities, key=lambda item: item.id):
        descriptor = capability_descriptors.get(requirement.id)
        operations = (
            tuple(sorted(requirement.operations))
            if requirement.operations
            else tuple(sorted(descriptor.operations if descriptor else ()))
        )
        operation_members: list[str] = []
        for operation_name in operations:
            operation = (
                descriptor.operations.get(operation_name)
                if descriptor is not None
                else None
            )
            input_schema = (
                workflow.schemas.get(operation.input_type)
                if operation is not None and operation.input_type
                else None
            )
            output_schema = (
                workflow.schemas.get(operation.output_type)
                if operation is not None and operation.output_type
                else None
            )
            input_type = schema_to_typescript(input_schema)
            output_type = schema_to_typescript(output_schema)
            return_type = (
                f"Promise<{output_type}>"
                if operation is not None
                and operation.completion == "suspend"
                else output_type
            )
            operation_members.append(
                (
                    f"readonly {json.dumps(operation_name)}: "
                    f"(input: {input_type}) => "
                    f"{return_type}"
                )
            )
        capability_members.append(
            (
                f"readonly {json.dumps(requirement.id)}: "
                "{ "
                + "; ".join(operation_members)
                + " }"
            )
        )
    capabilities_type = (
        "{ " + "; ".join(capability_members) + " }"
        if capability_members
        else "Readonly<Record<never, never>>"
    )
    return (
        "Readonly<{ "
        "signal?: VibeFlowAbortSignal; "
        f"capabilities: {capabilities_type}; "
        "trace(kind: string, details?: Readonly<Record<string, unknown>>): void"
        " }>"
    )


def _node_implementation(
    type_used: str,
    default_module: str,
    default_export: str,
    implementations: Mapping[str, object],
) -> tuple[str, str]:
    value = implementations.get(type_used)
    if value is None:
        return default_module, default_export
    if isinstance(value, (str, Path)):
        return str(value), default_export
    if isinstance(value, Mapping):
        source = value.get("source")
        source_mapping = source if isinstance(source, Mapping) else {}
        module = value.get(
            "module",
            value.get(
                "entry",
                value.get("ref", source_mapping.get("ref", default_module)),
            ),
        )
        exported = value.get(
            "export",
            source_mapping.get("export", default_export),
        )
        return str(module), str(exported or "run")
    return default_module, default_export


__all__ = ["node_contract_check", "validate_schema_subset"]
