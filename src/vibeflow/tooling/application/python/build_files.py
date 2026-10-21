"""Collect project implementations and package resources for Python AOT."""
from pathlib import Path

_EXCLUDED = {'.git', '.venv', 'node_modules', 'runs', 'build', 'dist', '__pycache__', 'vibeflow-preview', 'vibeflow-preview.config.js'}


def python_bundle_files(workspace, registry, config, *, out_dir, include):
    owner = workspace.root_for_path(config)
    roots = (owner.path.resolve(), workspace.root.resolve())
    shared = tuple(workspace.root / name for name in ('nodes', 'base_lib', 'plugins'))

    def eligible(path):
        owner = next((root for root in roots if path.is_relative_to(root)), None)
        visible = path.is_relative_to(roots[0]) or any(path.is_relative_to(group) for group in shared)
        return owner is not None and visible and not path.is_relative_to(out_dir) and not any(
            part in _EXCLUDED for part in path.relative_to(owner).parts) and path.suffix != '.pyc'

    files = {Path(config).resolve()}
    for root in (roots[0], *shared):
        files.update(path for path in root.rglob('*.py') if path.is_file() and eligible(path))
    # Explicit declaration support files may include data as well as code.
    loaded = registry.prepared_resources
    from vibeflow.tooling.application.python.project.declarations import _implementation_path
    for group in ('nodes', 'base_libs', 'plugins'):
        for descriptor in getattr(loaded.catalogs, group).available():
            descriptor = getattr(loaded.catalogs, group).require(descriptor)
            owner = registry.resource_roots.get((group, descriptor.id))
            if owner is None:
                continue
            for implementation in descriptor.implementations:
                for source in implementation.implementation_files:
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
        files.update(path for path in package.rglob('*') if path.is_file() and eligible(path))
    for entry in include:
        path = (owner.path / entry).resolve()
        if not (path.is_relative_to(owner.path) or any(path.is_relative_to(group) for group in shared)):
            raise ValueError(f'--include must belong to this root or project shared resources: {entry}')
        if not path.exists():
            raise ValueError(f'--include does not exist: {entry}')
        files.update(item for item in path.rglob('*') if item.is_file() and eligible(item)) if path.is_dir() else files.add(path)
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
