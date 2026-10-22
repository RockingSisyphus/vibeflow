"""Source members of catalog declarations, independent of resource-use policy."""
from vibeflow.core.descriptors.contributions import RESOURCE_GROUPS, resource_kind
from vibeflow.core.descriptors.source_bundle import ownership_resources, implementation_sources


def source_owners(prepared):
    """Attribute source symbols independently of selection or permission."""
    catalogs = prepared.catalogs
    declarations = list(ownership_resources(catalogs))
    known = {(kind, descriptor.id) for kind, descriptor in declarations}
    declarations.extend((resource_kind(entry.descriptor), entry.descriptor) for entry in prepared.resource_inventory
                        if (resource_kind(entry.descriptor), entry.descriptor.id) not in known)
    owners = []
    for kind, descriptor in declarations:
        origin = catalogs.origins.get((RESOURCE_GROUPS.get(kind), descriptor.id))
        package_id = origin.owner.plugin_id if origin else descriptor.id if kind == "plugin_declaration" else ""
        package = next((item["package_path"] for item in prepared.records if item.get("id") == package_id and item.get("loaded")), "")
        for implementation in getattr(descriptor, "implementations", ()):
            for role, locator in implementation_sources(implementation):
                if locator.kind != "file":
                    continue
                owners.append({"kind": kind, "id": descriptor.id, "path": locator.ref,
                    "symbol": locator.export or "", "role": role, "plugin_id": package_id, "package_path": package,
                    "base_libs": tuple(getattr(descriptor, "base_libs", ())),
                    "dependencies": tuple(getattr(descriptor, "dependencies", ())),
                    "selected": (kind, descriptor.id) in known})
    return tuple(owners)
