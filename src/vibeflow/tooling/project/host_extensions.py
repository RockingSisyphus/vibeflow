from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from vibeflow.tooling.project.resource_helpers import _finding
from vibeflow.core.constants import EFFECT_SCOPE_TRUSTED
from vibeflow.core.flow import STATUS_IMPLEMENTED, STATUS_PLANNED
from vibeflow.core.findings import HealthFinding


STATUSES = frozenset({STATUS_IMPLEMENTED, STATUS_PLANNED})
CONTRACT_FIELDS = ("targets", "provides", "dependencies")


@dataclass(frozen=True)
class HostExtensionResource:
    id: str
    status: str = STATUS_IMPLEMENTED
    display_name: str = ""
    category: str = ""
    description: str = ""
    version: str = ""
    targets: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    config: Mapping[str, object] = field(default_factory=dict)
    declared_contract_fields: frozenset[str] = field(
        default_factory=frozenset,
        repr=False,
    )
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "status": self.status,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
            "targets": list(self.targets),
            "provides": list(self.provides),
            "dependencies": list(self.dependencies),
            "config_keys": sorted(self.config),
            "effect_scope": EFFECT_SCOPE_TRUSTED,
        }
        if self.root_id:
            payload["root_id"] = self.root_id
        if self.root_path:
            payload["root_path"] = self.root_path
        if self.source_path:
            payload["source_path"] = self.source_path
        return payload


def host_extension_resources(
    config: Mapping[str, Any],
    *,
    findings: list[HealthFinding],
) -> list[HostExtensionResource]:
    raw = config.get("host_extensions", [])
    if raw == []:
        return []
    if not isinstance(raw, list):
        findings.append(
            _finding(
                "CONFIG.SCHEMA.HOST_EXTENSIONS_LIST",
                "host_extensions must be a list",
                "host_extensions",
                "host_extension",
            )
        )
        return []
    resources: list[HostExtensionResource] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        resource = _parse_resource(item, index=index, findings=findings)
        if resource is None:
            continue
        if resource.id in seen:
            findings.append(
                _finding(
                    "CONFIG.SCHEMA.HOST_EXTENSION_DUPLICATE",
                    f"duplicate host_extension id: {resource.id}",
                    f"host_extensions[{index}]",
                    "host_extension",
                )
            )
            continue
        seen.add(resource.id)
        resources.append(resource)
    return resources


def _parse_resource(
    item: object,
    *,
    index: int,
    findings: list[HealthFinding],
) -> HostExtensionResource | None:
    prefix = f"host_extensions[{index}]"
    if isinstance(item, str):
        spec: Mapping[str, object] = {"id": item}
    elif isinstance(item, Mapping):
        spec = item
    else:
        findings.append(
            _finding(
                "CONFIG.SCHEMA.HOST_EXTENSION_OBJECT",
                f"{prefix} must be a string or object",
                prefix,
                "host_extension",
            )
        )
        return None
    if "enabled" in spec and not isinstance(spec["enabled"], bool):
        findings.append(
            _finding(
                "CONFIG.SCHEMA.HOST_EXTENSION_ENABLED",
                f"{prefix}.enabled must be a boolean",
                f"{prefix}.enabled",
                "host_extension",
            )
        )
        return None
    if spec.get("enabled", True) is False:
        return None
    resource_id = _resource_id(spec)
    if not resource_id:
        findings.append(
            _finding(
                "CONFIG.SCHEMA.HOST_EXTENSION_ID",
                f"{prefix}.id must be a non-empty string",
                f"{prefix}.id",
                "host_extension",
            )
        )
        return None
    status = _resource_status(spec, prefix=prefix, findings=findings)
    extension_config = _resource_config(
        spec,
        prefix=prefix,
        findings=findings,
    )
    sequences = _contract_sequences(
        spec,
        prefix=prefix,
        findings=findings,
    )
    if sequences is None:
        return None
    metadata = _resource_metadata(spec)
    return HostExtensionResource(
        id=resource_id,
        status=status,
        display_name=metadata["display_name"],
        category=metadata["category"],
        description=metadata["description"],
        version=metadata["version"],
        targets=sequences["targets"],
        provides=sequences["provides"],
        dependencies=sequences["dependencies"],
        config=extension_config,
        declared_contract_fields=frozenset(
            name for name in CONTRACT_FIELDS if name in spec
        ),
    )


def _resource_id(spec: Mapping[str, object]) -> str:
    raw_id = spec.get("id", spec.get("name", ""))
    return raw_id.strip() if isinstance(raw_id, str) else ""


def _resource_status(
    spec: Mapping[str, object],
    *,
    prefix: str,
    findings: list[HealthFinding],
) -> str:
    status = (
        str(spec.get("status", STATUS_IMPLEMENTED)).strip()
        or STATUS_IMPLEMENTED
    )
    if status in STATUSES:
        return status
    findings.append(
        _finding(
            "CONFIG.SCHEMA.RESOURCE_STATUS",
            f"{prefix}.status must be implemented or planned",
            f"{prefix}.status",
            "host_extension",
        )
    )
    return STATUS_IMPLEMENTED


