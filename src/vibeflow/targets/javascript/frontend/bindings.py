"""Serializable JavaScript implementation bindings beside portable plans."""

from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from vibeflow.block_compiler.model import (
    PortableObject,
    SourceRef,
    WorkflowPlan,
    freeze_json_object,
)
from vibeflow.targets.javascript.frontend.model_types import (
    COMPLETIONS,
    EXECUTORS,
    SCHEDULES,
    CapabilityRequirement,
)


PLUGIN_TYPES = frozenset({"policy", "compiler", "runtime"})
PLUGIN_STATUSES = frozenset({"implemented", "planned"})


@dataclass(frozen=True)
class JavascriptPluginBinding:
    """Frozen JavaScript plugin factory facts beside the portable plan."""

    id: str
    plugin_type: str
    status: str
    target: str
    implementation: SourceRef | None = None
    config: Mapping[str, object] | PortableObject = field(default_factory=dict)
    completion: str = "immediate"
    priority: int = 100
    dependencies: tuple[str, ...] = ()
    external_packages: tuple[str, ...] = ()
    language: str = ""
    source_hash: str = ""
    config_hash: str = ""

    def __post_init__(self) -> None:
        plugin_id = _required_text(self.id, "plugin id")
        plugin_type = str(self.plugin_type or "").strip().lower()
        status = str(self.status or "").strip().lower()
        if plugin_type not in PLUGIN_TYPES and not (
            status == "planned" and not plugin_type
        ):
            raise ValueError(f"plugin type must be one of {sorted(PLUGIN_TYPES)}")
        if status not in PLUGIN_STATUSES:
            raise ValueError(
                f"plugin status must be one of {sorted(PLUGIN_STATUSES)}"
            )
        target = str(self.target or "").strip().lower()
        if target not in {"node", "browser"}:
            raise ValueError("plugin target must be node or browser")
        if status == "implemented" and not isinstance(
            self.implementation,
            SourceRef,
        ):
            raise TypeError("implemented plugin requires a SourceRef")
        if (
            status == "implemented"
            and isinstance(self.implementation, SourceRef)
            and not self.implementation.export.strip()
        ):
            raise ValueError("implemented plugin requires a factory export")
        if status == "planned" and self.implementation is not None:
            raise ValueError("planned plugin cannot bind an implementation")
        config = _portable_object(self.config, "plugin config")
        if self.completion not in COMPLETIONS:
            raise ValueError(f"completion must be one of {sorted(COMPLETIONS)}")
        if plugin_type in {"policy", "compiler"} and self.completion != "immediate":
            raise ValueError(
                f"{plugin_type} plugin factory must use immediate completion"
            )
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("plugin priority must be an integer")
        language = str(self.language or "").strip().lower()
        language = {"js": "javascript", "ts": "typescript"}.get(
            language,
            language,
        )
        if status == "implemented" and language not in {
            "javascript",
            "typescript",
        }:
            raise ValueError(
                "implemented JavaScript plugin language must be javascript or typescript"
            )
        if status == "planned" and language:
            raise ValueError("planned plugin cannot bind an implementation language")
        source_hash = _content_hash(self.source_hash, "source_hash")
        if status == "planned" and source_hash:
            raise ValueError("planned plugin cannot bind a source hash")
        canonical_config = json.dumps(
            config.to_value(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        expected_config_hash = hashlib.sha256(
            canonical_config.encode("utf-8")
        ).hexdigest()
        config_hash = _content_hash(self.config_hash, "config_hash")
        if config_hash and config_hash != expected_config_hash:
            raise ValueError("config_hash does not match plugin config")
        object.__setattr__(self, "id", plugin_id)
        object.__setattr__(self, "plugin_type", plugin_type)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "config", config)
        object.__setattr__(
            self,
            "dependencies",
            _unique_text_tuple(self.dependencies, "plugin dependencies"),
        )
        object.__setattr__(
            self,
            "external_packages",
            _unique_text_tuple(
                self.external_packages,
                "plugin external_packages",
            ),
        )
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "source_hash", source_hash)
        object.__setattr__(self, "config_hash", expected_config_hash)

    @property
    def module(self) -> str:
        return self.implementation.ref if self.implementation is not None else ""

    @property
    def export(self) -> str:
        return self.implementation.export if self.implementation is not None else ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "status": self.status,
            "target": self.target,
            "config": self.config.to_value(),
            "priority": self.priority,
            "dependencies": list(self.dependencies),
            "external_packages": list(self.external_packages),
            "config_hash": self.config_hash,
        }
        if self.plugin_type:
            payload["type"] = self.plugin_type
        if self.implementation is not None:
            payload.update(
                {
                    "module": self.module,
                    "export": self.export,
                    "completion": self.completion,
                    "language": self.language,
                    "source_hash": self.source_hash,
                }
            )
        return payload

    def to_value(self) -> dict[str, object]:
        return self.to_dict()


