"""Python compiler adapter with declaration facts and compiler-plugin orchestration.

The language-neutral graph compiler lives in :mod:`vibeflow.core.compiler`.
This module adapts canonical declarations and available implementation facts.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Protocol

from vibeflow.core.compiler import (
    CompiledGraph,
    GraphCompileError,
    compile_core,
    explicit_flow_cycles,
)
from vibeflow.core.flow import (
    LOOP_DEFINITION_IDS,
    STATUS_PLANNED,
    GraphConfig,
)
from vibeflow.core.constants import (
    TARGET_FEATURE_EXECUTION_LOCKS,
    TARGET_FEATURE_GLOBAL_STATE,
)
from vibeflow.core.models import (
    CoreCompilation,
    CoreCompileRequest,
    ImplementationFact,
    ImplementationFacts,
    TargetFeatureSet,
)


class CompilerPluginRegistry(Protocol):
    """Structural seam for compiler plugins owned by the Python frontend."""

    def compiler_plugins(self) -> tuple[object, ...]: ...


class GraphCompiler:
    """Python-facing compiler adapter.

    Dynamic registry lookup and plugin execution stop at this boundary; Core
    receives only immutable, language-neutral implementation facts.
    """

    def compile(
        self,
        graph: GraphConfig,
        *,
        registry: Any | None = None,
        catalog: Any | None = None,
        known_nodeset_types: set[str] | None = None,
        plugin_registry: CompilerPluginRegistry | None = None,
        owner: str = "pipeline",
        call_path: tuple[str, ...] = (),
        implementation_facts: ImplementationFacts | None = None,
    ) -> CompiledGraph:
        return self.compile_with_findings(
            graph,
            registry=registry,
            catalog=catalog,
            known_nodeset_types=known_nodeset_types,
            plugin_registry=plugin_registry,
            owner=owner,
            call_path=call_path,
            implementation_facts=implementation_facts,
        ).compiled_graph

    def compile_with_findings(
        self,
        graph: GraphConfig,
        *,
        registry: Any | None = None,
        catalog: Any | None = None,
        known_nodeset_types: set[str] | None = None,
        plugin_registry: CompilerPluginRegistry | None = None,
        owner: str = "pipeline",
        call_path: tuple[str, ...] = (),
        implementation_facts: ImplementationFacts | None = None,
    ) -> CoreCompilation:
        """Compile and retain advisory Core findings for health/report callers."""

        if registry is not None and catalog is not None:
            raise GraphCompileError(
                "compile accepts either registry or catalog, not both"
            )
        type_source = catalog if catalog is not None else registry
        _call_compiler_plugins(plugin_registry, "before_compile", graph)
        nodeset_types = known_nodeset_types or set(graph.nodeset_types)
        if implementation_facts is None:
            implementation_facts = _adapt_implementation_facts(graph, source=type_source, nodeset_types=nodeset_types)
        elif not isinstance(implementation_facts, ImplementationFacts):
            raise GraphCompileError("implementation_facts must be an ImplementationFacts snapshot")
        compilation = compile_core(
            CoreCompileRequest(
                graph=graph,
                implementation_facts=implementation_facts,
                target_features=TargetFeatureSet(
                    target="python",
                    features=frozenset(
                        {
                            TARGET_FEATURE_EXECUTION_LOCKS,
                            TARGET_FEATURE_GLOBAL_STATE,
                        }
                    ),
                ),
                known_nodeset_types=frozenset(nodeset_types),
                owner=owner,
            ),
        )
        call_scopes = getattr(registry, "call_effect_scopes", {})
        if call_scopes:
            compilation = replace(compilation, compiled_graph=replace(compilation.compiled_graph, effect_scopes={
                **compilation.compiled_graph.effect_scopes, **{node.id:call_scopes[(*call_path, node.id)]
                    for node in graph.nodes if (*call_path, node.id) in call_scopes}}))
        _call_compiler_plugins(
            plugin_registry,
            "after_compile",
            graph,
            compilation.compiled_graph,
        )
        if registry is not None and plugin_registry is not None:
            from vibeflow.targets.python.project.check_session import current_python_check
            session = current_python_check(registry)
            if session is not None:
                session.remember_compiler_stage(graph, compilation)
        return compilation

    def prepare_implementation_facts(self, graph: GraphConfig, *, registry=None, catalog=None) -> ImplementationFacts:
        """Freeze Target facts once for a root and its presentation subgraphs."""
        if registry is not None and catalog is not None:
            raise GraphCompileError("fact preparation accepts either registry or catalog, not both")
        return _adapt_implementation_facts(graph, source=catalog if catalog is not None else registry,
                                           nodeset_types=set(graph.nodeset_types))

    def _refresh_rule_facts(self, compilation: CoreCompilation, *, registry, call_path=()) -> CoreCompilation:
        """Update review metadata while retaining the compiler stage artifact.

        Rules describe the explicitly selected effects.
        Neither changes the already resolved native topology or contracts.
        Compiler hooks own their stage's other compiled fields.
        """
        facts = ImplementationFacts(tuple(replace(fact,
            effect_scope=registry.effect_scope(fact.definition_id),
            )
            for fact in compilation.workflow.implementation_facts.nodes),
            strict=compilation.workflow.implementation_facts.strict)
        graph = compilation.workflow.graph
        compiled = compilation.compiled_graph
        scopes = dict(compiled.effect_scopes)
        for node in graph.nodes:
            fact = facts.get(node.definition_id)
            if node.status != STATUS_PLANNED and fact is not None:
                scopes[node.id] = getattr(registry, "call_effect_scopes", {}).get((*call_path, node.id), fact.effect_scope or "unconstrained")
        return replace(compilation, workflow=replace(compilation.workflow, implementation_facts=facts),
                       compiled_graph=replace(compiled, effect_scopes=scopes))


def _adapt_implementation_facts(
    graph: GraphConfig,
    *,
    source: Any | None,
    nodeset_types: set[str],
) -> ImplementationFacts:
    if source is None:
        return ImplementationFacts()
    nodeset_types = set(nodeset_types)
    nodeset_types.update(graph.nodeset_types)
    relevant: set[str] = set()
    visited: set[int] = set()

    def collect(current: GraphConfig) -> None:
        if id(current) in visited:
            return
        visited.add(id(current))
        nodeset_types.update(current.nodeset_types)
        relevant.update(
            node.definition_id
            for node in current.nodes
            if node.status != STATUS_PLANNED
            and node.definition_id not in LOOP_DEFINITION_IDS

            and node.definition_id not in nodeset_types
        )
        for nodeset in current.nodeset_types.values():
            collect(nodeset.graph)

    collect(graph)
    facts: list[ImplementationFact] = []
    for type_key in sorted(relevant):
        try:
            registered = source.descriptor(type_key) if callable(getattr(source, "descriptor", None)) else _require_registered_type(source, type_key)
        except Exception:
            continue
        facts.append(_implementation_fact(type_key, registered, effect_scope=source.effect_scope(type_key) if callable(getattr(source, "effect_scope", None)) else "unconstrained"))
    return ImplementationFacts(tuple(facts), strict=True)


def _implementation_fact(type_key: str, registered: Any, *, effect_scope: str = "unconstrained") -> ImplementationFact:
    flow_kind = _text_attribute(registered, "flow_kind")
    contract = getattr(registered, "contract", None)
    completion = _text_attribute(registered, "completion")
    source_kind = ""
    source_ref = ""
    source_export = ""
    implementations = tuple(getattr(registered, "implementations", ()) or ())
    if implementations:
        implementation = implementations[0]
        completion = completion or _text_attribute(implementation, "completion")
        source = getattr(implementation, "source", None)
        source_kind = _text_attribute(source, "kind")
        source_ref = _text_attribute(source, "ref")
        source_export = _text_attribute(source, "export")
    return ImplementationFact(
        definition_id=type_key,
        flow_kind=flow_kind,
        effect_scope=effect_scope,

        requires=tuple(getattr(contract, "requires", ()) or ()),
        provides=tuple(getattr(contract, "provides", ()) or ()),
        completion=completion or "immediate",
        source_kind=source_kind,
        source_ref=source_ref,
        source_export=source_export,
    )




def _text_attribute(value: object, name: str) -> str:
    attribute = getattr(value, name, "")
    return "" if attribute is None else str(attribute)


def _call_compiler_plugins(
    plugin_registry: CompilerPluginRegistry | None,
    hook: str,
    *args: object,
) -> None:
    if plugin_registry is None:
        return
    for plugin in plugin_registry.compiler_plugins():
        method = getattr(plugin, hook, None)
        if not callable(method):
            continue
        try:
            method(*args)
        except Exception as exc:
            plugin_name = str(
                getattr(plugin, "name", plugin.__class__.__name__)
            )
            raise GraphCompileError(
                f"compiler plugin '{plugin_name}' {hook} failed: {exc}"
            ) from exc


def _require_registered_type(source: Any, type_key: str) -> Any:
    require = getattr(source, "require", None)
    if callable(require):
        return require(type_key)
    get = getattr(source, "get", None)
    if not callable(get):
        raise KeyError(type_key)
    value = get(type_key)
    if value is None:
        raise KeyError(type_key)
    return value

__all__ = [
    "CompiledGraph",
    "GraphCompileError",
    "GraphCompiler",
    "explicit_flow_cycles",
]