def _resource_config(
    spec: Mapping[str, object],
    *,
    prefix: str,
    findings: list[HealthFinding],
) -> dict[str, object]:
    raw_config = spec.get("config", spec.get("settings", {}))
    if raw_config in (None, {}):
        return {}
    if isinstance(raw_config, Mapping):
        return {str(key): value for key, value in raw_config.items()}
    findings.append(
        _finding(
            "CONFIG.SCHEMA.HOST_EXTENSION_CONFIG",
            f"{prefix}.config/settings must be an object",
            f"{prefix}.config",
            "host_extension",
        )
    )
    return {}


def _contract_sequences(
    spec: Mapping[str, object],
    *,
    prefix: str,
    findings: list[HealthFinding],
) -> dict[str, tuple[str, ...]] | None:
    sequences: dict[str, tuple[str, ...]] = {}
    invalid = False
    for name in CONTRACT_FIELDS:
        raw = spec.get(name, ())
        if name in spec and (
            not isinstance(raw, (list, tuple))
            or any(
                not isinstance(value, str) or not value.strip()
                for value in raw
            )
        ):
            findings.append(
                _finding(
                    "CONFIG.SCHEMA.HOST_EXTENSION_STRING_LIST",
                    f"{prefix}.{name} must be a list of non-empty strings",
                    f"{prefix}.{name}",
                    "host_extension",
                )
            )
            invalid = True
        sequences[name] = _string_sequence(raw)
    return None if invalid else sequences


def resolve_host_extension_resources(
    resources: tuple[HostExtensionResource, ...],
    *,
    catalog: object,
) -> tuple[
    tuple[HostExtensionResource, ...],
    tuple[HealthFinding, ...],
]:
    resolved: list[HostExtensionResource] = []
    findings: list[HealthFinding] = []
    get_descriptor = getattr(catalog, "get", None)
    source_for = getattr(catalog, "source_for", None)
    for resource in resources:
        descriptor = (
            get_descriptor(resource.id)
            if callable(get_descriptor)
            else None
        )
        if descriptor is None:
            if resource.status == STATUS_IMPLEMENTED:
                findings.append(
                    _finding(
                        "CONFIG.RESOURCE.UNKNOWN_HOST_EXTENSION",
                        (
                            "unknown implemented host_extension resource id: "
                            f"{resource.id}"
                        ),
                        resource.id,
                        "host_extension",
                    )
                )
            resolved.append(resource)
            continue
        resolved.append(
            _resolved_resource(
                resource,
                descriptor=descriptor,
                source_for=source_for,
                findings=findings,
            )
        )
    return tuple(resolved), tuple(findings)


def _resolved_resource(
    resource: HostExtensionResource,
    *,
    descriptor: object,
    source_for: object,
    findings: list[HealthFinding],
) -> HostExtensionResource:
    contract = {
        "targets": tuple(getattr(descriptor, "targets", ()) or ()),
        "provides": tuple(getattr(descriptor, "provides", ()) or ()),
        "dependencies": tuple(
            getattr(descriptor, "dependencies", ()) or ()
        ),
    }
    for name, expected in contract.items():
        declared = tuple(getattr(resource, name))
        if (
            name in resource.declared_contract_fields
            and declared != expected
        ):
            findings.append(
                _finding(
                    "CONFIG.RESOURCE.HOST_EXTENSION_CONTRACT",
                    (
                        f"host_extension '{resource.id}' {name} "
                        "must match its registered descriptor"
                    ),
                    f"{resource.id}.{name}",
                    "host_extension",
                )
            )
    descriptor_source = (
        str(source_for(resource.id))
        if callable(source_for)
        else ""
    )
    return replace(
        resource,
        display_name=(
            resource.display_name
            or str(getattr(descriptor, "display_name", "") or "")
        ),
        description=(
            resource.description
            or str(getattr(descriptor, "description", "") or "")
        ),
        version=(
            resource.version
            or str(getattr(descriptor, "version", "") or "")
        ),
        targets=contract["targets"],
        provides=contract["provides"],
        dependencies=contract["dependencies"],
        source_path=descriptor_source or resource.source_path,
    )


def _resource_metadata(
    spec: Mapping[str, object],
) -> dict[str, str]:
    return {
        "display_name": str(spec.get("display_name", "")).strip(),
        "category": str(spec.get("category", "")).strip(),
        "description": str(spec.get("description", "")).strip(),
        "version": str(spec.get("version", "")).strip(),
    }


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        dict.fromkeys(
            item.strip()
            for item in value
            if isinstance(item, str) and item.strip()
        )
    )


__all__ = [
    "HostExtensionResource",
    "host_extension_resources",
    "resolve_host_extension_resources",
]
