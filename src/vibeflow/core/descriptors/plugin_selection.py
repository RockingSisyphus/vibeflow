"""Pure plugin selection, Planned handling, and dependency closure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vibeflow.core.descriptors._resource_models import (
    PLUGIN_TYPES,
    PluginDescriptor,
)
from vibeflow.core.descriptors.catalogs import PluginCatalog
from vibeflow.core.descriptors.models import (
    IMPLEMENTATION_TARGETS,
    ImplementationDescriptor,
    _freeze_mapping,
    _required_text,
    _string_tuple,
    _thaw_json,
)
from vibeflow.core.flow import STATUS_IMPLEMENTED, STATUS_PLANNED, STATUSES


@dataclass(frozen=True)
class PluginSelectionError(ValueError):
    """A stable, language-neutral plugin selection failure."""

    code: str
    message: str
    plugin_id: str = ""

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True)
class PluginSelection:
    """One plugin declaration from a workflow or project configuration.

    Planned selections are complete architecture facts in their own right.
    They do not require a catalog descriptor and are never bound to an
    implementation.
    """

    id: str
    status: str = STATUS_IMPLEMENTED
    plugin_type: str = ""
    targets: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    config: Mapping[str, Any] = field(default_factory=dict)
    priority: int | None = None
    display_name: str = ""
    description: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        try:
            plugin_id = _required_text(self.id, field_name="plugin selection id")
            status = _required_text(
                self.status,
                field_name="plugin selection status",
            ).lower()
            plugin_type = str(self.plugin_type or "").strip().lower()
            targets = _string_tuple(
                self.targets,
                field_name="plugin selection targets",
            )
            dependencies = _string_tuple(
                self.dependencies,
                field_name="plugin selection dependencies",
            )
            config = _freeze_mapping(
                self.config,
                field_name="plugin selection config",
            )
        except ValueError as exc:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.SCHEMA",
                str(exc),
                str(self.id or "").strip(),
            ) from exc
        if status not in STATUSES:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.STATUS",
                f"plugin '{plugin_id}' status must be one of {sorted(STATUSES)}",
                plugin_id,
            )
        if plugin_type and plugin_type not in PLUGIN_TYPES:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.TYPE",
                f"plugin '{plugin_id}' type must be one of {sorted(PLUGIN_TYPES)}",
                plugin_id,
            )
        unknown_targets = sorted(set(targets) - IMPLEMENTATION_TARGETS)
        if unknown_targets:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.TARGET",
                f"plugin '{plugin_id}' has unsupported targets: {unknown_targets}",
                plugin_id,
            )
        if plugin_id in dependencies:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.DEPENDENCY",
                f"plugin '{plugin_id}' cannot depend on itself",
                plugin_id,
            )
        if self.priority is not None and (
            isinstance(self.priority, bool)
            or not isinstance(self.priority, int)
        ):
            raise PluginSelectionError(
                "PLUGIN.SELECTION.PRIORITY",
                f"plugin '{plugin_id}' priority must be an integer",
                plugin_id,
            )
        object.__setattr__(self, "id", plugin_id)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "plugin_type", plugin_type)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "config", config)
        object.__setattr__(
            self,
            "display_name",
            str(self.display_name or "").strip(),
        )
        object.__setattr__(
            self,
            "description",
            str(self.description or "").strip(),
        )
        object.__setattr__(self, "version", str(self.version or "").strip())

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "status": self.status,
            "config": _thaw_json(self.config),
        }
        if self.plugin_type:
            payload["type"] = self.plugin_type
        if self.targets:
            payload["targets"] = list(self.targets)
        if self.dependencies:
            payload["dependencies"] = list(self.dependencies)
        if self.priority is not None:
            payload["priority"] = self.priority
        for key in ("display_name", "description", "version"):
            value = getattr(self, key)
            if value:
                payload[key] = value
        return payload


@dataclass(frozen=True)
class ResolvedPluginSelection:
    """A selected plugin with an implementation only when it is active."""

    selection: PluginSelection
    descriptor: PluginDescriptor | None
    implementation: ImplementationDescriptor | None
    plugin_type: str
    targets: tuple[str, ...]
    dependencies: tuple[str, ...]
    config: Mapping[str, Any]
    priority: int

    def __post_init__(self) -> None:
        if self.selection.status == STATUS_PLANNED and self.implementation is not None:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.PLANNED_IMPLEMENTATION",
                f"planned plugin '{self.selection.id}' cannot bind an implementation",
                self.selection.id,
            )
        object.__setattr__(
            self,
            "config",
            _freeze_mapping(
                self.config,
                field_name=f"resolved plugin '{self.selection.id}' config",
            ),
        )

    @property
    def id(self) -> str:
        return self.selection.id

    @property
    def status(self) -> str:
        return self.selection.status

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "type": self.plugin_type,
            "status": self.status,
            "targets": list(self.targets),
            "dependencies": list(self.dependencies),
            "config": _thaw_json(self.config),
            "priority": self.priority,
        }
        if self.implementation is not None:
            payload["implementation"] = self.implementation.to_dict()
        return payload


@dataclass(frozen=True)
class PluginResolution:
    """Deterministic plugin closure split into active and Planned sets."""

    declared: tuple[ResolvedPluginSelection, ...]
    active: tuple[ResolvedPluginSelection, ...]
    planned: tuple[ResolvedPluginSelection, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "declared": [item.to_dict() for item in self.declared],
            "active": [item.to_dict() for item in self.active],
            "planned": [item.to_dict() for item in self.planned],
        }


@dataclass(frozen=True)
class PluginReviewRecord:
    """Language-neutral Plugin facts for architecture and review output.

    Review records intentionally omit implementation and source locators.  An
    implemented record still requires a descriptor, while a Planned record is
    complete without one.
    """

    id: str
    plugin_type: str
    status: str
    targets: tuple[str, ...]
    dependencies: tuple[str, ...]
    config: Mapping[str, Any]
    priority: int
    display_name: str = ""
    category: str = ""
    description: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "config",
            _freeze_mapping(
                self.config,
                field_name=f"plugin review record '{self.id}' config",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.id,
            "type": self.plugin_type,
            "status": self.status,
            "targets": list(self.targets),
            "dependencies": list(self.dependencies),
            "config": _thaw_json(self.config),
            "config_keys": sorted(self.config),
            "priority": self.priority,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
        }


def review_plugin_selections(
    selections: tuple[PluginSelection, ...],
    *,
    catalog: PluginCatalog,
) -> tuple[PluginReviewRecord, ...]:
    """Resolve architecture facts without selecting or loading source code."""

    if not isinstance(catalog, PluginCatalog):
        raise TypeError("catalog must be a PluginCatalog")
    declared = tuple(selections)
    if not all(isinstance(item, PluginSelection) for item in declared):
        raise TypeError("selections must contain PluginSelection values")
    seen: set[str] = set()
    records: list[PluginReviewRecord] = []
    for selection in declared:
        if selection.id in seen:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.DUPLICATE",
                f"duplicate plugin selection '{selection.id}'",
                selection.id,
            )
        seen.add(selection.id)
        descriptor = catalog.get(selection.id)
        if descriptor is None and selection.status == STATUS_IMPLEMENTED:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.UNKNOWN",
                f"unknown implemented plugin '{selection.id}'",
                selection.id,
            )
        if descriptor is not None:
            _validate_selection_contract(selection, descriptor)
        config = (
            dict(_thaw_json(descriptor.config_defaults))
            if descriptor is not None
            else {}
        )
        config.update(_thaw_json(selection.config))
        if descriptor is not None:
            _validate_plugin_config(
                config,
                descriptor.config_schema,
                plugin_id=selection.id,
            )
        records.append(
            PluginReviewRecord(
                id=selection.id,
                plugin_type=(
                    selection.plugin_type
                    or (descriptor.plugin_type if descriptor is not None else "")
                ),
                status=selection.status,
                targets=(
                    selection.targets
                    or (descriptor.targets if descriptor is not None else ())
                ),
                dependencies=(
                    selection.dependencies
                    or (descriptor.dependencies if descriptor is not None else ())
                ),
                config=config,
                priority=(
                    selection.priority
                    if selection.priority is not None
                    else (descriptor.priority if descriptor is not None else 100)
                ),
                display_name=(
                    selection.display_name
                    or (descriptor.display_name if descriptor is not None else "")
                ),
                category=(descriptor.category if descriptor is not None else ""),
                description=(
                    selection.description
                    or (descriptor.description if descriptor is not None else "")
                ),
                version=(
                    selection.version
                    or (descriptor.version if descriptor is not None else "")
                ),
            )
        )
    return tuple(records)


def resolve_plugin_selections(
    selections: tuple[PluginSelection, ...],
    *,
    catalog: PluginCatalog,
    target: str,
) -> PluginResolution:
    """Resolve implemented plugins without loading any implementation source."""

    if not isinstance(catalog, PluginCatalog):
        raise TypeError("catalog must be a PluginCatalog")
    normalized_target = str(target or "").strip().lower()
    if normalized_target not in IMPLEMENTATION_TARGETS:
        raise PluginSelectionError(
            "PLUGIN.SELECTION.TARGET",
            f"unsupported plugin target '{normalized_target}'",
        )
    declared_selections = tuple(selections)
    if not all(isinstance(item, PluginSelection) for item in declared_selections):
        raise TypeError("selections must contain PluginSelection values")
    by_id: dict[str, PluginSelection] = {}
    for selection in declared_selections:
        if selection.id in by_id:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.DUPLICATE",
                f"duplicate plugin selection '{selection.id}'",
                selection.id,
            )
        by_id[selection.id] = selection

    planned: list[ResolvedPluginSelection] = []
    planned_by_id: dict[str, ResolvedPluginSelection] = {}
    for selection in declared_selections:
        if selection.status != STATUS_PLANNED:
            continue
        descriptor = catalog.get(selection.id)
        if descriptor is not None:
            _validate_selection_contract(selection, descriptor)
        resolved = _resolve_planned(selection, descriptor)
        planned.append(resolved)
        planned_by_id[selection.id] = resolved

    active: list[ResolvedPluginSelection] = []
    active_by_id: dict[str, ResolvedPluginSelection] = {}
    visiting: list[str] = []

    def visit(plugin_id: str) -> None:
        if plugin_id in active_by_id:
            return
        if plugin_id in planned_by_id:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.PLANNED_DEPENDENCY",
                f"implemented plugin depends on planned plugin '{plugin_id}'",
                plugin_id,
            )
        if plugin_id in visiting:
            start = visiting.index(plugin_id)
            cycle = " -> ".join((*visiting[start:], plugin_id))
            raise PluginSelectionError(
                "PLUGIN.SELECTION.CYCLE",
                f"plugin dependency cycle: {cycle}",
                plugin_id,
            )
        descriptor = catalog.get(plugin_id)
        if descriptor is None:
            code = (
                "PLUGIN.SELECTION.UNKNOWN"
                if plugin_id in by_id
                else "PLUGIN.SELECTION.DEPENDENCY"
            )
            raise PluginSelectionError(
                code,
                f"unknown implemented plugin '{plugin_id}'",
                plugin_id,
            )
        selection = by_id.get(plugin_id) or PluginSelection(id=plugin_id)
        _validate_selection_contract(selection, descriptor)
        if normalized_target not in descriptor.targets:
            raise PluginSelectionError(
                "PLUGIN.SELECTION.TARGET",
                f"plugin '{plugin_id}' does not support target '{normalized_target}'",
                plugin_id,
            )
        visiting.append(plugin_id)
        for dependency_id in descriptor.dependencies:
            visit(dependency_id)
        visiting.pop()
        implementation = _implementation_for_target(
            descriptor,
            target=normalized_target,
        )
        config = dict(_thaw_json(descriptor.config_defaults))
        config.update(_thaw_json(selection.config))
        _validate_plugin_config(
            config,
            descriptor.config_schema,
            plugin_id=plugin_id,
        )
        resolved = ResolvedPluginSelection(
            selection=selection,
            descriptor=descriptor,
            implementation=implementation,
            plugin_type=descriptor.plugin_type,
            targets=descriptor.targets,
            dependencies=descriptor.dependencies,
            config=config,
            priority=(
                selection.priority
                if selection.priority is not None
                else descriptor.priority
            ),
        )
        active_by_id[plugin_id] = resolved
        active.append(resolved)

    implemented_roots = tuple(
        selection
        for selection in declared_selections
        if selection.status == STATUS_IMPLEMENTED
    )
    for selection in sorted(
        implemented_roots,
        key=lambda item: (_effective_priority(item, catalog), item.id),
    ):
        visit(selection.id)

    declared: list[ResolvedPluginSelection] = []
    for selection in declared_selections:
        resolved = (
            planned_by_id.get(selection.id)
            if selection.status == STATUS_PLANNED
            else active_by_id.get(selection.id)
        )
        assert resolved is not None
        declared.append(resolved)
    return PluginResolution(
        declared=tuple(declared),
        active=tuple(active),
        planned=tuple(planned),
    )


def _resolve_planned(
    selection: PluginSelection,
    descriptor: PluginDescriptor | None,
) -> ResolvedPluginSelection:
    defaults = (
        dict(_thaw_json(descriptor.config_defaults))
        if descriptor is not None
        else {}
    )
    defaults.update(_thaw_json(selection.config))
    if descriptor is not None:
        _validate_plugin_config(
            defaults,
            descriptor.config_schema,
            plugin_id=selection.id,
        )
    return ResolvedPluginSelection(
        selection=selection,
        descriptor=descriptor,
        implementation=None,
        plugin_type=(
            selection.plugin_type
            or (descriptor.plugin_type if descriptor is not None else "")
        ),
        targets=(
            selection.targets
            or (descriptor.targets if descriptor is not None else ())
        ),
        dependencies=(
            selection.dependencies
            or (descriptor.dependencies if descriptor is not None else ())
        ),
        config=defaults,
        priority=(
            selection.priority
            if selection.priority is not None
            else (descriptor.priority if descriptor is not None else 100)
        ),
    )


def _validate_selection_contract(
    selection: PluginSelection,
    descriptor: PluginDescriptor,
) -> None:
    mismatches: list[str] = []
    if selection.plugin_type and selection.plugin_type != descriptor.plugin_type:
        mismatches.append("type")
    if selection.targets and set(selection.targets) != set(descriptor.targets):
        mismatches.append("targets")
    if (
        selection.dependencies
        and selection.dependencies != descriptor.dependencies
    ):
        mismatches.append("dependencies")
    if mismatches:
        raise PluginSelectionError(
            "PLUGIN.SELECTION.CONTRACT",
            f"plugin '{selection.id}' conflicts with descriptor fields: {mismatches}",
            selection.id,
        )


def _implementation_for_target(
    descriptor: PluginDescriptor,
    *,
    target: str,
) -> ImplementationDescriptor:
    selected = [
        item for item in descriptor.implementations if target in item.targets
    ]
    if len(selected) != 1:
        raise PluginSelectionError(
            "PLUGIN.SELECTION.TARGET",
            f"plugin '{descriptor.id}' has no unique implementation for '{target}'",
            descriptor.id,
        )
    return selected[0]


def _validate_plugin_config(
    value: object,
    schema: Mapping[str, Any],
    *,
    plugin_id: str,
) -> None:
    if not schema:
        return

    def fail(path: str, message: str) -> None:
        raise PluginSelectionError(
            "PLUGIN.SELECTION.CONFIG_SCHEMA",
            f"plugin '{plugin_id}' config{path} {message}",
            plugin_id,
        )

    def matches_type(item: object, expected: str) -> bool:
        return {
            "object": isinstance(item, Mapping),
            "array": isinstance(item, (tuple, list)),
            "string": isinstance(item, str),
            "number": isinstance(item, (int, float))
            and not isinstance(item, bool),
            "integer": isinstance(item, int) and not isinstance(item, bool),
            "boolean": isinstance(item, bool),
            "null": item is None,
        }.get(expected, False)

    def visit(item: object, rule: object, path: str) -> None:
        if not isinstance(rule, Mapping):
            fail(path, "uses a non-object schema")
        expected = rule.get("type")
        expected_types = (
            (expected,)
            if isinstance(expected, str)
            else tuple(expected)
            if isinstance(expected, (tuple, list))
            else ()
        )
        if expected_types and not any(
            isinstance(kind, str) and matches_type(item, kind)
            for kind in expected_types
        ):
            fail(path, f"must have type {list(expected_types)!r}")
        if "const" in rule and item != rule["const"]:
            fail(path, "does not match const")
        enum = rule.get("enum")
        if isinstance(enum, (tuple, list)) and item not in enum:
            fail(path, "is not one of the allowed enum values")
        if isinstance(item, Mapping):
            properties = rule.get("properties", {})
            if properties is not None and not isinstance(properties, Mapping):
                fail(path, "uses invalid schema properties")
            required = rule.get("required", ())
            if required is not None and not isinstance(required, (tuple, list)):
                fail(path, "uses an invalid required list")
            for key in required or ():
                if not isinstance(key, str) or key not in item:
                    fail(path, f"is missing required property {key!r}")
            for key, child in item.items():
                child_path = f"{path}.{key}" if path else f".{key}"
                if key in (properties or {}):
                    visit(child, properties[key], child_path)
                elif rule.get("additionalProperties") is False:
                    fail(child_path, "is not allowed")
                elif isinstance(rule.get("additionalProperties"), Mapping):
                    visit(child, rule["additionalProperties"], child_path)
        if isinstance(item, (tuple, list)):
            minimum = rule.get("minItems")
            maximum = rule.get("maxItems")
            if isinstance(minimum, int) and len(item) < minimum:
                fail(path, f"must contain at least {minimum} items")
            if isinstance(maximum, int) and len(item) > maximum:
                fail(path, f"must contain at most {maximum} items")
            child_rule = rule.get("items")
            if isinstance(child_rule, Mapping):
                for index, child in enumerate(item):
                    visit(child, child_rule, f"{path}[{index}]")
        if isinstance(item, str):
            minimum = rule.get("minLength")
            maximum = rule.get("maxLength")
            if isinstance(minimum, int) and len(item) < minimum:
                fail(path, f"must contain at least {minimum} characters")
            if isinstance(maximum, int) and len(item) > maximum:
                fail(path, f"must contain at most {maximum} characters")
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            minimum = rule.get("minimum")
            maximum = rule.get("maximum")
            if isinstance(minimum, (int, float)) and item < minimum:
                fail(path, f"must be at least {minimum}")
            if isinstance(maximum, (int, float)) and item > maximum:
                fail(path, f"must be at most {maximum}")

    visit(value, schema, "")


def _effective_priority(
    selection: PluginSelection,
    catalog: PluginCatalog,
) -> int:
    if selection.priority is not None:
        return selection.priority
    descriptor = catalog.get(selection.id)
    return descriptor.priority if descriptor is not None else 100


__all__ = [
    "PluginResolution",
    "PluginSelection",
    "PluginSelectionError",
    "ResolvedPluginSelection",
    "resolve_plugin_selections",
]
