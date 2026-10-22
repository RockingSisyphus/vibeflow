"""Portable resource-use results; policy and discovery belong to their callers."""
from dataclasses import dataclass
from collections.abc import Mapping

from vibeflow.core.descriptors.json_values import freeze_json, thaw_json


RESOURCE_USE_TYPE = "vibeflow.resource_use.v1"
RESOURCE_SET_TYPE = "vibeflow.resource_set.v1"


@dataclass(frozen=True)
class ResourceUse:
    workflow: str
    resources: tuple | None = None
    planned: tuple = ()
    annotations: tuple = ()

    def __post_init__(self):
        if not isinstance(self.workflow, str) or not self.workflow:
            raise ValueError("resource use requires a workflow identity")
        if self.resources is not None:
            seen = set()
            for item in self.resources:
                if not isinstance(item, Mapping) or not all(isinstance(item.get(key), str) and item[key] for key in ("kind", "id", "reason")):
                    raise ValueError("resource use members require kind, id and reason")
                key = (item["kind"], item["id"])
                if key in seen:
                    raise ValueError(f"duplicate resource use member: {key}")
                seen.add(key)
            object.__setattr__(self, "resources", freeze_json(sorted(self.resources, key=lambda item:(item["kind"],item["id"]))))
        for name in ("planned", "annotations"):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or any(not isinstance(item, Mapping)
                    or not all(isinstance(item.get(key), str) and item[key] for key in ("kind", "id")) for item in values):
                raise ValueError(f"resource use {name} requires members with kind and id")
            object.__setattr__(self, name, freeze_json(values))

    def allows(self, kind, identifier):
        return self.resources is None or any(item["kind"] == kind and item["id"] == identifier for item in self.resources)

    def selection(self, kind, identifier):
        return next((thaw_json(item.get("selection", {})) for item in (*(self.resources or ()), *self.annotations)
                     if item["kind"] == kind and item["id"] == identifier), {})

    def to_dict(self):
        return {"workflow": self.workflow, "resources": thaw_json(self.resources), "planned": thaw_json(self.planned), "annotations": thaw_json(self.annotations)}


def dependency_order(identifiers, dependencies):
    """Order a declared dependency graph without granting access to its vertices."""
    ordered, complete, active = [], set(), []

    def visit(identifier):
        if identifier in complete:
            return
        if identifier in active:
            raise ValueError("resource dependency cycle: " + " -> ".join((*active[active.index(identifier):], identifier)))
        active.append(identifier)
        for dependency in dependencies(identifier):
            visit(dependency)
        active.pop()
        complete.add(identifier)
        ordered.append(identifier)

    for identifier in identifiers:
        visit(identifier)
    return tuple(ordered)


def required_base_libs(catalogs, *, node_ids, plugin_ids=()):
    """Read dependency reachability; membership is decided by resource-use Rules."""
    from vibeflow.core.descriptors.source_bundle import source_resources
    roots = []
    for kind, descriptor in source_resources(catalogs):
        if kind == "node" and descriptor.id in node_ids or kind == "plugin" and descriptor.id in plugin_ids or kind == "plugin_declaration":
            roots.extend(descriptor.base_libs)
    def dependencies(identifier):
        descriptor = catalogs.base_libs.get(identifier)
        if descriptor is None:
            raise ValueError(f"unknown required BaseLib '{identifier}'")
        return descriptor.dependencies
    return dependency_order(roots, dependencies)
