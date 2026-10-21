"""Read canonical declarations, then bind only selected Python symbols."""

from __future__ import annotations

from pathlib import Path

from vibeflow.targets.python.sdk.loading import source_paths
from vibeflow.targets.python.sdk.source_namespace import source_namespace
from vibeflow.targets.python.project.registry import NodeRegistry, NodeRegistryError, load_node_implementation
from vibeflow.targets.python.project.source_closure import resolve_local_module_path
from vibeflow.tooling.project.resources import prepare_workflow_resources


def default_python_registry() -> NodeRegistry:
    """Assemble the standard SDK contribution once at the Application boundary."""
    from vibeflow.tooling.project.resources import load_builtin_plugins
    loaded = load_builtin_plugins("python")
    registry = NodeRegistry()
    registry.prepared_resources = loaded
    registry.source_namespaces = loaded.binding_contexts.get("python", {})
    registry.rule_catalogs = (loaded.catalogs,)
    registry.direct_bindings = {(kind, key): value for (_, kind, key), value in loaded.bindings.items()}
    registry.rule_handler_loader = lambda plan: {
        key: registry.direct_bindings[("rule", key)]
        for invocation in plan.invocations for key in (invocation.rule.handler or invocation.rule.id,)
        if ("rule", key) in registry.direct_bindings}
    return registry


def declared_python_registry(workspace, config_path=None, *, prepared_resources=None) -> NodeRegistry:
    """Bind only resources contributed by this workflow's selected plugins."""
    from vibeflow.tooling.project.resources import load_builtin_plugins
    loaded = prepared_resources or (prepare_workflow_resources(workspace, config_path) if config_path else
        load_builtin_plugins("python"))
    registry = NodeRegistry()
    catalog = loaded.catalogs
    from vibeflow.tooling.project.resources.ownership import visible_source_roots, ResourceScope
    current_root = workspace.root_for_path(config_path) if config_path else None
    source_roots = visible_source_roots(workspace, current_root) if current_root else (workspace.root,)
    locations = {}
    bindings = {(kind, key): value for (_, kind, key), value in loaded.bindings.items()}
    bindings.update(loaded.resource_bindings)
    resource_roots = {}
    for group in ("nodes", "rules", "base_libs", "plugins"):
        for descriptor in getattr(catalog, group):
            origin = catalog.origins.get((group, descriptor.id))
            if origin is None:
                continue
            if origin.owner.kind != "plugin":
                resource_roots[(group, descriptor.id)] = ResourceScope(origin.owner.id,
                    Path(origin.owner.path), "python", {})
            else:
                resource_roots[(group, descriptor.id)] = ResourceScope(
                    origin.owner.root_id or "@project", Path(origin.owner.path), "python", {})
    for descriptor in catalog.nodes:
        implementations = tuple(item for item in descriptor.implementations if item.language == "python")
        if not implementations:
            continue
        if len(implementations) != 1:
            raise NodeRegistryError(f"node '{descriptor.id}' must select one Python implementation")
        root = resource_roots[("nodes", descriptor.id)]
        source = implementations[0].source
        path = _implementation_path(source.kind, source.ref, root.path, source_roots)
        symbol = str(source.export or "").strip()
        if not symbol:
            raise NodeRegistryError(f"node '{descriptor.id}' Python source must name its exported class")
        analysis_root = root.path if path.is_relative_to(root.path) else path.parent
        locations[descriptor.id] = (path, symbol, root.id, analysis_root)
        registry.register(descriptor, loader=lambda key=descriptor.id: _bind_node(registry, key, source_roots),
                          source=catalog.nodes.source_for(descriptor.id), source_line=catalog.origins[("nodes",descriptor.id)].line)
    registry.source_locations = locations
    registry.resource_roots = resource_roots
    registry.direct_bindings = bindings
    registry.prepared_resources = loaded
    registry.source_namespaces = loaded.binding_contexts.get("python", {})
    registry.source_root_ids = {path: current_root.id if current_root and path == current_root.path else "@project"
                                for path in source_roots}
    registry.source_roots = source_roots
    registry.source_context_loader = lambda key: analyze_node_source_context(registry, (key,))
    registry.rule_handler_loader = lambda plan: _load_rule_handlers(registry, plan, workspace)
    registry.rule_catalogs = (catalog,)
    from vibeflow.targets.python.quality.rule_adapter import selected_effect_scope
    registry.rule_policy_resolver = lambda key: selected_effect_scope(registry, key)
    return registry


from vibeflow.targets.python.project.sources import (workflow_node_ids, analyze_node_source_context,
    publish_python_source_context, collect_node_source_context, collect_workflow_source_context)


