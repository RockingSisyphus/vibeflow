"""One command's immutable review facts and compiled graph definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType
from typing import Any

from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.flow import GraphConfig
from vibeflow.core.models import CoreCompilation, ImplementationFacts
from vibeflow.core.rules.models import plain, readonly




def final_python_compilation(graph, registry):
    from vibeflow.targets.python.project.check_session import current_python_check
    from vibeflow.targets.python.project.compiler import GraphCompiler

    session = current_python_check(registry)
    compilation = getattr(session, "compilation", None)
    if compilation is not None and getattr(session, "compilation_input", None) is graph:
        return compilation
    facts = GraphCompiler().prepare_implementation_facts(graph, registry=registry)
    return GraphCompiler().compile_with_findings(graph, implementation_facts=facts)


@dataclass(frozen=True)
class PreparedPythonPresentation:
    graph: GraphConfig
    compiled: CompiledGraph
    implementation_facts: ImplementationFacts
    registry: object | None = field(default=None, repr=False)
    resources: object | None = field(default=None, repr=False)
    source_context: object | None = field(default=None, repr=False)
    implementation_sources: tuple = field(default=(), repr=False)
    source_config_available: bool = field(default=False, repr=False)
    _keys: dict[int, object] = field(default_factory=dict, repr=False, compare=False)
    _graphs: dict[object, tuple[GraphConfig, CompiledGraph]] = field(default_factory=dict, repr=False, compare=False)
    _architecture: list[Any] = field(default_factory=list, repr=False, compare=False)
    _errors: dict[object, Exception] = field(default_factory=dict, repr=False, compare=False)
    _inputs: list[GraphConfig] = field(default_factory=list, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._keys[id(self.graph)] = None
        self._graphs[None] = (self.graph, self.compiled)
        self._remember_definitions(self.graph)

    def _remember_definitions(self, graph: GraphConfig) -> None:
        for key, definition in graph.nodesets.items():
            self._keys[id(definition.graph)] = key

    def graph_for(self, graph: GraphConfig) -> tuple[GraphConfig, CompiledGraph]:
        """Compile each definition once against this snapshot's final facts."""
        key = self._keys.get(id(graph), ("graph", id(graph)))
        if key in self._errors:
            raise self._errors[key]
        if key not in self._graphs:
            self._inputs.append(graph)
            from vibeflow.targets.python.project.compiler import GraphCompiler

            compilation = GraphCompiler().compile_with_findings(
                graph, implementation_facts=self.implementation_facts,
            )
            effective = readonly(compilation.workflow.graph)
            compiled = readonly(compilation.compiled_graph)
            self._graphs[key] = (effective, compiled)
            self._keys[id(effective)] = key
            self._remember_definitions(effective)
        return self._graphs[key]

    def architecture(self) -> dict[str, object]:
        if not self._architecture:
            from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_facts

            self._architecture.append(readonly(build_architecture_facts(self)))
        # The public document API returns ordinary containers. Mutating one
        # document cannot alter the facts used by another renderer.
        return plain(self._architecture[0])


def prepare_python_presentation(
    graph: GraphConfig, *, compiled: CompiledGraph | None = None,
    registry: object | None = None, resources: object | None = None,
    compilation: CoreCompilation | None = None,
) -> PreparedPythonPresentation:
    """Use a final checked compilation, or prepare current standalone facts.

    A standalone call with a registry keeps the established registry-first
    behavior: its supplied compiled object may predate selected Rule results.
    Formal callers pass their post-Rule compilation explicitly.
    """
    from vibeflow.targets.python.project.compiler import GraphCompiler

    compiler = GraphCompiler()
    input_graph = graph
    if compilation is None and registry is not None:
        facts = compiler.prepare_implementation_facts(graph, registry=registry)
        compilation = compiler.compile_with_findings(graph, implementation_facts=facts)
    if compilation is not None:
        graph = compilation.workflow.graph
        compiled = compilation.compiled_graph
        facts = compilation.workflow.implementation_facts
    else:
        facts = ImplementationFacts()
        if compiled is None:
            compilation = compiler.compile_with_findings(graph, implementation_facts=facts)
            graph, compiled = compilation.workflow.graph, compilation.compiled_graph
    source_context = getattr(registry, "source_context_snapshot", None)
    if registry is not None and hasattr(registry, "loaded_plugins") and source_context is None:
        from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context

        source_context = collect_workflow_source_context(registry, graph)
    snapshot = _registry_snapshot(registry, source_context) if registry is not None else None
    source_config_available = bool(graph.source_path and Path(graph.source_path).is_file())
    implementation_sources = _implementation_source_records(registry, graph, source_context,
                                                            source_config_available=source_config_available)
    prepared = PreparedPythonPresentation(readonly(graph), readonly(compiled), facts, snapshot,
                                          readonly(resources), source_context, readonly(implementation_sources),
                                          source_config_available=source_config_available)
    prepared._keys[id(input_graph)] = None
    prepared._inputs.append(input_graph)
    prepared._remember_definitions(input_graph)
    from vibeflow.core.compiler import GraphCompileError
    for key, definition in prepared.graph.nodesets.items():
        if definition.graph.nodes:
            try:
                prepared.graph_for(definition.graph)
            except GraphCompileError as error:
                # A plain graph renderer need not display an unused invalid
                # body. Architecture raises this original error when it asks
                # for that body's facts, without performing a second compile.
                prepared._errors[key] = error
    return prepared