@dataclass(frozen=True)
class JavascriptCallBinding:
    """Static JavaScript source and contract facts for one node call."""

    path: tuple[str, ...]
    type_key: str
    implementation: SourceRef
    params: Mapping[str, object] | PortableObject = field(default_factory=dict)
    base_libs: tuple[str, ...] = ()
    capabilities: tuple[CapabilityRequirement, ...] = ()
    completion: str = "immediate"
    schedule: str = "inline"
    executor: str = "current"
    language: str = "javascript"
    params_schema: Mapping[str, object] | PortableObject = field(default_factory=dict)
    output_schema: Mapping[str, object] | PortableObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _binding_path(self.path))
        object.__setattr__(self, "type_key", _required_text(self.type_key, "type_key"))
        if not isinstance(self.implementation, SourceRef):
            raise TypeError("implementation must be a SourceRef")
        object.__setattr__(self, "params", _portable_object(self.params, "params"))
        object.__setattr__(self, "base_libs", _unique_text_tuple(self.base_libs, "base_libs"))
        capabilities = tuple(self.capabilities)
        if not all(isinstance(item, CapabilityRequirement) for item in capabilities):
            raise TypeError("capabilities must contain CapabilityRequirement values")
        object.__setattr__(self, "capabilities", capabilities)
        if self.completion not in COMPLETIONS:
            raise ValueError(f"completion must be one of {sorted(COMPLETIONS)}")
        if self.schedule not in SCHEDULES:
            raise ValueError(f"schedule must be one of {sorted(SCHEDULES)}")
        if self.executor not in EXECUTORS:
            raise ValueError(f"executor must be one of {sorted(EXECUTORS)}")
        language = str(self.language).strip().lower()
        language = {"js": "javascript", "ts": "typescript"}.get(language, language)
        if language not in {"javascript", "typescript"}:
            raise ValueError("language must be javascript or typescript")
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "params_schema", _portable_object(
            self.params_schema, "params_schema"
        ))
        object.__setattr__(self, "output_schema", _portable_object(
            self.output_schema, "output_schema"
        ))

    def to_dict(self) -> dict[str, object]:
        return {
            "path": list(self.path),
            "type_key": self.type_key,
            "implementation": self.implementation.to_dict(),
            "params": self.params.to_value(),
            "base_libs": list(self.base_libs),
            "capabilities": [item.to_dict() for item in self.capabilities],
            "completion": self.completion,
            "schedule": self.schedule,
            "executor": self.executor,
            "language": self.language,
            "params_schema": self.params_schema.to_value(),
            "output_schema": self.output_schema.to_value(),
        }

@dataclass(frozen=True)
class JavascriptSchemaMemberOrder:
    """Original JSON Schema ``properties`` order used by declaration output."""

    source: tuple[str, ...]
    path: tuple[str | int, ...]
    members: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _binding_path(self.source))
        path = tuple(self.path)
        valid = all(_valid_schema_path_item(item) for item in path)
        if not valid:
            raise ValueError(
                "schema member-order path entries must be non-empty strings "
                "or non-negative integers"
            )
        object.__setattr__(self, "path", path)
        members = _unique_text_tuple(tuple(self.members), "schema members")
        object.__setattr__(self, "members", members)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": list(self.source),
            "path": list(self.path),
            "members": list(self.members),
        }

