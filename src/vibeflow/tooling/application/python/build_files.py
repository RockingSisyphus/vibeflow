"""Collect project implementations and package resources for Python AOT."""
from pathlib import Path

_EXCLUDED = {'.git', '.venv', 'node_modules', 'runs', 'build', 'dist', '__pycache__', 'vibeflow-preview', 'vibeflow-preview.config.js'}


def python_bundle_files(workspace, registry, config, inputs, *, out_dir, include):
    workflow_root = workspace.root_for_path(config)
    roots = (workflow_root.path.resolve(), workspace.root.resolve())
    files = {Path(config).resolve(), *(path for path in inputs.files if path.is_relative_to(workspace.root))}
    # Imported private libraries are not members of the workflow's visible
    # catalog. Read declarations only in its checked dependency files, without
    # activating unrelated resources from the foreign root.
    from vibeflow.targets.python.sdk.discovery import discover_file_resources
    from vibeflow.targets.python.sdk.source_namespace import source_namespace
    from vibeflow.targets.python.sdk.loading import source_paths
    from vibeflow.tooling.application.python.project.declarations import _implementation_path
    namespace = source_namespace(workspace.root, namespaces=registry.source_namespaces)
    with source_paths(roots):
        for path in sorted(files):
            owner = workspace.root_for_path(path)
            if owner is None or owner == workflow_root or path.suffix != ".py":
                continue
            for resource in discover_file_resources(path, namespace):
                for implementation in getattr(resource.descriptor, "implementations", ()):
                    for source in getattr(implementation, "implementation_files", ()) if implementation.language == "python" else ():
                        files.add(_implementation_path(source.kind, source.ref, owner.path, roots))
    # Packages carry adjacent resources. Root-level data and dynamic imports
    # outside the source roots are explicit --include choices.
    packages = set()
    for source in tuple(files):
        package = source.parent
        while (package / '__init__.py').is_file():
            # The root boundary prevents collecting unrelated environment data.
            if package not in roots and any(package.is_relative_to(root) for root in roots):
                packages.add(package)
            if package in roots:
                break
            package = package.parent
    for package in packages:
        files.update(path for path in package.rglob('*') if path.is_file() and not path.is_relative_to(out_dir)
            and not any(part in _EXCLUDED for part in path.relative_to(package).parts)
            and path.suffix not in {'.py', '.pyc', '.pyo'})
    files.update(package / '__init__.py' for package in packages)
    for entry in include:
        path = (workflow_root.path / entry).resolve()
        if not path.exists():
            raise ValueError(f'--include does not exist: {entry}')
        files.update(item for item in path.rglob('*') if item.is_file() and not item.is_relative_to(out_dir)
            and not any(part in _EXCLUDED for part in item.relative_to(path).parts)
            and item.suffix != '.pyc') if path.is_dir() else files.add(path)
    return tuple(sorted(files))


def copy_python_framework(destination):
    """Read the installed package through resources, including zip distributions."""
    from importlib.resources import files
    copy_package_resources(files('vibeflow'), destination)


def copy_package_resources(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name == '__pycache__' or item.name.endswith(('.pyc','.pyo')):
            continue
        if item.is_dir():
            copy_package_resources(item, target / item.name)
        else:
            (target / item.name).write_bytes(item.read_bytes())
