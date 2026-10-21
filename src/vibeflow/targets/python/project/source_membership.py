"""Resolve explicit source membership without granting permissions to references."""
from pathlib import Path

from vibeflow.core.descriptors.source_bundle import implementation_sources, ownership_resources
from vibeflow.targets.python.project.source_closure import resolve_local_module_path


def resource_paths(descriptor, root, roots):
    for implementation in descriptor.implementations:
        if implementation.language != "python":
            continue
        for role, locator in implementation_sources(implementation):
            path = (Path(root) / locator.ref).resolve() if locator.kind == "file" else next(
                (found for owner in dict.fromkeys((Path(root), *map(Path, roots)))
                 if (found := resolve_local_module_path(locator.ref, project_root=owner)) is not None), None)
            if path is not None:
                yield role, path, locator.export or ""


def source_ownership(registry):
    if not hasattr(registry, "prepared_resources"):
        return {}
    catalogs = registry.prepared_resources.catalogs
    owners = []
    roots = getattr(registry, "source_roots", ())
    for kind, descriptor in ownership_resources(catalogs):
        group = {"node":"nodes", "base_lib":"base_libs", "plugin":"plugins", "rule":"rules"}.get(kind)
        origin = catalogs.origins.get((group, descriptor.id))
        package_id = origin.owner.plugin_id if origin else descriptor.id if kind == "plugin_declaration" else ""
        package = next((record.get("package_path", "") for record in catalogs.plugin_records if record.get("id") == package_id), "")
        root = getattr(registry, "resource_roots", {}).get((group, descriptor.id))
        if root is None:
            record = next((item for item in catalogs.plugin_records if item.get("id") == descriptor.id), {})
            root = next((value for value,key in getattr(registry,"source_root_ids",{}).items() if key == record.get("root")), None)
        if root is None:
            continue
        base = getattr(root, "path", root)
        for role, path, symbol in resource_paths(descriptor, base, roots):
            owners.append({"path":str(path), "id":descriptor.id, "kind":kind, "role":role, "symbol":symbol,
                           "plugin_id":package_id, "package_path":package,
                           "base_libs":list(getattr(descriptor,"base_libs",())),
                           "dependencies":list(getattr(descriptor,"dependencies",()))})
            if kind == "rule":
                origin = catalogs.origins.get(("rules",descriptor.id))
                if origin is not None:
                    record = next((item for item in catalogs.plugin_records if item.get("id") == origin.owner.plugin_id), {})
                    libraries = record.get("declaration", {}).get("base_libs", ())
                    owners.append({"path":str(path),"id":origin.owner.plugin_id,"kind":"plugin_declaration",
                        "role":"declaration","symbol":symbol,"base_libs":list(libraries),"dependencies":[],
                        "plugin_id":package_id,"package_path":package})
    # Unused business definitions still own their implementation symbols. Their
    # identities prevent direct calls without activating their types or rules.
    existing = {(item["kind"],item["id"],item["role"],item["path"]) for item in owners}
    for entry in registry.prepared_resources.resource_inventory:
        descriptor = entry.descriptor
        from vibeflow.core.descriptors.models import NodeDescriptor
        if not isinstance(descriptor, NodeDescriptor):
            continue
        for role,path,symbol in resource_paths(descriptor, entry.origin.owner.path, roots):
            if ("node",descriptor.id,role,str(path)) not in existing:
                owners.append({"path":str(path),"id":descriptor.id,"kind":"node","role":role,"symbol":symbol,
                    "plugin_id":"","package_path":"","base_libs":list(descriptor.base_libs),"dependencies":[]})
    return {"source_owners":tuple(owners)}


def subject_files(context):
    sources = context.require("source_context")
    resource_id = context.subject.get("definition_id", context.subject.get("id", ""))
    kind = context.subject.get("kind", "node")
    entries = [item["path"] for item in context.facts.get("source_owners", ())
               if item["kind"] == kind and item["id"] == resource_id]
    if not entries:
        source = context.facts.get("resource_source_file") or context.facts.get("base_lib_file")
        node = next((item for item in sources.nodes if item.definition_id == resource_id), None)
        entries = [source.path] if source else [node.path] if node else []
    files = {file.path:file for path in entries for file in sources.import_closure(path)}
    return tuple(files.values()) if entries else sources.files


def implementation_review_files(context):
    """Lifecycle/package health does not absorb contributed implementations."""
    closure = subject_files(context)
    kind = context.subject.get("kind")
    if kind not in {"plugin", "plugin_declaration"}:
        return closure
    owners = context.facts.get("source_owners", ())
    resource_id = context.subject.get("id")
    descriptor = context.subject.get("descriptor", {})
    libraries = descriptor.get("base_libs", ()) if hasattr(descriptor,"get") else getattr(descriptor,"base_libs", ())
    def selected(file):
        claims = [item for item in owners if item["path"] == file.path]
        return not claims or any(item["kind"] == kind and item["id"] == resource_id
            or item["kind"] == "base_lib" and item["id"] in libraries for item in claims)
    return tuple(file for file in closure if selected(file))