@dataclass(frozen=True)
class JavascriptBindingPlan:
    """JavaScript-only source, resource, host, and import-policy sidecar."""

    workflow_id: str
    calls: tuple[JavascriptCallBinding, ...] = ()
    schemas: Mapping[str, object] | PortableObject = field(default_factory=dict)
    base_libs: Mapping[str, object] | PortableObject = field(default_factory=dict)
    capabilities: Mapping[str, object] | PortableObject = field(default_factory=dict)
    host_extensions: tuple[Mapping[str, object] | PortableObject, ...] = ()
    runtime_plugins: tuple[JavascriptPluginBinding, ...] = ()
    import_policy: Mapping[str, object] | PortableObject = field(default_factory=dict)
    schema_member_orders: tuple[JavascriptSchemaMemberOrder, ...] = ()

    def __post_init__(self) -> None:
        workflow_id = _required_text(self.workflow_id, "workflow_id")
        object.__setattr__(self, "workflow_id", workflow_id)
        calls = tuple(self.calls)
        if not all(isinstance(item, JavascriptCallBinding) for item in calls):
            raise TypeError("calls must contain JavascriptCallBinding values")
        paths = tuple(item.path for item in calls)
        if len(set(paths)) != len(paths):
            raise ValueError("call paths must be unique")
        object.__setattr__(self, "calls", calls)
        for name in ("schemas", "base_libs", "capabilities", "import_policy"):
            value = _portable_object(getattr(self, name), name)
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "host_extensions",
            tuple(
                _portable_object(value, f"host_extensions[{index}]")
                for index, value in enumerate(self.host_extensions)
            ),
        )
        runtime_plugins = tuple(self.runtime_plugins)
        if not all(
            isinstance(item, JavascriptPluginBinding)
            for item in runtime_plugins
        ):
            raise TypeError(
                "runtime_plugins must contain JavascriptPluginBinding values"
            )
        invalid_runtime = [
            item.id
            for item in runtime_plugins
            if item.plugin_type != "runtime" or item.status != "implemented"
        ]
        if invalid_runtime:
            raise ValueError(
                "runtime_plugins must contain active runtime bindings: "
                f"{invalid_runtime}"
            )
        plugin_ids = tuple(item.id for item in runtime_plugins)
        if len(set(plugin_ids)) != len(plugin_ids):
            raise ValueError("runtime plugin ids must be unique")
        object.__setattr__(self, "runtime_plugins", runtime_plugins)
        orders = tuple(self.schema_member_orders)
        if not all(isinstance(item, JavascriptSchemaMemberOrder) for item in orders):
            raise TypeError(
                "schema_member_orders must contain "
                "JavascriptSchemaMemberOrder values"
            )
        ordered = tuple(sorted(orders, key=_schema_member_order_key))
        identities = tuple((item.source, item.path) for item in ordered)
        if len(set(identities)) != len(identities):
            raise ValueError("schema member-order locations must be unique")
        object.__setattr__(self, "schema_member_orders", ordered)

    def binding(self, path: tuple[str, ...]) -> JavascriptCallBinding:
        normalized = _binding_path(path)
        for binding in self.calls:
            if binding.path == normalized:
                return binding
        raise KeyError(".".join(normalized))

    def to_dict(self) -> dict[str, object]:
        return {
            "workflow_id": self.workflow_id,
            "calls": [item.to_dict() for item in self.calls],
            "schemas": self.schemas.to_value(),
            "base_libs": self.base_libs.to_value(),
            "capabilities": self.capabilities.to_value(),
            "host_extensions": [item.to_value() for item in self.host_extensions],
            "runtime_plugins": [item.to_dict() for item in self.runtime_plugins],
            "import_policy": self.import_policy.to_value(),
            "schema_member_orders": [
                item.to_dict() for item in self.schema_member_orders
            ],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        )

