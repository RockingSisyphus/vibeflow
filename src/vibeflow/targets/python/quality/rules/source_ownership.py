"""Check actual local import edges against fixed, selected resource declarations."""
import ast
from collections import deque

from vibeflow.targets.python.project.source_membership import subject_files
from vibeflow.targets.python.quality.rules.helpers import finding


def ownership_findings(context):
    owners = context.facts.get("source_owners")
    if owners is None:
        return ()
    sources = context.require("source_context")
    kind = context.subject.get("kind", "node")
    resource_id = context.subject.get("type_key", context.subject.get("id", ""))
    paths = {file.path for file in subject_files(context)}
    contributed = {(item["kind"],item["id"]) for item in context.facts.get("declarations", ())
                   if item.get("origin", {}).get("plugin_id") == resource_id}
    own_sources = [item for item in owners if item["kind"] == kind and item["id"] == resource_id and item["path"] in paths]
    fallback = {"kind":kind,"id":resource_id,"base_libs":[],"dependencies":[]}
    pending = deque((item,item["path"]) for item in own_sources)
    if not pending:
        pending.extend((fallback,path) for path in paths)
    visited = set()
    findings = []
    while pending:
        own,path = pending.popleft()
        key = (own["kind"],own["id"],path,own.get("role"),own.get("symbol"))
        if key in visited:
            continue
        visited.add(key)
        implementation = sources._analysis._implementation_tree(sources,path,own.get("symbol","")) if own.get("role") == "entry" and own["kind"] in {"node","plugin"} else None
        referenced = {item.id for item in ast.walk(implementation) if isinstance(item,ast.Name)} if implementation else None
        if referenced is not None:
            referenced.update(alias.asname or alias.name.split(".")[0]
                for statement in ast.walk(implementation) if isinstance(statement,(ast.Import,ast.ImportFrom))
                for alias in statement.names)
        for imported in sources.imports:
            if imported.path != path or not imported.resolved_path or imported.resolved_path not in paths:
                continue
            destinations = _destination_owners(owners, imported, own)
            if referenced is not None and (imported.alias or imported.symbol or imported.module.split(".")[0]) not in referenced and (destinations or own["kind"] == "plugin"):
                continue
            allowed = bool(destinations) and all(_allowed(own,item,contributed) for item in destinations)
            if not allowed:
                code = "VF_IMPORT_LAYER" if destinations else "VF_IMPORT_OWNER"
                findings.append(finding(context, code,
                    f"{own['kind']} '{own['id']}' imports {'a resource outside its declared dependencies' if destinations else 'unregistered local source'}: {imported.resolved_path}",
                    path=imported.path, line=imported.line, column=imported.column,
                    details={"destination":imported.resolved_path,"owners":destinations}))
            if allowed:
                pending.extend((item,imported.resolved_path) for item in destinations)
            elif not destinations:
                pending.append((own,imported.resolved_path))
    return tuple(findings)


def _destination_owners(owners, imported, own):
    candidates = [item for item in owners if item["path"] == imported.resolved_path]
    same = [item for item in candidates if item["kind"] == own["kind"] and item["id"] == own["id"]]
    if same:
        return same
    symbol = imported.symbol.split(".")[0]
    named = [item for item in candidates if item.get("symbol") and item["symbol"].split(".")[0] == symbol]
    return named or candidates


def _allowed(own, destination, contributed):
    return (destination["kind"] == own["kind"] and destination["id"] == own["id"]
        or destination["kind"] == "base_lib" and destination["id"] in (*own["base_libs"],*own["dependencies"])
        or own["kind"] == "plugin_declaration" and (destination["kind"],destination["id"]) in contributed)
