"""Resolve explicit source membership without granting permissions to references."""
from pathlib import Path

from vibeflow.core.descriptors.source_bundle import implementation_sources
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
    from vibeflow.core.descriptors.source_members import source_owners
    return {"source_owners": source_owners(registry.prepared_resources)}


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