def build_javascript_binding_plan(
    plan: WorkflowPlan,
    *,
    implementations: Mapping[str, Mapping[str, object]] | None = None,
    base_libs_by_type: Mapping[str, Sequence[str]] | None = None,
    capabilities_by_type: Mapping[
        str,
        Sequence[CapabilityRequirement | Mapping[str, object]],
    ]
    | None = None,
    schemas: Mapping[str, object] | None = None,
    base_libs: Mapping[str, object] | None = None,
    capabilities: Mapping[str, object] | None = None,
    host_extensions: Sequence[Mapping[str, object]] = (),
    runtime_plugins: Sequence[JavascriptPluginBinding] = (),
    import_policy: Mapping[str, object] | None = None,
) -> JavascriptBindingPlan:
    """Build a JavaScript sidecar from plain, in-memory Target facts."""

    if not isinstance(plan, WorkflowPlan):
        raise TypeError("plan must be a WorkflowPlan")
    implementation_facts = implementations or {}
    base_lib_facts = base_libs_by_type or {}
    capability_facts = capabilities_by_type or {}
    calls: list[JavascriptCallBinding] = []
    schema_orders: list[JavascriptSchemaMemberOrder] = []
    for block in plan.blocks:
        for node in block.nodes:
            path = (*block.path, node.id)
            metadata = implementation_facts.get(node.type_used, {})
            completion = _completion(node, metadata)
            executor = _javascript_executor(completion, node.schedule)
            params_schema = _mapping_fact(metadata, "params_schema")
            output_schema = _mapping_fact(metadata, "output_schema")
            schema_orders.extend(_contract_schema_orders(
                path, "params_schema", params_schema
            ))
            schema_orders.extend(_contract_schema_orders(
                path, "output_schema", output_schema
            ))
            calls.append(
                JavascriptCallBinding(
                    path=path,
                    type_key=node.type_used,
                    implementation=node.implementation,
                    params=node.params,
                    base_libs=_base_lib_ids(node.type_used, base_lib_facts),
                    capabilities=_call_capabilities(
                        node.type_used,
                        node.io_operation,
                        capability_facts,
                    ),
                    completion=completion,
                    schedule=node.schedule,
                    executor=executor,
                    language=_implementation_language(
                        metadata, node.implementation.ref
                    ),
                    params_schema=params_schema,
                    output_schema=output_schema,
                )
            )
    schema_mapping = schemas or {}
    for type_key in sorted(schema_mapping):
        schema_orders.extend(_schema_member_orders(
            ("schemas", str(type_key)), schema_mapping[type_key]
        ))
    return JavascriptBindingPlan(
        workflow_id=plan.workflow_id,
        calls=tuple(calls),
        schemas=schema_mapping,
        base_libs=base_libs or {},
        capabilities=capabilities or {},
        host_extensions=tuple(host_extensions),
        runtime_plugins=tuple(runtime_plugins),
        import_policy=import_policy or {},
        schema_member_orders=tuple(schema_orders),
    )


