"""Language source facts for the current Python command's declaration closure."""
import inspect
from vibeflow.core.tasks import call_specs
import sys
from pathlib import Path

from vibeflow.core.flow import GraphConfig, STATUS_PLANNED, LOOP_NODE_TYPES, IO_NODE_TYPE
from vibeflow.targets.python.project.registry import NodeRegistry, NodeRegistryError
from vibeflow.targets.python.project.source_closure import collect_python_source_facts
from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, PythonSourceCall, build_python_source_context


def workflow_node_types(graph):
    from vibeflow.core.rules.planning import graph_rule_subjects
    selected = set()
    for subject in graph_rule_subjects(graph):
        for node in call_specs(subject.graph.nodes):
            if node.status != STATUS_PLANNED and node.type_used not in LOOP_NODE_TYPES and node.type_used != IO_NODE_TYPE and node.type_used not in subject.graph.nodesets:
                selected.add(node.type_used)
    return tuple(sorted(selected))


def analyze_node_source_context(registry: NodeRegistry, type_keys: tuple[str, ...], *, calls=None):
    """Return the requested implementation closure without changing active facts."""
    from vibeflow.targets.python.project.source_membership import resource_paths
    from vibeflow.targets.python.project.check_session import current_python_check
    session = current_python_check(registry)
    parsed = session.parsed_sources if session is not None else None
    parse_cache = session.parse_cache if session is not None else None

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
        entries = (path, *(file for role,file,_ in resource_paths(descriptor, root, getattr(registry,"source_roots",(root,))) if role == "support"))
        for fact in (fact for entry in entries for fact in collect_python_source_facts(entry, project_root=root, source_roots=getattr(registry, "source_roots", (root,)), _facts=source_facts, _parsed=parsed, _parse_cache=parse_cache)):
            if fact.load_error:
                raise NodeRegistryError(fact.load_error)
            owner = Path(fact.root_path) if fact.root_path else next((item for item in getattr(registry, "source_roots", (root,)) if Path(fact.path).is_relative_to(item)), Path(fact.path).parent)
            relative = Path(fact.path).relative_to(owner)
            module = ".".join(relative.with_suffix("").parts)
            if module.endswith(".__init__"):
                module = module[:-9]
            files[fact.path] = PythonSourceFile(fact.path, module, fact.source, getattr(registry, "source_root_ids", {}).get(owner, root_id), fact._tree, fact.parse_error,fact.parse_line,fact.parse_column)
    # Inspect explicitly registered parts of libraries already in this scope.
    for catalog in getattr(registry,"rule_catalogs", ()) or ():
        for library in getattr(catalog, "base_libs", ()):
            root_object = getattr(registry,"resource_roots",{}).get(("base_libs",library.id))
            if root_object is None:
                continue
            members = tuple(resource_paths(library,root_object.path,registry.source_roots))
            if not any(str(path) in files for role,path,_ in members if role == "entry"):
                continue
            for role,path,_ in members:
                if role != "support":
                    continue
                for fact in collect_python_source_facts(path,project_root=root_object.path,source_roots=registry.source_roots,_facts=source_facts,_parsed=parsed,_parse_cache=parse_cache):
                    if fact.load_error:
                        raise NodeRegistryError(fact.load_error)
                    owner = Path(fact.root_path) if fact.root_path else root_object.path
                    module = ".".join(Path(fact.path).relative_to(owner).with_suffix("").parts).removesuffix(".__init__")
                    files[fact.path] = PythonSourceFile(fact.path,module,fact.source,root_object.id,fact._tree,
                        fact.parse_error,fact.parse_line,fact.parse_column)
    return build_python_source_context(nodes, files.values())


def publish_python_source_context(registry, context):
    """Publish a complete scope and sample its actual module loading state."""
    loaded_paths = {str(Path(filename).resolve()) for module in tuple(sys.modules.values())
                    if isinstance(filename := getattr(module, "__file__", None), str)}
    from types import MappingProxyType
    registry.source_load_states = MappingProxyType({file.path: "loaded" if file.path in loaded_paths else "not_loaded" for file in context.files})
    registry.source_context_snapshot = context
    from vibeflow.targets.python.project.check_session import current_python_check
    session = current_python_check(registry)
    if session is not None:
        session.sources = context
    return context


def collect_node_source_context(registry: NodeRegistry, type_keys: tuple[str, ...], *, calls=None):
    return publish_python_source_context(registry, analyze_node_source_context(registry, type_keys, calls=calls))


def collect_workflow_source_context(registry, graph):
    from vibeflow.core.rules.planning import graph_rule_subjects
    calls = {}
    call_facts = []
    subjects = {item.call_path:item for item in graph_rule_subjects(graph) if not item.declaration_only}
    def collect(subject):
        for spec in subject.graph.nodes:
            path = (*subject.call_path,spec.id)
            call_id = "/".join(path)
            calls.setdefault(spec.type_used, []).append((subject.owner, call_id))
            call_facts.append(PythonSourceCall(subject.owner,call_id,spec.type_used,spec.params,subject.graph.source_path,spec.id,path,spec.rulesets))
            if path in subjects:
                collect(subjects[path])
            for slot in spec.task_targets:
                task_path = (*path, "tasks", slot)
                if task_path in subjects:
                    collect(subjects[task_path])
    collect(subjects[()])
    from dataclasses import replace
    context = analyze_node_source_context(registry, workflow_node_types(graph), calls=calls)
    context = replace(context,calls=tuple(call_facts))
    return publish_python_source_context(registry, context)

