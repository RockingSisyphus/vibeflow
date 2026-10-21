"""Python Application adapter for fixed plugin bootstrap."""
from vibeflow.targets.python.sdk.loading import load_plugin


def load_plugin_definition(source, *, owner, workspace, node_command, loading_context=None):
    return load_plugin(source, root=owner.path,
        source_roots=(owner.path, workspace.root), namespaces=loading_context)


def normalize_contributions(contribution, bindings, *, owner, workspace):
    from vibeflow.targets.python.sdk.identity import normalize_contributions as normalize
    return normalize(contribution, bindings, root=owner.path,
        source_roots=(owner.path, workspace.root))

def load_builtin_definition():
    from vibeflow.targets.python.rules.plugin import builtin_plugin
    return builtin_plugin()


def plugin_source_paths(definition, contribution, *, owner, workspace, package, node_command, syntax_cache=None):
    """Reuse Python's static import closure for the package loading contract."""
    from vibeflow.targets.python.project.source_closure import collect_python_source_facts
    from vibeflow.targets.python.project.source_closure import resolve_local_module_path
    from vibeflow.core.descriptors.source_bundle import implementation_sources
    paths = set()
    for entry in contribution.resources:
        for implementation in getattr(entry.descriptor, "implementations", ()):
            for _, locator in implementation_sources(implementation):
                if locator.kind == "file":
                    continue
                path = next((found for root in (owner.path, workspace.root, package.parent)
                    if (found := resolve_local_module_path(locator.ref, project_root=root)) is not None), None)
                if path is None or not path.is_relative_to(package):
                    raise ValueError(f"Plugin '{contribution.id}' implementation must resolve inside its package: {locator.ref}")
                paths.add(str(path))
    facts, parsed = {}, {}
    for source in package.rglob("*.py"):
        for fact in collect_python_source_facts(source, project_root=owner.path,
            source_roots=(workspace.root,), _facts=facts, _parsed=parsed, _parse_cache=syntax_cache):
            paths.add(fact.path)
    return paths
