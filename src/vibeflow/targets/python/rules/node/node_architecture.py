"""Finite resource relations, selected separately from effects."""
import ast
from vibeflow.core.rules import RuleResult
from vibeflow.targets.python.rules.node.helpers import source_subject, finding
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
        expressions = ast.walk(tree)
        for expression in expressions:
            position = (getattr(expression, "lineno", 1), getattr(expression, "col_offset", 0)+1)
            code = ""
            if isinstance(expression, ast.Call) and position in calls.get(source.path, ()):
                code = "NODE.METADATA.NODE_DIRECT_CALL"
            elif isinstance(expression, ast.Attribute) and position in reads.get(source.path, ()):
                code = "NODE.METADATA.NODE_INTERNAL_READ"
            if code:
                findings[(source.path, *position, code)] = finding(context, code,
                    "Node source must use declared workflow relations instead of another Node implementation",
                    path=source.path, line=position[0], column=position[1], suggested_fix_type="move_to_nodeset")
    return RuleResult(findings=tuple(findings.values()))


def _node_coupling_sites(context, node):
    """Use resolved symbols and canonical ownership, never an export's spelling."""
    sources = context.require("source_context")
    entries = {f"{item['path']}:{item['symbol']}" for item in context.facts.get("source_owners", ())
               if item["kind"] == "node" and item["id"] != node.definition_id and item["role"] == "entry" and item.get("symbol")}
    entries.update(f"{item.path}:{item.symbol}" for item in sources.nodes if item.definition_id != node.definition_id)
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
