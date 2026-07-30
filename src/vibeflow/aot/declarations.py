from __future__ import annotations

import json
import re
from typing import Any, Mapping

from vibeflow.aot.model import CapabilitySpec, WorkflowSpec
from vibeflow.aot.templates import DECLARATION_PREAMBLE


def declarations(
    workflow: WorkflowSpec,
    *,
    has_host_extensions: bool = False,
) -> str:
    input_lines: list[str] = []
    for item in workflow.inputs:
        optional = "" if item.required else "?"
        input_lines.append(
            f"  readonly {json.dumps(item.key)}{optional}: "
            f"{schema_to_typescript(item.schema)};"
        )
    output_lines: list[str] = []
    for item in workflow.outputs:
        optional = "?" if item.cardinality == "optional_one" else ""
        value_type = schema_to_typescript(item.schema)
        if item.cardinality == "all":
            value_type = f"readonly ({value_type})[]"
        output_lines.append(
            f"  readonly {json.dumps(item.alias)}{optional}: {value_type};"
        )
    capability_lines = _capability_declarations(workflow)
    lines = [
            DECLARATION_PREAMBLE.rstrip(),
            "",
            "export interface WorkflowInputs {",
            *input_lines,
            "}",
            "",
            "export interface WorkflowOutputs {",
            *output_lines,
            "}",
            "",
            *capability_lines,
            "",
            "export interface WorkflowRunOptions {",
            "  readonly signal?: VibeFlowAbortSignal;",
            '  readonly trace?: WorkflowTraceMode;',
            "  readonly onTrace?: (event: WorkflowTraceEvent) => void;",
            "  readonly capabilities?: WorkflowCapabilities;",
            "  readonly detachedTimeoutMs?: number;",
            "}",
            "",
            "export const VIBEFLOW_WORKFLOW_ABI: \"vibeflow.workflow.v2\";",
            _entry_declaration(workflow),
    ]
    if has_host_extensions:
        lines.extend(["", *_host_declarations(workflow)])
    lines.append("")
    return "\n".join(lines)


def _entry_declaration(workflow: WorkflowSpec) -> str:
    if workflow.entry_mode == "sync":
        return (
            "export function runWorkflow("
            "inputs: WorkflowInputs, options?: WorkflowRunOptions"
            "): WorkflowOutputs;"
        )
    return (
        "export function runWorkflowAsync("
        "inputs: WorkflowInputs, options?: WorkflowRunOptions"
        "): Promise<WorkflowOutputs>;"
    )


def _host_declarations(workflow: WorkflowSpec) -> list[str]:
    invocation = (
        "runWorkflow(inputs: WorkflowInputs, "
        "options?: WorkflowRunOptions): WorkflowOutputs;"
        if workflow.entry_mode == "sync"
        else "runWorkflowAsync(inputs: WorkflowInputs, "
        "options?: WorkflowRunOptions): Promise<WorkflowOutputs>;"
    )
    return [
        "export interface WorkflowHostOptions {",
        "  readonly capabilities?: WorkflowCapabilities;",
        "}",
        "",
        "export interface WorkflowHost {",
        "  readonly signal: VibeFlowAbortSignal;",
        "  readonly started: boolean;",
        "  start(): Promise<void>;",
        "  stop(): Promise<void>;",
        f"  {invocation}",
        "}",
        "",
        "export function createWorkflowHost(",
        "  options?: WorkflowHostOptions,",
        "): WorkflowHost;",
    ]