def _implementation_source_records(registry, graph, sources, *, source_config_available):
    """Complete presentation source facts while the command session is active."""
    if not hasattr(registry, "loaded_plugins") or not source_config_available:
        return ()
    from vibeflow.core.descriptors.source_bundle import source_resources
    from vibeflow.targets.python.project.check_session import current_python_check
    from vibeflow.targets.python.project.source_closure import collect_python_source_facts
    from vibeflow.targets.python.project.source_membership import resource_paths
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, build_python_source_context

    session = current_python_check(registry)
    parsed = session.parsed_sources if session is not None else None
    collected = {file.path:file for file in sources.files}
    source_facts = {}
    for kind, descriptor in source_resources(registry.loaded_plugins.catalogs):
        if kind not in {"plugin", "plugin_declaration"}:
            continue
        for _, entry, _ in resource_paths(descriptor, graph.root_path, registry.source_roots):
            for fact in collect_python_source_facts(entry, project_root=Path(graph.root_path),
                    source_roots=registry.source_roots, _facts=source_facts, _parsed=parsed,
                    _parse_cache=session.parse_cache if session is not None else None):
                if fact.path not in collected:
                    collected[fact.path] = PythonSourceFile(fact.path, fact.module_name, fact.source, "",
                        fact._tree, fact.parse_error, fact.parse_line, fact.parse_column)
    resolved = sources if len(collected) == len(sources.files) else build_python_source_context((), collected.values())
    import sys
    loaded_paths = {str(Path(filename).resolve()) for module in tuple(sys.modules.values())
                    if isinstance(filename := getattr(module, "__file__", None), str)}
    return tuple({"path":file.path, "load_state":"loaded" if file.path in loaded_paths else "not_loaded",
                  "imports":[{"path":item.resolved_path, "specifier":item.specifier, "line":item.line}
                     for item in resolved.imports if item.path == file.path]} for file in collected.values())


def _registry_snapshot(registry: object, source_context: object | None) -> object:
    from vibeflow.targets.python.project.registry import NodeRegistryQueries

    snapshot = NodeRegistryQueries(registry)
    # Existing bindings are metadata only. This query surface has no get(),
    # loader, Rule handler, or lifecycle factory.
    bindings = dict(getattr(registry, "_registry", {}))
    bindings.update({key: value for (kind, key), value in getattr(registry, "direct_bindings", {}).items()
                     if kind == "node" and isinstance(value, type)})
    object.__setattr__(snapshot, "_registry", MappingProxyType(bindings))
    for name in ("source_locations", "source_root_ids", "source_load_states"):
        object.__setattr__(snapshot, name, MappingProxyType(dict(getattr(registry, name, {}))))
    object.__setattr__(snapshot, "source_roots", tuple(getattr(registry, "source_roots", ())))
    object.__setattr__(snapshot, "source_context_snapshot", source_context)
    object.__setattr__(snapshot, "review_findings", tuple(getattr(registry, "review_findings", ())))
    if hasattr(registry, "loaded_plugins"):
        object.__setattr__(snapshot, "loaded_plugins", registry.loaded_plugins)
    return snapshot
