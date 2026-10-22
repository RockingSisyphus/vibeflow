"""Resolved resource and import facts for replaceable governance Rules."""
from pathlib import Path

from vibeflow.core.descriptors.contributions import resource_kind


def implementation_paths(descriptor):
    return tuple(str(Path(source.ref).resolve())
        for implementation in getattr(descriptor, "implementations", ())
        for source in (implementation.source, *getattr(implementation, "implementation_files", ()))
        if source.kind == "file")


def package_facts(contribution, *, owner, package_path, source_kind, source_paths, project_path, owner_scope):
    resources = tuple({"id": entry.descriptor.id, "kind": resource_kind(entry.descriptor),
        "path": str(Path(entry.origin.path).resolve()), "implementation_paths": implementation_paths(entry.descriptor)}
        for entry in contribution.resources)
    return {"id": contribution.id, "path": str(Path(package_path).resolve()), "source": contribution.source,
        "source_kind": source_kind, "scope": owner_scope, "owner_path": str(owner.path), "owner_id": owner.id,
        "project_path": str(project_path), "resources": resources,
        "source_paths": tuple(str(Path(path).resolve()) for path in source_paths
            if not (Path(path).name == "__init__.py" and Path(path).is_file() and not Path(path).read_text().strip()))}


def dependency_fact(workspace, source, target, *, kind, **details):
    source, target = Path(source).resolve(), Path(target).resolve()
    source_root, target_root = workspace.root_for_path(source), workspace.root_for_path(target)
    return {"path": str(source), "imported_path": str(target), "kind": kind,
        "source_root": getattr(source_root, "id", ""), "root": getattr(target_root, "id", ""),
        "shared": source_root is None, "in_project": target.is_relative_to(workspace.root), **details}


def governance_resource_facts(workspace, workflows, governance, resources, *, root=None, includes=()):
    selected = [value for path, value in workflows.items()
                if root is None or workspace.root_for_path(path) == root]
    selected.extend(value for owner, _, value in governance if owner == root)
    packages = tuple({(package["owner_id"], package["source"]): package
        for value in selected for package in value.packages
        if package["scope"] == ("root" if root else "project")
        and (root is None or package["owner_id"] == root.id)}.values())
    nodesets = tuple(item for value in selected if value.document is not None
                     for item in value.document.nodeset_imports)
    dependencies = [dependency_fact(workspace, item["importer"], item["path"], kind="nodeset",
                                   field=item["field"]) for item in nodesets]
    for resource in resources:
        if root is not None and resource["owner"]["kind"] == "project":
            continue
        dependencies.extend(dependency_fact(workspace, resource["path"], path, kind="implementation")
                            for path in resource.get("implementation_paths", ()))
    for package in packages:
        dependencies.append(dependency_fact(workspace, Path(package["owner_path"])/"root_rules.jsonc",
                            package["source"], kind="plugin"))
    if root is not None:
        if root.project_target == "javascript":
            package_root = root.project_config.get("javascript", {}).get("package_root", ".")
            dependencies.append(dependency_fact(workspace, root.config_path,
                root.path / package_root, kind="package_root"))
        dependencies.extend(dependency_fact(workspace, root.path/"root_rules.jsonc", root.path/path, kind="include")
                            for path in includes)
    plugin_directories = tuple(str(path / "plugins") for path in (workspace.root, *(owner.path for owner in workspace.roots)))
    return {"plugin_directories": plugin_directories, "packages": packages, "nodeset_imports": nodesets, "resource_dependencies": tuple(dependencies)}
