"""Application-closure and neutral Tooling dependency checks."""

from __future__ import annotations

import ast
from pathlib import Path

from .models import Finding, SourceLocation
from .python_scan import (
    ImportGraph,
    repository_path,
    shortest_import_path,
    target_layer,
)


_PYTHON_APPLICATION_MODULES: frozenset[str] = frozenset()

_JAVASCRIPT_APPLICATION_MODULES: frozenset[str] = frozenset()

_PYTHON_APPLICATION_PREFIXES = (
    "vibeflow.tooling.application.python",
    "vibeflow.targets.python.application",
)

_JAVASCRIPT_APPLICATION_PREFIXES = (
    "vibeflow.tooling.application.javascript",
    "vibeflow.targets.javascript.application",
)

_PYTHON_ONLY_SYMBOLS = frozenset(
    {
        "BaseLibRegistry",
        "CompiledBlock",
        "ConfigResources",
        "EffectivePolicy",
        "ExecutionPlan",
        "NodeContract",
        "NodeInfo",
        "NodeRegistry",
        "PipelineRuntime",
        "PluginRegistry",
        "PluginResourceRegistry",
        "PureNode",
        "PythonBindingPlan",
        "PythonCompiledBlock",
        "RuntimeOptions",
        "WorkspaceEnvironment",
        "WorkspaceResourceRegistries",
    }
)

_PYTHON_ONLY_MODULE_PARTS = frozenset({"portable_adapter"})


def neutral_tooling_findings(root: Path, graph: ImportGraph) -> list[Finding]:
    """Reject Target dependencies outside explicit application boundaries."""

    application_modules = frozenset(
        {*_python_application_modules(graph), *_javascript_application_modules(graph)}
    )
    neutral_modules = tuple(
        sorted(
            module
            for module in graph.modules
            if (
                module == "vibeflow.__main__"
                or module == "vibeflow.tooling"
                or module.startswith("vibeflow.tooling.")
            )
            and module not in application_modules
        )
    )
    findings: list[Finding] = []
    for module in neutral_modules:
        path = shortest_import_path(
            graph,
            module,
            lambda target: target_layer(target)
            in {"python-target", "javascript-target"},
            stop_at=lambda target: target in application_modules,
        )
        if path is None:
            continue
        findings.append(
            _dependency_path_finding(
                root=root,
                graph=graph,
                path=path,
                code="NEUTRAL_TARGET_DEPENDENCY",
                message="Target-neutral Tooling/CLI may not depend on a Target",
                source_layer="neutral-tooling",
                target=path[-1],
            )
        )
    return findings


def python_application_findings(root: Path, graph: ImportGraph) -> list[Finding]:
    """Check Python Target modules plus their Tooling application closure."""

    return _application_cross_target_findings(
        root,
        graph,
        language="python",
    ) + _transitive_target_findings(
        root,
        graph,
        layer="python-target",
    )


def javascript_application_findings(
    root: Path,
    graph: ImportGraph,
) -> list[Finding]:
    """Check JavaScript Target/application closure and Python symbol leakage."""

    return (
        _application_cross_target_findings(
            root,
            graph,
            language="javascript",
        )
        + _transitive_target_findings(
            root,
            graph,
            layer="javascript-target",
        )
        + _javascript_python_symbol_findings(root, graph)
    )


def _module_matches(
    module: str,
    values: frozenset[str],
    prefixes: tuple[str, ...],
) -> bool:
    return module in values or any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in prefixes
    )


def _python_application_modules(graph: ImportGraph) -> tuple[str, ...]:
    return tuple(
        sorted(
            module
            for module in graph.modules
            if _module_matches(
                module,
                _PYTHON_APPLICATION_MODULES,
                _PYTHON_APPLICATION_PREFIXES,
            )
        )
    )


def _javascript_application_modules(graph: ImportGraph) -> tuple[str, ...]:
    return tuple(
        sorted(
            module
            for module in graph.modules
            if _module_matches(
                module,
                _JAVASCRIPT_APPLICATION_MODULES,
                _JAVASCRIPT_APPLICATION_PREFIXES,
            )
        )
    )


def _path_edge_details(
    graph: ImportGraph,
    path: tuple[str, ...],
) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for source, target in zip(path, path[1:]):
        edge = graph.edge(source, target)
        details.append(
            {
                "source": source,
                "target": target,
                "path": edge.source_path if edge is not None else "",
                "line": edge.line if edge is not None else 1,
                "column": edge.column if edge is not None else 0,
                "kind": edge.kind if edge is not None else "unknown",
            }
        )
    return details


def _dependency_path_finding(
    *,
    root: Path,
    graph: ImportGraph,
    path: tuple[str, ...],
    code: str,
    message: str,
    source_layer: str,
    target: str,
) -> Finding:
    first = graph.edge(path[0], path[1])
    source_path = (
        first.source_path
        if first is not None
        else repository_path(graph.modules[path[0]].path, root)
    )
    line = first.line if first is not None else 1
    column = first.column if first is not None else 0
    rendered_path = " -> ".join(path)
    return Finding(
        code=code,
        severity="error",
        subject_type="python_module",
        subject_id=path[0],
        source_location=SourceLocation(source_path, line, column),
        message=f"{message}; shortest import path: {rendered_path}.",
        suggested_fix=(
            "Move the dependency behind the owning Target application boundary "
            "or pass plain data across the boundary."
        ),
        details={
            "source_layer": source_layer,
            "target": target,
            "dependency_path": list(path),
            "dependency_edges": _path_edge_details(graph, path),
        },
    )


