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
        self._projections = {}
        self._file_metrics = {}

    def _implementation_tree(self, sources, path, name):
        """Borrow this snapshot's AST nodes for read-only Target analysis."""
        key = (path, name)
        if key not in self._projections:
            source = sources.file(path)
            if not name:
                tree = source._tree
            else:
                symbol = sources.symbol(path, name)
                tree = self._project_implementation(sources, source, symbol) if symbol else None
            self._projections[key] = tree
        return self._projections[key]

    @staticmethod
    def _project_implementation(sources, source, symbol):
        selected, pending = set(), [symbol.id]
        pending.extend(item.id for item in sources.symbols
                       if item.path == source.path and item.name.startswith(symbol.name + "."))
        while pending:
            current = pending.pop()
            if current in selected:
                continue
            selected.add(current)
            pending.extend(item.target for item in sources.references if item.source == current)
        local = [item for item in sources.symbols if item.path == source.path and item.id in selected]
        # A selected class already contains its methods; do not traverse twice.
        classes = {item.name for item in local if item.kind == "class"}
        nodes = [item._node for item in local
                 if not any(item.name.startswith(owner + ".") for owner in classes)]
        used = {item.id for node in nodes for item in ast.walk(node) if isinstance(item, ast.Name)}
        imports = [item for item in (source._tree.body if source._tree else ())
                   if isinstance(item, (ast.Import, ast.ImportFrom))
                   and any((alias.asname or alias.name.split(".")[0]) in used for alias in item.names)]
        return ast.Module(body=[*imports, *nodes], type_ignores=[])

    def _measure_file(self, source):
        key = (source.path, source.text)
        if key not in self._file_metrics:
            self._file_metrics[key] = measure_tree(source._tree, source.text)[0]
        return self._file_metrics[key]

    def measurements(self, context):
        sources = context.facts.get("source_context")
        if sources is not None and sources._analysis is not self:
            return sources._analysis.measurements(context)
        if context.subject.get("kind") != "node":
            source = context.facts.get("resource_source_file") or context.require("base_lib_file")
            if source._tree is None:
                return None
            name = context.facts.get("resource_symbol", "")
            text = source.text
            from vibeflow.targets.python.project.source_membership import implementation_review_files
            closure = implementation_review_files(context)
            key = (context.subject.get("kind"), source.path, source.text, name,
                   tuple((file.path, file.text) for file in closure))
            if key not in self._cache:
                tree = source._tree if context.subject.get("kind") == "plugin_declaration" else self._implementation_tree(sources, source.path, name)
                if tree is None:
                    return None
                metrics, counter = measure_tree(tree, text)
                helpers = tuple((file.path,self._measure_file(file)) for file in closure if file.path != source.path and file._tree is not None)
                self._cache[key] = SourceMeasurements(metrics, source.path, 1, helpers=helpers,
                    function_names=tuple(counter.function_names), fingerprint=counter.run_pure_fingerprint,
                    shape=counter.run_pure_shape)
            return self._cache[key]
        sources = context.require("source_context")
        node = next(item for item in sources.nodes if item.type_key == context.subject["type_key"])
        symbol = sources.symbol(node.path, node.symbol)
        if symbol is None:
            return None
        from vibeflow.targets.python.project.source_membership import subject_files
        closure = subject_files(context)
        key = (node.path, node.symbol, json.dumps(node.descriptor.to_dict(), sort_keys=True),
               tuple((file.path, file.module, file.text) for file in closure))
        if key not in self._cache:
            source = sources.file(node.path)
            text = "\n".join(source.text.splitlines()[symbol.line - 1:symbol.end_line])
            metrics, counter = measure_tree(ast.Module(body=[symbol._node], type_ignores=[]), text,
                params=len(node.descriptor.contract.params_schema),
                contract_keys=len(node.descriptor.contract.requires) + len(node.descriptor.contract.provides))
            from dataclasses import replace
            metrics = replace(metrics,source_lines=len(source.text.splitlines()),source_bytes=len(source.text.encode()))
            implementation_paths = {item.path for item in sources.nodes}
            helper_paths = {item.path for item in sources.helpers(node.type_key)}
            helper_paths.update(item["path"] for item in context.facts.get("source_owners", ())
                if item["kind"] == "node" and item["id"] == node.type_key and item["role"] == "support")
            helpers = tuple(file for file in closure if file.path in helper_paths
                and file.path not in implementation_paths and file._tree is not None)
            by_path = {file.path: file for file in helpers}
            def dependencies(path):
                return tuple(dict.fromkeys(by_path[item.resolved_path].module for item in sources.imports
                    if item.path == path and item.resolved_path in by_path))
            starts = dependencies(node.path)
            graph = {file.module: dependencies(file.path) for file in helpers}
            graph["node"] = starts
            chain = analyze_call_graph(graph, entry="node") if starts else CallChain()
            helper_metrics = tuple((file.path, self._measure_file(file)) for file in helpers)
            self._cache[key] = SourceMeasurements(metrics, node.path, symbol.line, helper_metrics, chain, starts,
                tuple(counter.function_names), counter.run_pure_fingerprint, counter.run_pure_shape)
        return self._cache[key]
