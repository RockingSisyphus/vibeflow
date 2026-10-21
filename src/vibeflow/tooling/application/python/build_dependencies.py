"""Collect selected implementation packages without importing delayed bindings.

Ordinary imported libraries remain environment dependencies. Package resources
are read through their import locations, not by executing implementation bodies.
"""
import importlib.resources
import importlib.util
from importlib.resources.readers import MultiplexedPath
from pathlib import Path
from vibeflow.targets.python.project.source_closure import resolve_local_module_path
import sys


def implementation_packages(registry, used, *, roots, framework):
    modules, files = {}, set()
    for key in used:
        direct = registry.direct_bindings.get(('node', key))
        if direct is not None:
            modules[direct.__module__] = None
        else:
            path = registry.source_locations[key][0]
            source = registry.descriptor(key).implementations[0].source
            if source.kind in {'module', 'package'}:
                modules[source.ref] = path
            else:
                files.add(path)
    for (kind, _), value in registry.direct_bindings.items():
        if kind in {'plugin', 'base_lib'} and hasattr(value, '__module__'):
            modules[value.__module__] = None
    for group in ('plugins', 'base_libs'):
        for descriptor in getattr(registry.prepared_resources.catalogs, group):
            if group == 'plugins' and descriptor.plugin_type != 'runtime':
                continue
            for implementation in descriptor.implementations:
                source = implementation.source
                if source.kind in {'module', 'package'}:
                    modules.setdefault(source.ref, None)
                elif source.kind == 'file':
                    owner = registry.resource_roots[(group, descriptor.id)]
                    files.add((owner.path / source.ref).resolve())
    for record in registry.prepared_resources.records:
        source = record['source']
        if source['kind'] in {'module', 'package'}:
            modules.setdefault(source['ref'], None)
    prefixes, resources = {}, []

    def external(path):
        return not any(path.is_relative_to(root) for root in (*roots, framework))

    def add(origin, resource, package_paths, relative, loader=None):
        for prefix in package_paths:
            prefixes[prefix] = '_dependencies'
        if not any(item[0] == origin for item in resources):
            resources.append((origin, resource, Path('_dependencies') / relative, loader))

    for name, hint in sorted(modules.items()):
        module = sys.modules.get(name)
        local = next((path for root in roots
                      if (path := resolve_local_module_path(name, project_root=root)) is not None), None)
        filename = hint or local or getattr(module, '__file__', None)
        specification = None if filename else importlib.util.find_spec(name)
        filename = filename or getattr(specification, 'origin', None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if not external(path):
            continue
        top_name = (getattr(module, '__package__', '') or name).split('.')[0]
        top = sys.modules.get(top_name)
        top_spec = getattr(top, '__spec__', None) if top is not None else importlib.util.find_spec(top_name)
        locations = tuple(getattr(top, '__path__', ()) or getattr(top_spec, 'submodule_search_locations', ()) or ())
        if locations:
            origins = tuple(Path(value).resolve() for value in locations)
            resource = importlib.resources.files(top) if top is not None and top_spec is not None else (
                MultiplexedPath(*origins) if len(origins) > 1 else origins[0])
            add(origins[0], resource, tuple(value.parent for value in origins), Path(top_name))
        else:
            loader = getattr(module, '__loader__', None) or getattr(specification, 'loader', None)
            add(path, None, (path.parent,), Path(path.name), loader)
    for path in sorted(files):
        path = Path(path).resolve()
        if not external(path):
            continue
        package, outer = path.parent, None
        while (package / '__init__.py').is_file():
            outer, package = package, package.parent
        if outer is not None:
            add(outer, outer, (outer.parent,), Path(outer.name))
        else:
            add(path, None, (path.parent,), Path(path.name))
    return tuple(prefixes.items()), tuple(resources)


def copy_implementation_packages(resources, staging):
    from vibeflow.tooling.application.python.build_files import copy_package_resources
    for origin, resource, relative, loader in resources:
        target = staging / relative
        if resource is not None:
            copy_package_resources(resource, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(origin.read_bytes() if origin.is_file() else loader.get_data(str(origin)))
