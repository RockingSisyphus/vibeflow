"""Resource ownership supplied to root source Rules, using prepared declarations."""
from pathlib import Path
from os.path import relpath

from vibeflow.core.descriptors.source_bundle import ownership_resources, implementation_sources


def private_root_imports(workspace, root, imports):
    """Attribute Target-resolved import edges; policy stays in the root Rule."""
    result = {}
    for source, target, line in imports:
        owner = workspace.root_for_path(target)
        shared = workspace.root_for_path(source) is None
        if owner is not None and (owner.id != root.id or shared):
            key = (str(source), str(target), line)
            result[key] = {"path":str(source), "imported_path":str(target), "root":owner.id, "line":line, "shared":shared}
    return tuple(result[key] for key in sorted(result))


def root_resource_scopes(workspace, root, workflows, files):
    """One scope per workflow; permissions never leak between its selections."""
    scopes = []
    for path, prepared in workflows.items():
        if workspace.root_for_path(path).id != root.id:
            continue
        catalogs, owners = prepared.catalogs, []
        declarations = list(ownership_resources(catalogs))
        declared = {(kind, descriptor.id) for kind, descriptor in declarations}
        from vibeflow.core.descriptors.contributions import resource_kind
        declarations.extend((resource_kind(entry.descriptor), entry.descriptor)
            for entry in prepared.resource_inventory
            if (resource_kind(entry.descriptor), entry.descriptor.id) not in declared)
        for kind, descriptor in declarations:
            group = {"node":"nodes", "base_lib":"base_libs", "plugin":"plugins", "rule":"rules"}.get(kind)
            origin = catalogs.origins.get((group, descriptor.id))
            package_id = origin.owner.plugin_id if origin else descriptor.id if kind == "plugin_declaration" else ""
            for implementation in getattr(descriptor, "implementations", ()):
                for role, locator in implementation_sources(implementation):
                    if locator.kind != "file" or not Path(locator.ref).is_relative_to(root.path):
                        continue
                    owners.append({"path":Path(relpath(locator.ref, root.path)).as_posix(),
                        "kind":kind,"id":descriptor.id,"role":role,"symbol":locator.export,"selected":(kind,descriptor.id) in declared,
                        "plugin_id":package_id,"base_libs":tuple(getattr(descriptor,"base_libs",())),
                        "dependencies":tuple(getattr(descriptor,"dependencies",()))})
        # Package-private source is owned by its Plugin without a second list of
        # installable components. Independent Node/BaseLib support stays explicit.
        for record in prepared.records:
            if not record.get("loaded"):
                continue
            package = Path(record["package_path"])
            for file in files:
                if (root.path / file.path).is_relative_to(package):
                    owners.append({"path":file.path,"kind":"plugin_declaration","id":record["id"],
                        "plugin_id":record["id"],"role":"support","symbol":"","base_libs":(),"dependencies":()})
        scopes.append({"id":str(path),"owners":owners})
    return tuple(scopes)