def _application_cross_target_findings(
    root: Path,
    graph: ImportGraph,
    *,
    language: str,
) -> list[Finding]:
    if language == "python":
        roots = _python_application_modules(graph)
        forbidden_layer = "javascript-target"
    else:
        roots = _javascript_application_modules(graph)
        forbidden_layer = "python-target"
    findings: list[Finding] = []
    for module in roots:
        path = shortest_import_path(
            graph,
            module,
            lambda target: target_layer(target) == forbidden_layer,
        )
        if path is None:
            continue
        findings.append(
            _dependency_path_finding(
                root=root,
                graph=graph,
                path=path,
                code="APPLICATION_CROSS_TARGET",
                message=(
                    f"{language.capitalize()} Application may not depend on "
                    f"{forbidden_layer}"
                ),
                source_layer=f"{language}-application",
                target=path[-1],
            )
        )
    return findings


def _transitive_target_findings(
    root: Path,
    graph: ImportGraph,
    *,
    layer: str,
) -> list[Finding]:
    forbidden_layer = (
        "javascript-target" if layer == "python-target" else "python-target"
    )
    prefix = (
        "vibeflow.targets.python"
        if layer == "python-target"
        else "vibeflow.targets.javascript"
    )
    findings: list[Finding] = []
    for module in sorted(
        name
        for name in graph.modules
        if name == prefix or name.startswith(prefix + ".")
    ):
        path = shortest_import_path(
            graph,
            module,
            lambda target: target_layer(target) == forbidden_layer,
            minimum_edges=2,
        )
        if path is None:
            continue
        findings.append(
            _dependency_path_finding(
                root=root,
                graph=graph,
                path=path,
                code="TRANSITIVE_LAYER_DEPENDENCY",
                message=f"{layer} reaches {forbidden_layer} transitively",
                source_layer=layer,
                target=path[-1],
            )
        )
    return findings


def _javascript_python_symbol_findings(
    root: Path,
    graph: ImportGraph,
) -> list[Finding]:
    findings: list[Finding] = []
    for module in _javascript_application_modules(graph):
        record = graph.modules[module]
        if record.tree is None:
            continue
        occurrences: dict[str, ast.AST] = {}
        for node in ast.walk(record.tree):
            for symbol in _python_symbols(node):
                previous = occurrences.get(symbol)
                if previous is None or _node_location(node) < _node_location(previous):
                    occurrences[symbol] = node
        relative = repository_path(record.path, root)
        for symbol, node in sorted(occurrences.items()):
            findings.append(
                Finding(
                    code="JAVASCRIPT_APPLICATION_PYTHON_SYMBOL",
                    severity="error",
                    subject_type="python_module",
                    subject_id=module,
                    source_location=SourceLocation(
                        relative,
                        getattr(node, "lineno", 1),
                        getattr(node, "col_offset", 0),
                    ),
                    message=(
                        "JavaScript Application uses Python-specific symbol or "
                        f"module {symbol!r}."
                    ),
                    suggested_fix=(
                        "Replace the Python adapter with Core data, Block Compiler "
                        "IR, or a JavaScript Target binding."
                    ),
                    details={"symbol": symbol},
                )
            )
    return findings


def _python_symbols(node: ast.AST) -> set[str]:
    symbols: set[str] = set()
    if isinstance(node, ast.ImportFrom):
        if node.module and (
            node.module == "vibeflow.targets.python"
            or node.module.startswith("vibeflow.targets.python.")
            or any(
                part in _PYTHON_ONLY_MODULE_PARTS
                for part in node.module.split(".")
            )
        ):
            symbols.add(node.module)
        symbols.update(
            alias.name
            for alias in node.names
            if alias.name in _PYTHON_ONLY_SYMBOLS
        )
    elif isinstance(node, ast.Import):
        symbols.update(
            alias.name
            for alias in node.names
            if alias.name == "vibeflow.targets.python"
            or alias.name.startswith("vibeflow.targets.python.")
            or any(
                part in _PYTHON_ONLY_MODULE_PARTS
                for part in alias.name.split(".")
            )
        )
    elif isinstance(node, ast.Name) and node.id in _PYTHON_ONLY_SYMBOLS:
        symbols.add(node.id)
    elif isinstance(node, ast.Attribute) and node.attr in _PYTHON_ONLY_SYMBOLS:
        symbols.add(node.attr)
    return symbols


def _node_location(node: ast.AST) -> tuple[int, int]:
    return getattr(node, "lineno", 1), getattr(node, "col_offset", 0)


__all__ = [
    "javascript_application_findings",
    "neutral_tooling_findings",
    "python_application_findings",
]
