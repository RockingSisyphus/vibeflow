"""Compatibility compiler facade with Python compiler-plugin orchestration.

The language-neutral graph compiler lives in :mod:`vibeflow.core.compiler`.
This module adapts legacy Registry/Catalog objects into static facts and keeps
the established Python compiler-plugin hook order.
"""

from __future__ import annotations

from typing import Any, Protocol

from vibeflow.core.compiler import (
    CompiledGraph,
    GraphCompileError,
    GraphCompiler as CoreGraphCompiler,
    explicit_flow_cycles,
)
from vibeflow.core.flow import (
    IO_NODE_TYPE,
    LOOP_NODE_TYPES,
    STATUS_PLANNED,
    GraphConfig,
)
from vibeflow.core.constants import (
    TARGET_FEATURE_EXECUTION_LOCKS,
    TARGET_FEATURE_GLOBAL_STATE,
)
from vibeflow.core.models import (
    ImplementationFact,
    ImplementationFacts,
    TargetFeatureSet,
)


class CompilerPluginRegistry(Protocol):
    """Structural seam for compiler plugins owned by the Python frontend."""

    def compiler_plugins(self) -> tuple[object, ...]: ...


class GraphCompiler:
    """Legacy Python-facing compiler wrapper.

    Dynamic registry lookup and plugin execution stop at this boundary; Core
    receives only immutable, language-neutral implementation facts.
    """

    def compile(
        self,
        graph: GraphConfig,
        *,
        registry: Any | None = None,
        catalog: Any | None = None,
        known_nodesets: set[str] | None = None,
        plugin_registry: CompilerPluginRegistry | None = None,
        owner: str = "pipeline",
    ) -> CompiledGraph:
        if registry is not None and catalog is not None:
            raise GraphCompileError(
                "compile accepts either registry or catalog, not both"
            )
        type_source = catalog if catalog is not None else registry
        _call_compiler_plugins(plugin_registry, "before_compile", graph)
        nodesets = known_nodesets or set(graph.nodesets)
        implementation_facts = _adapt_implementation_facts(
            graph,
            source=type_source,
            nodesets=nodesets,
        )
        compiled = CoreGraphCompiler().compile(
            graph,
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
            known_nodesets=nodesets,
            owner=owner,
        )
        _call_compiler_plugins(
            plugin_registry,
            "after_compile",
            graph,
            compiled,
        )
        return compiled


def _adapt_implementation_facts(
    graph: GraphConfig,
    *,
    source: Any | None,
    nodesets: set[str],
) -> ImplementationFacts:
    if source is None:
        return ImplementationFacts()
    relevant = set(nodesets)
    relevant.update(
        node.type_used
        for node in graph.nodes
        if node.status != STATUS_PLANNED
        and node.type_used not in LOOP_NODE_TYPES
        and node.type_used != IO_NODE_TYPE
        and node.type_used not in nodesets
    )
    facts: list[ImplementationFact] = []
    for type_key in sorted(relevant):
        try:
            registered = _require_registered_type(source, type_key)
        except Exception:
            continue
        facts.append(_implementation_fact(type_key, registered))
    return ImplementationFacts(tuple(facts), strict=True)


def _implementation_fact(type_key: str, registered: Any) -> ImplementationFact:
    direct_flow_kind = _text_attribute(registered, "flow_kind")
    info = getattr(registered, "NODE_INFO", None)
    flow_kind = direct_flow_kind or _text_attribute(info, "flow_kind")
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
    if not source_ref:
        source_ref = _text_attribute(registered, "__module__")
        source_export = _text_attribute(registered, "__qualname__")
        source_kind = "module" if source_ref else ""
    return ImplementationFact(
        type_key=type_key,
        flow_kind=flow_kind,
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