def _capability_declarations(workflow: WorkflowSpec) -> list[str]:
    descriptors: dict[str, CapabilitySpec] = {}
    required: dict[str, set[str]] = {}

    def visit(plan: WorkflowSpec) -> None:
        for descriptor in plan.capabilities:
            descriptors.setdefault(descriptor.id, descriptor)
        for node in plan.nodes:
            for requirement in node.capabilities:
                required.setdefault(
                    requirement.id,
                    set(),
                ).update(requirement.operations)
            if node.subplan is not None:
                visit(node.subplan)

    visit(workflow)
    lines = ["export interface WorkflowCapabilities {"]
    for capability_id in sorted(required):
        interface_name = _typescript_name("Capability", capability_id)
        lines.append(
            f"  readonly {json.dumps(capability_id)}: {interface_name};"
        )
    lines.append("}")
    for capability_id in sorted(required):
        descriptor = descriptors.get(capability_id)
        operations = required[capability_id] or set(
            descriptor.operations if descriptor else ()
        )
        interface_name = _typescript_name("Capability", capability_id)
        lines.extend(["", f"export interface {interface_name} {{"])
        for operation_name in sorted(operations):
            operation = (
                descriptor.operations.get(operation_name)
                if descriptor
                else None
            )
            input_type = schema_to_typescript(
                workflow.schemas.get(operation.input_type)
                if operation and operation.input_type
                else None
            )
            output_type = schema_to_typescript(
                workflow.schemas.get(operation.output_type)
                if operation and operation.output_type
                else None
            )
            return_type = (
                f"Promise<{output_type}>"
                if operation and operation.completion == "suspend"
                else output_type
            )
            lines.append(
                f"  readonly {json.dumps(operation_name)}: "
                f"(input: {input_type}, context: "
                "{ readonly signal?: VibeFlowAbortSignal }) "
                f"=> {return_type};"
            )
        lines.append("}")
    return lines


def _typescript_name(prefix: str, value: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", value)
    suffix = "".join(
        part[:1].upper() + part[1:] for part in parts
    ) or "Anonymous"
    if suffix[0].isdigit():
        suffix = f"_{suffix}"
    return f"{prefix}{suffix}"


def schema_to_typescript(schema: Mapping[str, Any] | None) -> str:
    if not schema:
        return "unknown"
    if "const" in schema:
        return _literal_type(schema["const"])
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return " | ".join(_literal_type(item) for item in enum)
    any_of = schema.get("anyOf", schema.get("oneOf"))
    if isinstance(any_of, list) and any_of:
        return " | ".join(
            schema_to_typescript(
                item if isinstance(item, Mapping) else None
            )
            for item in any_of
        )
    all_of = schema.get("allOf")
    if isinstance(all_of, list) and all_of:
        return " & ".join(
            schema_to_typescript(
                item if isinstance(item, Mapping) else None
            )
            for item in all_of
        )
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join(
            schema_to_typescript({**dict(schema), "type": item})
            for item in schema_type
        )
    if schema_type == "null":
        return "null"
    if schema_type == "boolean":
        return "boolean"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "string":
        return "string"
    if schema_type == "array":
        item_schema = schema.get("items")
        item_type = schema_to_typescript(
            item_schema if isinstance(item_schema, Mapping) else None
        )
        return f"readonly ({item_type})[]"
    if schema_type == "object" or isinstance(
        schema.get("properties"),
        Mapping,
    ):
        return _object_type(schema)
    return "unknown"


def _object_type(schema: Mapping[str, Any]) -> str:
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        return "Readonly<Record<string, unknown>>"
    required = {
        str(item)
        for item in schema.get("required", ())
        if isinstance(item, str)
    }
    members = []
    for key, child in properties.items():
        optional = "" if str(key) in required else "?"
        members.append(
            f"readonly {json.dumps(str(key))}{optional}: "
            f"{schema_to_typescript(child if isinstance(child, Mapping) else None)}"
        )
    if not members and schema.get("additionalProperties") is False:
        return "Readonly<Record<string, never>>"
    if schema.get("additionalProperties") is not False:
        members.append("readonly [key: string]: unknown")
    return "{ " + "; ".join(members) + " }"


def _literal_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, Mapping):
        if not value:
            return "Readonly<Record<string, never>>"
        members = [
            (
                f"readonly {json.dumps(str(key), ensure_ascii=False)}: "
                f"{_literal_type(item)}"
            )
            for key, item in sorted(
                value.items(),
                key=lambda entry: str(entry[0]),
            )
        ]
        return "{ " + "; ".join(members) + " }"
    if isinstance(value, (list, tuple)):
        return (
            "readonly ["
            + ", ".join(_literal_type(item) for item in value)
            + "]"
        )
    raise TypeError(
        f"JSON Schema literal is not JSON-compatible: "
        f"{type(value).__name__}"
    )


__all__ = ["declarations", "schema_to_typescript"]
