"""Reusable measurements over the Target's resolved, immutable source snapshot."""

from dataclasses import dataclass
import ast
import json

from vibeflow.core.quality.implementation import CallChain, ImplementationMetrics, analyze_call_graph
from vibeflow.targets.python.quality.source_analysis.metrics import _ComplexityCounter, _analyze_internal_call_chain


@dataclass(frozen=True)
class SourceMeasurements:
    metrics: ImplementationMetrics
    path: str
    line: int
    helpers: tuple[tuple[str, ImplementationMetrics], ...] = ()
    dependency_chain: CallChain = CallChain()
    imported_modules: tuple[str, ...] = ()
    function_names: tuple[str, ...] = ()
    fingerprint: str = ""
    shape: str = ""


def measure_tree(tree, text, *, params=0, contract_keys=0):
    counter = _ComplexityCounter()
    counter.visit(tree)
    chain = _analyze_internal_call_chain(tree)
    metrics = ImplementationMetrics(source_lines=len(text.splitlines()), source_bytes=len(text.encode()),
        function_count=counter.function_count, branch_count=counter.branch_count,
        max_nesting_depth=counter.max_nesting_depth, param_count=params, contract_key_count=contract_keys,
        call_chain=CallChain(chain.length, chain.path, chain.recursive_paths))
    return metrics, counter


class PythonSourceAnalysis:
    """One check's measurement cache; policy decisions remain in Rule handlers."""

    def __init__(self):
        self._cache = {}

    def measurements(self, context):
        if context.subject.get("kind") == "base_lib":
            source = context.require("base_lib_file")
            if source.tree is None:
                return None
            name = context.facts.get("resource_symbol", "")
            tree = context.require("source_context").implementation_tree(source.path, name)
            if tree is None:
                return None
            symbol = context.require("source_context").symbol(source.path, name) if name else None
            text = "\n".join(source.text.splitlines()[symbol.line-1:symbol.end_line]) if symbol else source.text
            key = ("base_lib", source.path, source.text, name)
            if key not in self._cache:
                metrics, counter = measure_tree(tree, text)
                self._cache[key] = SourceMeasurements(metrics, source.path, symbol.line if symbol else 1,
                    function_names=tuple(counter.function_names), fingerprint=counter.run_pure_fingerprint,
                    shape=counter.run_pure_shape)
            return self._cache[key]
        sources = context.require("source_context")
        if sources._analysis is not self:
            return sources._analysis.measurements(context)
        node = next(item for item in sources.nodes if item.type_key == context.subject["type_key"])
        symbol = sources.symbol(node.path, node.symbol)
        if symbol is None:
            return None
        closure = sources.import_closure(node.path)
        key = (node.path, node.symbol, json.dumps(node.descriptor.to_dict(), sort_keys=True),
               tuple((file.path, file.module, file.text) for file in closure))
        if key not in self._cache:
            source = sources.file(node.path)
            text = "\n".join(source.text.splitlines()[symbol.line - 1:symbol.end_line])
            metrics, counter = measure_tree(ast.Module(body=[symbol.node], type_ignores=[]), text,
                params=len(node.descriptor.contract.params_schema),
                contract_keys=len(node.descriptor.contract.requires) + len(node.descriptor.contract.provides))
            implementation_paths = {item.path for item in sources.nodes}
            helpers = tuple(file for file in closure if file.path not in implementation_paths and file.tree is not None)
            by_path = {file.path: file for file in helpers}
            def dependencies(path):
                return tuple(dict.fromkeys(by_path[item.resolved_path].module for item in sources.imports
                    if item.path == path and item.resolved_path in by_path))
            starts = dependencies(node.path)
            graph = {file.module: dependencies(file.path) for file in helpers}
            graph["node"] = starts
            chain = analyze_call_graph(graph, entry="node") if starts else CallChain()
            helper_metrics = tuple((file.path, measure_tree(file.tree, file.text)[0]) for file in helpers)
            self._cache[key] = SourceMeasurements(metrics, node.path, symbol.line, helper_metrics, chain, starts,
                tuple(counter.function_names), counter.run_pure_fingerprint, counter.run_pure_shape)
        return self._cache[key]
