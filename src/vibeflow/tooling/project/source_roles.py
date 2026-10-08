"""Assemble explicit resource membership separately for each selected workflow."""

from pathlib import Path

from vibeflow.core.descriptors.source_bundle import implementation_sources, ownership_resources


_GROUPS = {"node": "nodes", "base_lib": "base_libs", "plugin": "plugins",
           "host_extension": "host_extensions", "rule": "rules"}


def resource_structure_scopes(catalogs, root, *, language, resolve_module=None):
    root = Path(root).resolve()
    scopes = []
    for index, catalog in enumerate(catalogs):
        owners = []
        for kind, descriptor in ownership_resources(catalog):
            origin = catalog.origins.get((_GROUPS.get(kind), descriptor.id))
            plugin_id = origin.plugin_id if origin else descriptor.id if kind == "plugin_declaration" else ""
            for implementation in descriptor.implementations:
                family = "javascript" if implementation.language == "typescript" else implementation.language
                if family != language:
                    continue
                for role, locator in implementation_sources(implementation):
                    path = _source_path(locator, root, catalog.source_roots, resolve_module)
                    if path is None or not path.is_relative_to(root):
                        continue
                    owners.append({"path": path.relative_to(root).as_posix(), "id": descriptor.id,
                        "kind": kind, "role": "declaration" if kind == "plugin_declaration" else role,
                        "symbol": (locator.export or ("run" if kind == "node" and language == "javascript" else "")) if role == "entry" else "",
                        "base_libs": list(getattr(descriptor, "base_libs", ())),
                        "dependencies": list(getattr(descriptor, "dependencies", ())), "plugin_id": plugin_id})
        scopes.append({"id": str(index), "owners": owners})
    return tuple(scopes)


def _source_path(locator, root, roots, resolve_module):
    if locator.kind == "file":
        return (root / locator.ref).resolve()
    if locator.kind == "module" and resolve_module:
        return next((path for base in dict.fromkeys((root, *map(Path, roots)))
            if (path := resolve_module(locator.ref, base)) is not None), None)
    return None