def _load_rule_handlers(registry, plan, workspace):
    handlers = {}
    roots = tuple(root for root in workspace.roots if root.project_target == "python")
    for invocation in plan.invocations:
        rule = invocation.rule
        from vibeflow.targets.shared.bindings import native_binding
        key = rule.handler or rule.id
        direct = getattr(registry, "direct_bindings", {}).get(("rule", key))
        if direct is None:
            direct = native_binding(registry.rule_catalogs[0], "rule", key)
        if direct is not None:
            handlers[key] = direct
            handlers[rule.id] = direct
            continue
        implementations = tuple(item for item in rule.implementations if item.language == "python")
        if not implementations:
            continue
        if len(implementations) != 1:
            raise NodeRegistryError(f"rule '{rule.id}' must select one Python implementation")
        source = implementations[0].source
        owner = getattr(registry, "resource_roots", {}).get(("rules", rule.id))
        if owner is None:
            raise NodeRegistryError(f"rule '{rule.id}' has no contributing plugin")
        manifest = registry.rule_catalogs[0].rules.source_for(rule.id)
        symbol = source.export or rule.handler
        if not symbol:
            raise NodeRegistryError(f"rule '{rule.id}' must name its exported handler")
        path = None
        try:
            path = _implementation_path(source.kind, source.ref, owner.path, registry.source_roots)
            handlers[rule.id] = _load_rule_handler(path, symbol, owner, registry)
        except Exception as exc:
            implementation = {"kind":source.kind,"ref":source.ref,"export":symbol}
            if path is not None or source.kind == "file":
                implementation["path"] = str(path or (owner.path / source.ref).resolve())
            raise PythonRuleBindingError(rule.id, manifest, implementation, exc,
                registry.rule_catalogs[0].rules.location_for(rule.id)) from exc
    return handlers


def _load_rule_handler(path, symbol, owner, registry):
    with source_paths((owner.path,*registry.source_roots)):
        namespaces = registry.source_namespaces
        module = source_namespace(owner.path, namespaces=namespaces, source_roots=registry.source_roots).load(path)
        value = module
        for part in symbol.split("."):
            value = getattr(value,part)
    if not callable(value):
        raise NodeRegistryError("declared Rule handler must be callable")
    return value


class PythonRuleBindingError(NodeRegistryError):
    """A declaration-backed Rule implementation could not be loaded."""
    def __init__(self, rule_id, manifest, implementation, cause, location=None):
        from vibeflow.core.findings import HealthFinding
        symbol = implementation["export"]
        message = f"rule '{rule_id}' handler '{symbol}' could not be bound: {cause}"
        self.findings = (HealthFinding(rule_id="RULE.IMPLEMENTATION.LOAD", severity="error",
            object_type="rule", object_id=rule_id, definition_id=rule_id, failure_layer="rule",
            message=message, source_location=location or {"path":str(manifest)},
            details={"implementation":implementation}),)
        super().__init__(message)


def _implementation_path(kind: str, reference: str, root: Path, roots: tuple[Path, ...]) -> Path:
    if kind == "file":
        path = (root / reference).resolve()

    elif kind in {"module", "package"}:
        path = next((value for candidate in (root, *roots) if (value := resolve_local_module_path(reference, project_root=candidate)) is not None), None)
        if path is None:
            import importlib.util
            with source_paths((root, *roots)):
                spec = importlib.util.find_spec(reference)
            if spec is None or not spec.origin:
                raise NodeRegistryError(f"cannot resolve declared Python module '{reference}'")
            path = Path(spec.origin).resolve()
    else:
        raise NodeRegistryError(f"Python implementation source kind '{kind}' is not supported")
    if not path.is_file():
        raise NodeRegistryError(f"declared Python source does not exist: {path}")
    return path


def _bind_node(registry: NodeRegistry, key: str, roots: tuple[Path, ...]) -> type:
    from vibeflow.targets.python.quality.rule_adapter import review_python_node_binding

    snapshot = getattr(registry, "source_context_snapshot", None)
    selected = tuple(node for node in snapshot.nodes if node.definition_id == key) if snapshot is not None else ()
    # The checked workflow already supplied its actual calls and ownership.
    # Limit this binding check to its Node without replacing the full snapshot.
    context = publish_python_source_context(registry, snapshot) if selected else collect_node_source_context(registry, (key,))
    results = review_python_node_binding(registry, context, key, **registry.rule_defaults())
    findings = tuple(item for item in results.findings if item.severity == "error")
    if findings:
        raise PythonSourceRuleError(findings)
    direct = getattr(registry, "direct_bindings", {}).get(("node", key))
    if direct is not None:
        publish_python_source_context(registry, context)
        return direct
    path, symbol, _, root = registry.source_locations[key]
    namespaces = registry.source_namespaces
    namespace = source_namespace(root, namespaces=namespaces, source_roots=registry.source_roots)
    def load():
        with source_paths((root, *roots)):
            implementation = namespace.load(path)
            for member in symbol.split("."):
                implementation = getattr(implementation, member)
            return implementation
    implementation = load_node_implementation(registry, key, path, symbol, load)
    publish_python_source_context(registry, context)
    return implementation


class PythonSourceRuleError(NodeRegistryError):
    def __init__(self, findings):
        self.findings = tuple(findings)
        super().__init__("; ".join(item.message for item in self.findings))


__all__ = ["declared_python_registry", "workflow_node_ids", "collect_node_source_context", "collect_workflow_source_context", "PythonSourceRuleError"]
