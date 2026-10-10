"""Project private Target analysis into a single Node's public source view."""
import ast
from copy import deepcopy
from dataclasses import replace

from vibeflow.core.rules import RuleContext
from vibeflow.targets.python.quality.source_context import PythonSourceContext


def local_sources(sources, node, call=None):
    root = sources.symbol(node.path, node.symbol)
    selected = {item.id for item in sources.symbols
                if item.path == node.path and (item.name == node.symbol or item.name.startswith(node.symbol + "."))}
    selected.update(item.id for item in sources.helpers(node.type_key))
    if root is not None:
        selected.update(item.id for item in sources.class_members(root).values())
    # Inherited methods are part of this implementation even when the base
    # also has its own Node declaration. Retain only its selected members.
    inherited = {item.id for item in sources.class_members(root).values()} if root is not None else set()
    ancestors = {(item.path, item.name.rpartition(".")[0]) for item in sources.symbols
        if item.id in inherited and not item.name.startswith(node.symbol + ".")}
    selected.update(item.id for item in sources.symbols if (item.path, item.name) in ancestors)
    foreign = tuple((item.path, item.symbol) for item in sources.nodes if item.type_key != node.type_key
        and (item.path, item.symbol) not in ancestors)
    symbols = tuple(item for item in sources.symbols if item.id in selected and not any(
        item.path == path and (item.name == name or item.name.startswith(name + ".")) for path, name in foreign))
    identities = {item.id for item in symbols}
    files = []
    imports = []
    for source in sources.files:
        own = [item for item in symbols if item.path == source.path]
        if not own:
            continue
        classes = {item.name for item in own if item.kind == "class"}
        body = []
        for item in own:
            if any(item.name.startswith(name + ".") for name in classes):
                continue
            statement = deepcopy(item._node)
            if (item.path, item.name) in ancestors and isinstance(statement, ast.ClassDef):
                retained = {(symbol._node.lineno, symbol._node.col_offset) for symbol in own
                    if symbol.name.startswith(item.name + ".")}
                statement.body = [child for child in statement.body if (child.lineno, child.col_offset) in retained]
                node_names = {"node", *(alias.asname or alias.name for declaration in source._tree.body
                    if isinstance(declaration, ast.ImportFrom) and declaration.module
                    and declaration.module.startswith("vibeflow.targets.python.sdk")
                    for alias in declaration.names if alias.name == "node")}
                statement.decorator_list = [decorator for decorator in statement.decorator_list
                    if not isinstance(decorator, ast.Call) or not (
                        isinstance(decorator.func, ast.Name) and decorator.func.id in node_names
                        or isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "node")]
            body.append(statement)
        used = {item.id for statement in body for item in ast.walk(statement) if isinstance(item, ast.Name)}
        relevant_imports = [item for item in (source._tree.body if source._tree else ())
            if isinstance(item, (ast.Import, ast.ImportFrom)) and any(
                (alias.asname or alias.name.split(".")[0]) in used for alias in item.names)]
        body = [*deepcopy(relevant_imports), *body]
        lines = source.text.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        spans = []
        def position(line, column):
            return offsets[line - 1] + len(lines[line - 1].encode("utf-8")[:column].decode("utf-8", errors="ignore"))
        def span(statement):
            start = position(statement.lineno, statement.col_offset)
            end = position(getattr(statement, "end_lineno", statement.lineno), getattr(statement, "end_col_offset", 0))
            spans.append((start, end))
            for decorator in getattr(statement, "decorator_list", ()):
                # Include the @ preceding the expression.
                span(decorator)
                spans.append((offsets[decorator.lineno - 1] + max(0, decorator.col_offset - 1), start))
        for statement in body:
            if isinstance(statement, ast.ClassDef) and any((source.path, name) in ancestors and name == statement.name for name in classes):
                spans.append((offsets[statement.lineno - 1] + statement.col_offset,
                    offsets[min(child.lineno for symbol in own if symbol.name == statement.name for child in symbol._node.body) - 1]))
                for child in statement.body:
                    span(child)
                for decorator in statement.decorator_list:
                    span(decorator)
                    spans.append((offsets[decorator.lineno - 1] + max(0, decorator.col_offset - 1), position(decorator.lineno, decorator.col_offset)))
            else:
                span(statement)
        stop = max((end for _,end in spans), default=0)
        visible = bytearray(stop)
        for start,end in spans:
            visible[start:end] = bytes([1]) * (end - start)
        text = "".join(char if visible[index] or char in "\r\n" else " "
            for index,char in enumerate(source.text[:stop])) + "\n"
        visible_lines = {index + 1 for index,line in enumerate(text.splitlines()) if line.strip()}
        projected = {statement.name:statement for statement in body if isinstance(statement, ast.ClassDef)}
        symbols = tuple(replace(symbol, _node=projected[symbol.name]) if (symbol.path,symbol.name) in ancestors and symbol.path == source.path else symbol for symbol in symbols)
        files.append(replace(source, text=text, _tree=ast.Module(body=body, type_ignores=[])))
        imports.extend(item for item in sources.imports if item.path == source.path and item.line in visible_lines)
    return PythonSourceContext((replace(node, calls=()),), tuple(files), symbols,
        tuple(item for item in sources.references if item.source in identities),
        tuple(item for item in sources.ownership if item.type_key == node.type_key and item.symbol_id in identities),
        (), tuple(imports))