def _mapping_fact(
    metadata: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = metadata.get(key, {})
    if not isinstance(value, Mapping):
        raise TypeError(f"implementation {key} must be a mapping")
    return value


def _content_hash(value: object, field_name: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized and (
        len(normalized) != 64
        or any(character not in "0123456789abcdef" for character in normalized)
    ):
        raise ValueError(f"{field_name} must be an SHA-256 hex digest")
    return normalized


def _base_lib_ids(
    type_key: str,
    facts: Mapping[str, Sequence[str]],
) -> tuple[str, ...]:
    label = f"base_libs_by_type[{type_key!r}]"
    return tuple(sorted({_required_text(value, label) for value in facts.get(type_key, ())}))


def _implementation_language(
    metadata: Mapping[str, object],
    source_ref: str,
) -> str:
    supplied = str(metadata.get("language", "") or "").strip().lower()
    if supplied:
        return supplied
    return (
        "typescript"
        if Path(source_ref).suffix.lower() in {".ts", ".tsx", ".mts"}
        else "javascript"
    )


def _contract_schema_orders(
    call_path: tuple[str, ...],
    contract_name: str,
    schemas: Mapping[str, object],
) -> tuple[JavascriptSchemaMemberOrder, ...]:
    result: list[JavascriptSchemaMemberOrder] = []
    for key in sorted(schemas):
        result.extend(
            _schema_member_orders(
                ("calls", *call_path, contract_name, str(key)),
                schemas[key],
            )
        )
    return tuple(result)


def _schema_member_orders(
    source: tuple[str, ...],
    schema: object,
) -> tuple[JavascriptSchemaMemberOrder, ...]:
    result: list[JavascriptSchemaMemberOrder] = []

    def visit(value: object, path: tuple[str | int, ...]) -> None:
        if isinstance(value, Mapping):
            properties = value.get("properties")
            if isinstance(properties, Mapping):
                members = tuple(properties)
                if not all(isinstance(item, str) and item for item in members):
                    raise TypeError(
                        "JSON Schema properties keys must be non-empty strings"
                    )
                result.append(
                    JavascriptSchemaMemberOrder(
                        source=source,
                        path=path,
                        members=members,
                    )
                )
            for key, child in value.items():
                if not isinstance(key, str):
                    raise TypeError("JSON Schema keys must be strings")
                visit(child, (*path, key))
            return
        if isinstance(value, (tuple, list)):
            for index, child in enumerate(value):
                visit(child, (*path, index))

    visit(schema, ())
    return tuple(result)


def _schema_member_order_key(
    value: JavascriptSchemaMemberOrder,
) -> str:
    return json.dumps(
        [list(value.source), list(value.path)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _completion(node: object, metadata: Mapping[str, object]) -> str:
    operation = str(getattr(node, "io_operation", ""))
    if operation == "receive":
        return "suspend"
    if operation == "send":
        return "immediate"
    value = metadata.get("completion", getattr(node, "completion", "immediate"))
    return str(value or "immediate")


def _javascript_executor(completion: str, schedule: str) -> str:
    if completion == "suspend" or schedule != "inline":
        return "event_loop"
    return "current"


def _call_capabilities(
    type_key: str,
    io_operation: str,
    facts: Mapping[
        str,
        Sequence[CapabilityRequirement | Mapping[str, object]],
    ],
) -> tuple[CapabilityRequirement, ...]:
    if io_operation:
        return (CapabilityRequirement("vibeflow.port", (io_operation,)),)
    normalized: list[CapabilityRequirement] = []
    for index, raw in enumerate(facts.get(type_key, ())):
        if isinstance(raw, CapabilityRequirement):
            requirement = raw
        elif isinstance(raw, Mapping):
            capability_id = _required_text(
                raw.get("id"),
                f"capabilities_by_type[{type_key!r}][{index}].id",
            )
            operations = raw.get("operations", ())
            if not isinstance(operations, (tuple, list)):
                raise TypeError("capability operations must be a tuple or list")
            names = {
                _required_text(operation, "capability operation")
                for operation in operations
            }
            requirement = CapabilityRequirement(capability_id, tuple(sorted(names)))
        else:
            raise TypeError(
                "capability facts must contain mappings or "
                "CapabilityRequirement values"
            )
        normalized.append(requirement)
    return tuple(sorted(normalized, key=lambda item: item.id))


def _portable_object(
    value: Mapping[str, object] | PortableObject,
    path: str,
) -> PortableObject:
    if isinstance(value, PortableObject):
        return value
    if not isinstance(value, Mapping):
        raise TypeError(f"{path} must be a mapping")
    return freeze_json_object(value, path=path)


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _binding_path(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError("binding path must be a non-empty tuple")
    return tuple(_required_text(item, "binding path entry") for item in value)


def _valid_schema_path_item(value: object) -> bool:
    return (
        isinstance(value, str) and bool(value)
        or isinstance(value, int) and not isinstance(value, bool) and value >= 0
    )


def _unique_text_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{label} must be a tuple")
    normalized = tuple(_required_text(item, f"{label} entry") for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} entries must be unique")
    return normalized


__all__ = [
    "JavascriptBindingPlan",
    "JavascriptCallBinding",
    "JavascriptPluginBinding",
    "JavascriptSchemaMemberOrder",
    "build_javascript_binding_plan",
]
