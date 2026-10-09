"""Finite resource relations, selected separately from effects."""
import ast
from vibeflow.core.rules import RuleResult
from vibeflow.targets.python.quality.rules.helpers import source_subject, finding
from vibeflow.targets.python.quality.source_analysis.resource_slices import node_source_slices


def node_architecture(context, inputs, params):
    if context.subject.get("kind") != "node":
        return RuleResult()
    sources, node, symbol = source_subject(context)
    if symbol is None or not isinstance(symbol._node, ast.ClassDef):
        return RuleResult(state="unavailable")
    calls, reads = _node_coupling_sites(context, node)
    findings = {}
    for source, tree in node_source_slices(context, node, symbol):
        authorized = _authorized_library_imports(context, source.path, node)
        foreign = {item.path for item in sources.nodes if item.type_key != node.type_key}
        foreign.update(item["path"] for item in context.facts.get("source_owners", ())
            if item["kind"] == "node" and item["id"] != node.type_key and item["role"] == "entry")
        foreign_imports = {(item.line, item.module) for item in sources.imports
            if item.path == source.path and item.resolved_path in foreign} - authorized
        # A shared declaration file may import Nodes for Plugin.resources.
        # Its unrelated imports do not belong to this Node's source slice.
        shared = any(item["path"] == source.path and item["role"] == "entry"
                     and item["kind"] == "plugin"
                     for item in context.facts.get("source_owners", ()))
        expressions = list(ast.walk(tree))
        if not shared:
            expressions.extend(item for item in source._tree.body
                               if isinstance(item, (ast.Import, ast.ImportFrom)))
        for expression in expressions:
            position = (getattr(expression, "lineno", 1), getattr(expression, "col_offset", 0)+1)
            code = ""
            if isinstance(expression, ast.Call) and position in calls.get(source.path, ()):
                code = "NODE.METADATA.NODE_DIRECT_CALL"
            elif isinstance(expression, ast.Attribute) and position in reads.get(source.path, ()):
                code = "NODE.METADATA.NODE_INTERNAL_READ"
            elif isinstance(expression, (ast.Import, ast.ImportFrom)):
                modules = (expression.module,) if isinstance(expression, ast.ImportFrom) else tuple(item.name for item in expression.names)
                if any((position[0], module) in foreign_imports for module in modules):
                    code = "NODE.METADATA.NODE_IMPORT"
            if code:
                findings[(source.path, *position, code)] = finding(context, code,
                    "Node source must use declared workflow relations instead of another Node implementation",
                    path=source.path, line=position[0], column=position[1], suggested_fix_type="move_to_nodeset")
    return RuleResult(findings=tuple(findings.values()))


def _node_coupling_sites(context, node):
    """Use resolved symbols and canonical ownership, never an export's spelling."""
    sources = context.require("source_context")
    entries = {f"{item['path']}:{item['symbol']}" for item in context.facts.get("source_owners", ())
               if item["kind"] == "node" and item["id"] != node.type_key and item["role"] == "entry" and item.get("symbol")}
    entries.update(f"{item.path}:{item.symbol}" for item in sources.nodes if item.type_key != node.type_key)
    def foreign(target):
        return any(target == entry or target.startswith(entry + ".") for entry in entries)
    calls, reads = {}, {}
    for reference in sources.references:
        if not foreign(reference.target):
            continue
        path = reference.source.rpartition(":")[0]
        destination = calls if reference.kind in {"call", "receiver"} else reads if reference.kind == "member_reference" else None
        if destination is not None:
            destination.setdefault(path, set()).add((reference.line, reference.column))
    return ({path:frozenset(sites) for path,sites in calls.items()},
            {path:frozenset(sites) for path,sites in reads.items()})


def _authorized_library_imports(context, path, node):
    """Named library exports do not become Nodes because they share a file."""
    owners = context.facts.get("source_owners", ())
    selected = set(node.descriptor.base_libs)
    imports = {}
    for imported in context.require("source_context").imports:
        if imported.path != path:
            continue
        token = imported.symbol.split(".")[0]
        candidates = [item for item in owners if item["path"] == imported.resolved_path]
        foreign_node = any(item["kind"] == "node" and item["id"] != node.type_key and item.get("symbol", "").split(".")[0] == token for item in candidates)
        allowed = bool(token and token != "*" and not foreign_node and any(
            item["kind"] == "base_lib" and item["id"] in selected and
            (not item.get("symbol") or item["symbol"].split(".")[0] == token) for item in candidates))
        key = (imported.line, imported.module)
        imports[key] = imports.get(key, True) and allowed
    return {key for key, allowed in imports.items() if allowed}
