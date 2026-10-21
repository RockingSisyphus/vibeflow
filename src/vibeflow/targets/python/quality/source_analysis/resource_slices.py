"""Borrow resource-owned source slices from the existing SourceContext."""
import ast
from copy import copy


def node_source_slices(context, node, symbol):
    sources = context.require("source_context")
    helpers = sources.helpers(node.definition_id)
    methods = sources.class_members(symbol)
    by_path = {}
    for member in methods.values():
        by_path.setdefault(member.path, []).append(member._node)
    by_path.setdefault(node.path, [])
    for path, members in by_path.items():
        source = sources.file(path)
        shell = copy(symbol._node)
        shell.body = [*members, *(item for item in symbol._node.body
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and path == node.path)]
        used = {item.id for item in ast.walk(shell) if isinstance(item, ast.Name)}
        imports = [item for item in source._tree.body if isinstance(item, (ast.Import, ast.ImportFrom))
            and any((alias.asname or alias.name.split(".")[0]) in used for alias in item.names)]
        globals_ = [helper._node for helper in helpers if helper.path == path and helper.kind == "global"]
        yield source, ast.Module(body=[*imports, *globals_, shell], type_ignores=[])
    method_ids = {member.id for member in methods.values()}
    for source in sources.files:
        support = any(item["kind"] == "node" and item["id"] == node.definition_id
            and item["role"] == "support" and item["path"] == source.path
            for item in context.facts.get("source_owners", ()))
        if support:
            yield source, source._tree
            continue
        selected = [item for item in helpers if item.path == source.path and item.id not in method_ids
            and item.kind in {"function", "global"}]
        covered = set()
        body = []
        for helper in selected:
            projected = sources._analysis._implementation_tree(sources, source.path, helper.name)
            if projected is None:
                continue
            for statement in projected.body:
                if id(statement) not in covered:
                    body.append(statement)
                    covered.update(id(item) for item in ast.walk(statement))
        if body:
            yield source, ast.Module(body=body, type_ignores=[])
