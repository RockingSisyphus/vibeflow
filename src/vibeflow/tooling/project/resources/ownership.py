"""Resolve ownership and NodeType defaults before Target binding and compilation."""

from dataclasses import dataclass, replace
from pathlib import Path

from vibeflow.core.descriptors.contributions import ResourceDeclaration, ResourceOrigin, resource_kind
from vibeflow.core.descriptors.ownership import ResourceOwner
from vibeflow.core.descriptors.node_types import resolve_node_type


@dataclass(frozen=True)
class ResourceScope:
    id: str
    path: Path
    project_target: str
    project_config: object
    toolchain_root: Path | None = None


def selected_plugin_scope(workspace, root, selection):
    scope = selection.get("scope", "root")
    if root.project_target == "project" and scope != "project":
        raise ValueError("project governance can only select project Plugins")
    if scope not in {"root", "project"}:
        raise ValueError("plugin scope must be root or project; other roots' private Plugins are unavailable")
    path = workspace.root if scope == "project" else root.path
    source = selection.get("source", {})
    suffix = Path(source.get("ref", "")).suffix
    language = selection.get("language") or ("python" if suffix == ".py" or root.project_target == "project" and not suffix else
        "javascript" if suffix in {".ts", ".js", ".mjs", ".mts"} else root.project_target)
    if language not in {"python", "javascript"}:
        raise ValueError("plugin declaration language must be python or javascript")
    return ResourceScope("project" if scope == "project" else root.id, path, language, root.project_config, root.path)


def visible_source_roots(workspace, root):
    return (root.path, workspace.root)


def standalone_resources(workspace, root, contributions, *, node_ids, node_command="node", discovery_cache=None, syntax_cache=None, loading_context=None):
    types = {entry.descriptor.id: entry.descriptor for contribution in contributions
             for entry in contribution.resources if resource_kind(entry.descriptor) == "node_type"}
    found, bindings, inventory, states = [], {}, [], {}
    for kind, identifier, directory in (("project", "project", workspace.root), ("root", root.id, root.path)):
        owner = ResourceOwner(kind, identifier, root.id if kind == "root" else "", str(directory))
        key = (root.project_target, directory)
        cache = discovery_cache if discovery_cache is not None else {}
        if key not in cache:
            from vibeflow.tooling.application.project_targets import preparation_adapter
            resources = preparation_adapter(root.project_target).discover_resources(directory,
                root=root, workspace=workspace, node_command=node_command, syntax_cache=syntax_cache, loading_context=loading_context)
            cache[key] = resources
        resources = cache[key]
        states.update(resources.load_states)
        for resource in resources.resources:
            descriptor = resolve_descriptor_sources(resource.descriptor, directory)
            origin = ResourceOrigin(owner, resource.path, resource.line, symbol=resource.symbol)
            from vibeflow.tooling.application.project_targets import preparation_adapter
            descriptor = preparation_adapter(root.project_target).normalize_resource(ResourceDeclaration(descriptor,origin),
                resource.implementation, directory=directory, root=root, workspace=workspace)
            for implementation in getattr(descriptor, "implementations", ()):
                for locator in (implementation.source, *getattr(implementation, "implementation_files", ())):
                    if locator.kind != "file":
                        continue
                    path = Path(locator.ref).resolve()
                    if not path.is_relative_to(directory) or kind == "project" and any(path.is_relative_to(item.path) for item in workspace.roots):
                        raise ValueError(f"{resource.path}: {resource_kind(descriptor)} '{descriptor.id}' references code outside its owner: {path}")
            inventory.append(ResourceDeclaration(descriptor, origin))
            if resource_kind(descriptor) == "node":
                if descriptor.id not in node_ids:
                    continue
                descriptor = resolve_node_type(descriptor, types)
            found.append(ResourceDeclaration(descriptor, origin))
            if resource.implementation is not None:
                bindings[(resource_kind(descriptor), descriptor.id)] = resource.implementation
    return tuple(found), bindings, tuple(inventory), states


def referenced_definition_ids(graph):
    """Prepare definitions referenced by every declared graph, including unused types.

    NodesetType IDs stay in the candidate set so a business Node with the same
    ID reaches the compiler's existing conflict diagnostic.
    """
    from vibeflow.core.flow import LOOP_DEFINITION_IDS
    pending, seen, identifiers = [graph], set(), set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        identifiers.update(node.definition_id for node in current.nodes if node.definition_id not in LOOP_DEFINITION_IDS)
        pending.extend(definition.graph for definition in current.nodeset_types.values())
    return frozenset(identifiers)


def resolve_descriptor_sources(descriptor, directory):
    """Resolve file locators against the declared resource owner, without IO."""
    implementations = getattr(descriptor, "implementations", None)
    if implementations is None:
        return descriptor
    def locate(source):
        return replace(source, ref=str((Path(directory) / source.ref).resolve())) if source.kind == "file" else source
    values = tuple(replace(implementation, source=locate(implementation.source),
        **({"implementation_files":tuple(map(locate, implementation.implementation_files))}
           if hasattr(implementation, "implementation_files") else {})) for implementation in implementations)
    return replace(descriptor, implementations=values) if values != implementations else descriptor


def bind_plugin_owner(contribution, *, root_id, package_path):
    """Attach the actual selected package directory to every contribution."""
    owner = ResourceOwner("plugin", contribution.id, root_id, str(package_path))
    return replace(contribution, resources=tuple(replace(entry,
        origin=replace(entry.origin, owner=owner)) for entry in contribution.resources))


def check_plugin_package(contribution, *, package_path, source_paths=(), project_path=None):
    package = Path(package_path).resolve()
    for filename in source_paths:
        path = Path(filename).resolve()
        if project_path is None or not path.is_relative_to(project_path) or path.is_relative_to(package):
            continue
        relative = path.relative_to(project_path)
        if "node_modules" in relative.parts or path.name == "__init__.py" and not path.read_text().strip():
            continue
        raise ValueError(f"Plugin '{contribution.id}' imports project code outside its package: {path}")
    for resource in contribution.resources:
        if resource_kind(resource.descriptor) == "node":
            raise ValueError("Plugin.resources must not contain business Nodes; define NodeTypes and place Nodes in nodes/")
        if not Path(resource.origin.path).resolve().is_relative_to(package):
            raise ValueError(f"Plugin '{contribution.id}' contribution is outside its package: {resource.origin.path}")
        for implementation in getattr(resource.descriptor, "implementations", ()):
            for locator in (implementation.source, *getattr(implementation, "implementation_files", ())):
                if locator.kind == "file" and not Path(locator.ref).resolve().is_relative_to(package):
                    raise ValueError(f"Plugin '{contribution.id}' implementation is outside its package: {locator.ref}")