def node_context(sources, node, call, *, phase, identity, extra_facts=None, local=None):
    local = local if local is not None else local_sources(sources, node, call)
    facts = {"source_context": local}
    if call is not None:
        facts["call"] = call
    # Explicit adapter facts may describe this Node; never expose shared catalogs.
    facts.update(extra_facts or {})
    return RuleContext(facts=facts, subject={"kind": "node", "type_key": node.type_key,
        "descriptor": node.descriptor, "source_identity": identity,
        **({"owner": call.owner, "call_id": call.node_id, "call_path": call.call_path} if call is not None else {})},
        scope={"files": tuple(item.path for item in local.files)}, phase=phase, target="python")


def bind_native_analysis(handlers, native, private_context):
    """Native language analysis retains private services outside public facts."""
    from functools import wraps
    from inspect import unwrap
    result = dict(handlers)
    for key, handler in handlers.items():
        if key not in native or unwrap(native[key]) is not unwrap(handler):
            continue
        @wraps(handler)
        def analyze(context, inputs, params, *, check=handler):
            # Services analyse the real import operation and canonical ownership;
            # their output is ordinary portable diagnostics/metrics, never facts.
            active = private_context
            if "call" not in context.facts:
                active = replace(active, facts={key:value for key,value in active.facts.items() if key != "call"})
            return check(replace(active, phase=context.phase,
                subject={**{key:value for key,value in private_context.subject.items() if key in context.subject},
                    **({"rule_call_id":context.subject["rule_call_id"]} if "rule_call_id" in context.subject else {})}), inputs, params)
        result[key] = analyze
    return result


def graph_sources(sources, subjects):
    """Responsibility view; the complete command snapshot remains background."""
    if sources is None:
        return None
    types = {node.type_used for subject in subjects for node in subject.graph.nodes}
    nodes = tuple(node for node in sources.nodes if node.type_key in types)
    paths = {file.path for node in nodes for file in sources.import_closure(node.path)}
    calls = {(*subject.call_path,node.id) for subject in subjects for node in subject.graph.nodes}
    return PythonSourceContext(nodes, tuple(file for file in sources.files if file.path in paths),
        tuple(symbol for symbol in sources.symbols if symbol.path in paths),
        tuple(reference for reference in sources.references if reference.source.rpartition(":")[0] in paths),
        tuple(owner for owner in sources.ownership if owner.type_key in types),
        tuple(call for call in sources.calls if call.call_path in calls),
        tuple(item for item in sources.imports if item.path in paths))
