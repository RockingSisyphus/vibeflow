"""Read canonical declarations, then bind only selected Python symbols."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from contextlib import contextmanager
from pathlib import Path

from vibeflow.core.descriptors.models import NodeDescriptor
from vibeflow.core.flow import GraphConfig, IO_NODE_TYPE, LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.targets.python.project.registry import NodeRegistry, NodeRegistryError
from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, PythonSourceCall, build_python_source_context
from vibeflow.tooling.application.python.project.source_preflight import collect_python_source_facts, resolve_local_module_path
from vibeflow.tooling.project.descriptor_loader import load_project_descriptor_catalogs


def declared_python_registry(workspace) -> NodeRegistry:
    """Load every resource identity without executing a registry or Node file."""
    registry = NodeRegistry()
    catalogs = []
    locations: dict[str, tuple[Path, str, str, Path]] = {}
    origins = {}
    source_roots = tuple(root.path for root in workspace.roots if root.project_target == "python")
    for root in workspace.roots:
        if root.project_target != "python":
            continue
        catalog = load_project_descriptor_catalogs(root.path, project_config=root.config_path)
        catalogs.append(catalog)
        for category in getattr(catalog, "categories", ()):
            existing = registry.categories.get(category.id)
            if existing is None:
                registry.categories.register(category, source=catalog.categories.source_for(category.id))
            elif existing != category:
                raise NodeRegistryError(f"conflicting category declaration '{category.id}'")
        for descriptor in catalog.nodes:
            implementations = tuple(item for item in descriptor.implementations if item.language == "python")
            if not implementations:
                continue
            if len(implementations) != 1:
                raise NodeRegistryError(f"node '{descriptor.type_key}' must select one Python implementation")
            if descriptor.type_key in origins:
                from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
                previous = origins[descriptor.type_key]
                raise WorkspaceConfigError("WORKSPACE.REGISTRY.DUPLICATE_TYPE_KEY",
                    f"duplicate node type_key '{descriptor.type_key}' from root '{root.id}' ({root.config_path}) conflicts with root '{previous.id}' ({previous.config_path})",
                    {"path":str(root.config_path), "previous_root":previous.id, "current_root":root.id})
            origins[descriptor.type_key] = root
            source = implementations[0].source
            path = _implementation_path(source.kind, source.ref, root.path, source_roots)
            symbol = str(source.export or "").strip()
            if not symbol:
                raise NodeRegistryError(f"node '{descriptor.type_key}' Python source must name its exported class")
            location = (path, symbol, root.id, root.path)
            locations[descriptor.type_key] = location
            registry.register(descriptor, loader=lambda key=descriptor.type_key: _bind_node(registry, key, source_roots), source=catalog.nodes.source_for(descriptor.type_key))
    registry.source_locations = locations
    registry.source_root_ids = {root.path:root.id for root in workspace.roots}
    registry.source_roots = source_roots
    registry.source_context_loader = lambda key: collect_node_source_context(registry, (key,))
    registry.rule_handler_loader = lambda plan: _load_rule_handlers(registry, plan, workspace)
    registry.rule_catalogs = tuple(catalogs)
    from vibeflow.targets.python.quality.rule_adapter import selected_effect_scope

    registry.rule_policy_resolver = lambda key: selected_effect_scope(registry, key)
    return registry


def workflow_node_types(graph: GraphConfig) -> tuple[str, ...]:
    """Follow actual Nodeset and Loop calls, not unused registered definitions."""
    selected: set[str] = set()
    visited: set[str] = set()

    def walk(current: GraphConfig, inherited: dict[str, object]) -> None:
        definitions = {**inherited, **current.nodesets}
        for node in current.nodes:
            if node.status == STATUS_PLANNED:
                continue
            nested = node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used
            if nested in definitions:
                if nested not in visited:
                    visited.add(nested)
                    walk(definitions[nested].graph, definitions)
            elif node.type_used not in LOOP_NODE_TYPES and node.type_used != IO_NODE_TYPE:
                selected.add(node.type_used)

    walk(graph, {})
    return tuple(sorted(selected))


def collect_node_source_context(registry: NodeRegistry, type_keys: tuple[str, ...], *, calls=None):
    nodes: list[PythonSourceNode] = []
    files: dict[str, PythonSourceFile] = {}
    source_facts = {}
    for key in type_keys:
        if key not in registry.available():
            continue
        descriptor = registry.descriptor(key)
        try:
            path, symbol, root_id, root = getattr(registry, "source_locations", {})[key]
        except KeyError:
            implementation = getattr(registry, "_registry", {}).get(key)
            filename = inspect.getsourcefile(implementation) if implementation is not None else None
            if filename is None:
                raise NodeRegistryError(f"node '{key}' has no available declared source location or bound source")
            path = Path(filename).resolve()
            symbol = implementation.__qualname__.replace(".<locals>", "")
            root_id = "bound"
            root = path.parent
            for _ in implementation.__module__.split(".")[:-1]:
                root = root.parent
        nodes.append(PythonSourceNode(descriptor, str(path), symbol, root_id, tuple((calls or {}).get(key, ()))))
        for fact in collect_python_source_facts(path, project_root=root, source_roots=getattr(registry, "source_roots", (root,)), _facts=source_facts):
            if fact.load_error:
                raise NodeRegistryError(fact.load_error)
            owner = Path(fact.root_path) if fact.root_path else next((item for item in getattr(registry, "source_roots", (root,)) if Path(fact.path).is_relative_to(item)), Path(fact.path).parent)
            relative = Path(fact.path).relative_to(owner)
            module = ".".join(relative.with_suffix("").parts)
            if module.endswith(".__init__"):
                module = module[:-9]
            files[fact.path] = PythonSourceFile(fact.path, module, fact.source, getattr(registry, "source_root_ids", {}).get(owner, root_id), fact._tree, fact.parse_error,fact.parse_line,fact.parse_column)
    context = build_python_source_context(nodes, files.values())
    registry.source_context_snapshot = context
    return context


def collect_workflow_source_context(registry, graph):
    calls = {}
    call_facts = []
    def collect(current, inherited, prefix=(), owner="pipeline", active=()):
        definitions = {**inherited,**current.nodesets}
        for spec in current.nodes:
            path = (*prefix,spec.id)
            call_id = "/".join(path)
            calls.setdefault(spec.type_used, []).append((owner, call_id))
            call_facts.append(PythonSourceCall(owner,call_id,spec.type_used,spec.params,current.source_path,spec.id,path))
            key = spec.loop.body if spec.type_used in LOOP_NODE_TYPES else spec.type_used
            if spec.status != STATUS_PLANNED and key in definitions and key not in active:
                collect(definitions[key].graph,definitions,path,"nodeset:"+key,(*active,key))
    collect(graph,{})
    from dataclasses import replace
    context = collect_node_source_context(registry, workflow_node_types(graph), calls=calls)
    context = replace(context,calls=tuple(call_facts))
    registry.source_context_snapshot = context
    return context


def _load_rule_handlers(registry, plan, workspace):
    handlers = {}
    roots = tuple(root for root in workspace.roots if root.project_target == "python")
    for invocation in plan.invocations:
        rule = invocation.rule
        implementations = tuple(item for item in rule.implementations if item.language == "python")
        if not implementations:
            continue
        if len(implementations) != 1:
            raise NodeRegistryError(f"rule '{rule.id}' must select one Python implementation")
        source = implementations[0].source
        owner = next((root for root,catalog in zip(roots,registry.rule_catalogs) if catalog.rules.get(rule.id) == rule and not catalog.rules.source_for(rule.id).startswith("builtin:")), None)
        if owner is None:
            raise NodeRegistryError(f"rule '{rule.id}' has no declaring Python project")
        # Trusted rule code has normal process capabilities; Node effect Rules do not sandbox it.
        manifest = next(catalog.rules.source_for(rule.id) for root,catalog in zip(roots,registry.rule_catalogs) if root is owner)
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
            raise PythonRuleBindingError(rule.id, manifest, implementation, exc) from exc
    return handlers


def _load_rule_handler(path, symbol, owner, registry):
    with _source_paths((owner.path,*registry.source_roots)):
        name = f"_vibeflow_rule_{abs(hash(str(path)))}"
        module = sys.modules.get(name)
        if module is None:
            spec = importlib.util.spec_from_file_location(name,path)
            if spec is None or spec.loader is None:
                raise NodeRegistryError(f"cannot load rule source: {path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(name,None)
                raise
        value = module
        for part in symbol.split("."):
            value = getattr(value,part)
    if not callable(value):
        raise NodeRegistryError("declared Rule handler must be callable")
    return value


class PythonRuleBindingError(NodeRegistryError):
    """A declaration-backed Rule implementation could not be loaded."""
    def __init__(self, rule_id, manifest, implementation, cause):
        from vibeflow.core.findings import HealthFinding
        symbol = implementation["export"]
        message = f"rule '{rule_id}' handler '{symbol}' could not be bound: {cause}"
        self.findings = (HealthFinding(rule_id="RULE.IMPLEMENTATION.LOAD", severity="error",
            object_type="rule", object_id=rule_id, definition_id=rule_id, failure_layer="rule",
            message=message, source_location={"path":str(manifest),"line":1,"column":1},
            details={"implementation":implementation}),)
        super().__init__(message)


def _implementation_path(kind: str, reference: str, root: Path, roots: tuple[Path, ...]) -> Path:
    if kind == "file":
        path = (root / reference).resolve()
        if not path.is_relative_to(root.resolve()):
            raise NodeRegistryError("implementation file must remain under its declaring project root")
    elif kind == "module":
        path = next((value for candidate in (root, *roots) if (value := resolve_local_module_path(reference, project_root=candidate)) is not None), None)
        if path is None:
            raise NodeRegistryError(f"cannot resolve declared Python module '{reference}'")
    else:
        raise NodeRegistryError(f"Python implementation source kind '{kind}' is not supported")
    if not path.is_file():
        raise NodeRegistryError(f"declared Python source does not exist: {path}")
    return path


def _bind_node(registry: NodeRegistry, key: str, roots: tuple[Path, ...]) -> type:
    from dataclasses import replace
    from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules

    snapshot = getattr(registry, "source_context_snapshot", None)
    selected = tuple(node for node in snapshot.nodes if node.type_key == key) if snapshot is not None else ()
    # The checked workflow already supplied its actual calls and ownership.
    # Limit this binding check to its Node without replacing the full snapshot.
    context = replace(snapshot,nodes=selected) if selected else collect_node_source_context(registry, (key,))
    results = execute_python_node_rules(registry, context, phase="import",**registry.rule_defaults())
    findings = tuple(item for item in results.findings if item.severity == "error")
    if findings:
        raise PythonSourceRuleError(findings)
    path, symbol, _, root = registry.source_locations[key]
    relative = path.relative_to(root).with_suffix("")
    module_name = ".".join(relative.parts)
    try:
        with _source_paths((root, *roots)):
            module = sys.modules.get(module_name)
            if module is None or Path(getattr(module, "__file__", "")).resolve() != path:
                specification = importlib.util.spec_from_file_location(module_name, path)
                if specification is None or specification.loader is None:
                    raise NodeRegistryError(f"cannot load declared Python source: {path}")
                module = importlib.util.module_from_spec(specification)
                sys.modules[module_name] = module
                try:
                    specification.loader.exec_module(module)
                except BaseException:
                    sys.modules.pop(module_name, None)
                    raise
            implementation = module
            for member in symbol.split("."):
                implementation = getattr(implementation, member)
        if not isinstance(implementation, type):
            raise NodeRegistryError(f"declared Python symbol '{symbol}' must be a class")
    except Exception as exc:
        from vibeflow.core.findings import HealthFinding
        error = NodeRegistryError(f"node '{key}' implementation '{symbol}' could not be bound: {exc}")
        error.findings = (HealthFinding(rule_id="NODE.IMPLEMENTATION.BINDING",severity="error",
            object_type="node",object_id=key,failure_layer="implementation",message=str(error),
            source_location={"path":registry.source_info(key).path,"line":1,"column":1},
            details={"implementation":{"path":str(path),"export":symbol}}),)
        raise error from exc
    return implementation


class PythonSourceRuleError(NodeRegistryError):
    def __init__(self, findings):
        self.findings = tuple(findings)
        super().__init__("; ".join(item.message for item in self.findings))


@contextmanager
def _source_paths(roots: tuple[Path, ...]):
    additions = [str(root) for root in dict.fromkeys(roots) if str(root) not in sys.path]
    sys.path[:0] = additions
    try:
        yield
    finally:
        for value in additions:
            sys.path.remove(value)


__all__ = ["declared_python_registry", "workflow_node_types", "collect_node_source_context", "collect_workflow_source_context", "PythonSourceRuleError"]
