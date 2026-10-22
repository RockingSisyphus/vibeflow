"""Project implementation inputs reached by the checked Python build.

Resource-use Rules decide availability. This projection only follows executable
calls, selected plugin declarations/lifecycles and declared library dependencies.
Both local source copying and external package copying consume these same inputs.
"""
from dataclasses import dataclass
from pathlib import Path

from vibeflow.core.descriptors.resource_use import required_base_libs
from vibeflow.core.descriptors.source_bundle import declaration_descriptor
from vibeflow.targets.python.project.source_membership import resource_paths


@dataclass(frozen=True)
class PythonBuildInputs:
    files: tuple[Path, ...]
    modules: tuple[tuple[str, None], ...]


def python_build_inputs(registry, used, resource_use, native_plan):
    from vibeflow.targets.python.project.check_session import current_python_check
    from vibeflow.targets.python.project.source_closure import collect_python_source_facts
    loaded = registry.prepared_resources
    catalogs = loaded.catalogs
    roots = registry.source_roots
    session = current_python_check(registry)
    files, modules, facts = set(), {}, {}

    def source(path, root):
        path = Path(path).resolve()
        files.add(path)
        if path.suffix == ".py":
            for fact in collect_python_source_facts(path, project_root=root, source_roots=roots,
                    _facts=facts, _parsed=session.parsed_sources if session else None,
                    _parse_cache=session.parse_cache if session else None):
                if fact.load_error:
                    raise ValueError(fact.load_error)
                files.add(Path(fact.path))

    def implementation(kind, descriptor, root):
        direct = registry.direct_bindings.get((kind, descriptor.id))
        if direct is not None and hasattr(direct, "__module__"):
            modules[direct.__module__] = None
        for item in descriptor.implementations:
            if item.language == "python" and item.source.kind in {"module", "package"}:
                modules.setdefault(item.source.ref, None)
        for _, path, _ in resource_paths(descriptor, root, roots):
            source(path, root)

    runtime = tuple(catalogs.plugins.require(selection["id"])
        for selection in loaded.lifecycle_selections if selection.get("status") != "planned"
        and resource_use.allows("plugin", selection["id"])
        and catalogs.plugins.require(selection["id"]).plugin_type == "runtime")
    libraries = required_base_libs(catalogs, node_ids=used, plugin_ids={item.id for item in runtime})
    for kind, group, descriptors in (
            ("node", "nodes", (registry.descriptor(key) for key in sorted(used))),
            ("base_lib", "base_libs", (catalogs.base_libs.require(key) for key in libraries)),
            ("plugin", "plugins", runtime)):
        for descriptor in descriptors:
            implementation(kind, descriptor, registry.resource_roots[(group, descriptor.id)].path)
    # Plugin entry declarations retain their imports and package data. Merely
    # contributing a lazy implementation does not make that implementation an input.
    for record in loaded.records:
        if not record.get("loaded") or not record.get("declaration"):
            continue
        descriptor = declaration_descriptor(record["declaration"])
        implementation("plugin_declaration", descriptor, Path(record["package_path"]))
        locator = record["source"]
        if locator["kind"] in {"module", "package"}:
            modules.setdefault(locator["ref"], None)
    # Imports may reach other members of a plugin without naming a BaseLib ID.
    # Attach support files only once their implementation entry is actually reached.
    pending = list(catalogs.base_libs)
    while pending:
        reached = [item for item in pending if any(path in files for role, path, _ in
            resource_paths(item, registry.resource_roots[("base_libs", item.id)].path, roots) if role == "entry")]
        if not reached:
            break
        for descriptor in reached:
            pending.remove(descriptor)
            implementation("base_lib", descriptor, registry.resource_roots[("base_libs", descriptor.id)].path)
    stack = [native_plan]
    while stack:
        for frame in stack.pop().frames.values():
            if frame.planned_stub_path:
                source(frame.planned_stub_path, roots[0])
            if frame.subplan is not None:
                stack.append(frame.subplan)
    return PythonBuildInputs(tuple(sorted(files)), tuple(sorted(modules.items())))
