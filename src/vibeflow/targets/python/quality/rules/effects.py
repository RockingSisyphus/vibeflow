"""An effect policy is a selected rule output, never a Node identity grant."""

import ast
from copy import copy

from vibeflow.core.rules import EFFECT_POLICY_TYPE, RuleRecord, RuleResult
from vibeflow.targets.python.quality.rules.helpers import finding, rule_effect_scope, source_info, source_policy, source_subject, violation_finding
from vibeflow.targets.python.quality.source_analysis.ast_rules import import_aliases, import_modules
from vibeflow.targets.python.quality.source_analysis.visitors import ModulePurityVisitor, NodePurityVisitor


def no_side_effects(context, inputs, params):
    scope = rule_effect_scope(params)
    policy = source_policy(params, sections=("imports",))
    policy_record = RuleRecord(EFFECT_POLICY_TYPE, {"effect_scope": scope, "source": "vibeflow.no_side_effects"})
    if context.subject.get("kind") == "python_source":
        from vibeflow.targets.python.quality.rules.project_effects import source_effect_findings
        sources = context.facts.get("python_sources")
        if sources is None:
            sources = ((context.require("python_source"), context.require("source_file")),)
        from vibeflow.targets.python.quality.source_context import build_python_source_context
        source_context = build_python_source_context((), (parsed for _, parsed in sources))
        return RuleResult(records={"effect_policy":policy_record},findings=tuple(
            finding for source, parsed in sources if parsed._tree is not None
            for finding in source_effect_findings(source, parsed._tree, policy=policy, effect_scope=scope,
                resolved_calls=source_context.resolved_function_calls(parsed.path))))
    if context.subject.get("kind") == "base_lib":
        from vibeflow.targets.python.quality.rules.base_lib_effects import _BaseLibEffectVisitor
        source = context.require("base_lib_file")
        if source._tree is None:
            return RuleResult(state="unavailable")
        sources = context.require("source_context")
        tree = sources._analysis._implementation_tree(sources, source.path, context.facts.get("resource_symbol", ""))
        if tree is None:
            return RuleResult(state="unavailable")
        scanner = _BaseLibEffectVisitor(path=source.path,module=source.module,policy=policy,effect_scope=scope,
            resolved_calls=context.require("source_context").resolved_function_calls(source.path))
        scanner.visit(tree)
        diagnostics = list(scanner.findings)
        from vibeflow.targets.python.project.source_membership import subject_files
        for helper in subject_files(context):
            if helper.path != source.path and helper._tree is not None:
                support_scanner = _BaseLibEffectVisitor(path=helper.path,module=helper.module,
                    policy=policy,effect_scope=scope,
                    resolved_calls=context.require("source_context").resolved_function_calls(helper.path))
                support_scanner.visit(helper._tree)
                diagnostics.extend(support_scanner.findings)
        return RuleResult(records={"effect_policy":policy_record},findings=tuple(finding(context,item.rule_id,item.message,
            path=str(item.source_location.get("path",source.path)),line=int(item.source_location.get("line",1)),column=int(item.source_location.get("column",1)),
            details=item.details) for item in diagnostics))
    if context.subject.get("kind") == "plugin":
        findings = []
        sources = context.require("source_context")
        from vibeflow.targets.python.project.source_membership import implementation_review_files
        for source in implementation_review_files(context):
            if source._tree is None:
                return RuleResult(state="unavailable")
            selected = source.path == context.require("resource_source_file").path
            tree = sources._analysis._implementation_tree(sources, source.path, context.facts.get("resource_symbol", "")) if selected else source._tree
            if tree is None:
                return RuleResult(state="unavailable")
            visitor = ModulePurityVisitor(policy=policy, source=source_info(source),
                node_class_name="", known_node_modules=(),
                audit_all_definitions=True, effect_scope=scope,
                resolved_calls=sources.resolved_function_calls(source.path))
            visitor.visit(tree)
            findings.extend(violation_finding(context,item) for item in visitor.violations)
        return RuleResult(records={"effect_policy":policy_record},findings=tuple(findings))
    sources, node, symbol = source_subject(context)
    if symbol is None or not isinstance(symbol._node, ast.ClassDef):
        return RuleResult(records={"effect_policy": policy_record}, state="unavailable")
    source = sources.file(node.path)
    other_nodes = tuple(item for item in context.facts.get("node_catalog",()) if item.type_key != node.type_key)
    coupling_calls, internal_reads = _node_coupling_sites(context, node)
    modules_by_path = {item.path: item.module for item in sources.files}
    known_modules = tuple(modules_by_path.get(implementation.source.ref,
        implementation.source.ref.removesuffix(".py").replace("/", "."))
        for item in other_nodes for implementation in item.implementations if implementation.language == "python")
    other_ids = {item.type_key for item in other_nodes}
    other_paths = {item["path"] for item in context.facts.get("source_owners", ())
                   if item["kind"] == "node" and item["id"] in other_ids and item["role"] == "entry"}
    known_modules += tuple(item.module for item in sources.imports if item.resolved_path in other_paths)
    from vibeflow.targets.python.quality.source_analysis.input_tracking import source_input_parameters
    input_parameters = source_input_parameters(sources,node)
    methods_by_path = {}
    for member in sources.class_members(symbol).values():
        methods_by_path.setdefault(member.path, []).append(member._node)
    methods_by_path.setdefault(node.path, [])
    violations = []
    for method_path, methods in methods_by_path.items():
        method_source = sources.file(method_path)
        visitor = NodePurityVisitor(
            policy=policy, source=source_info(method_source), contract=node.descriptor.contract,
            known_node_modules=known_modules, line_offset=0, effect_scope=scope,
            node_call_sites=coupling_calls.get(method_path, frozenset()), node_internal_read_sites=internal_reads.get(method_path, frozenset()),
            initial_aliases=import_aliases(method_source._tree), resolved_calls=sources.resolved_function_calls(method_source.path),
            authorized_resource_imports=_authorized_library_imports(context, method_source.path, node),
            imported_roots={module.split(".", 1)[0] for item in ast.walk(method_source._tree) if isinstance(item, (ast.Import, ast.ImportFrom)) for module in import_modules(item)},
            module_state_names={target.id for item in method_source._tree.body if isinstance(item,(ast.Assign,ast.AnnAssign)) for target in (item.targets if isinstance(item,ast.Assign) else (item.target,)) if isinstance(target, ast.Name)},
            input_parameters={item.name.rsplit(".",1)[-1]:input_parameters.get(item.id,set()) for item in sources.helpers(node.type_key) if item.path == method_source.path},
        )
        # Only the class shell is changed; borrowed methods remain read-only.
        selected_class = copy(symbol._node)
        selected_class.body = [*methods, *(item for item in selected_class.body
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and method_path == node.path)]
        visitor.visit(ast.Module(body=[selected_class], type_ignores=[]))
        violations.extend(visitor.violations)
    visitor = NodePurityVisitor(policy=policy, source=source_info(source),
        contract=node.descriptor.contract, known_node_modules=known_modules,
        line_offset=0, effect_scope=scope, authorized_resource_imports=_authorized_library_imports(context, source.path, node))
    referenced_names = {item.id for item in ast.walk(symbol._node) if isinstance(item,ast.Name)}
    package_file = any(item["path"] == source.path and item["kind"] == "plugin_declaration"
                       for item in context.facts.get("source_owners", ()))
    for statement in source._tree.body:
        if isinstance(statement,(ast.Import,ast.ImportFrom)):
            for module in import_modules(statement):
                if module in known_modules and (not package_file or any(
                    (alias.asname or alias.name.split(".")[0]) in referenced_names for alias in statement.names)):
                    visitor._check_import(module,statement)
    violations.extend(visitor.violations)
    helpers = sources.helpers(node.type_key)
    node_methods = {item.id for item in sources.class_members(symbol).values()}
    symbols_by_id = {item.id: item for item in sources.symbols}
    references_by_source = {}
    for reference in sources.references:
        references_by_source.setdefault(reference.source, set()).add(reference.target)
    for helper_source in sources.files:
        selected = [helper for helper in helpers if helper.path == helper_source.path and helper.kind == "function" and helper.id not in node_methods]
        globals_ = {helper.name for helper in helpers if helper.path == helper_source.path and helper.kind == "global"}
        support = any(item["kind"] == "node" and item["id"] == node.type_key and item["role"] == "support" and item["path"] == helper_source.path for item in context.facts.get("source_owners", ()))
        if (not selected and not globals_ and not support) or helper_source._tree is None:
            continue
        selected_functions = [helper._node for helper in selected]
        # Nested definitions are already visited inside their selected parent.
        # Keep their resolved module dependencies in the same source slice.
        selected_ast_ids = {id(item) for function in selected_functions for item in ast.walk(function)}
        pending = [item.id for item in sources.symbols if item.path == helper_source.path
                   and (id(item._node) in selected_ast_ids or item.kind == "global" and item.name in globals_)]
        visited = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            for target_id in references_by_source.get(current, ()):
                target = symbols_by_id[target_id]
                if target.path == helper_source.path and target.kind == "global":
                    globals_.add(target.name)
                    pending.append(target.id)
        used = {name.id for function in selected_functions for name in ast.walk(function) if isinstance(name,ast.Name)}
        for item in helper_source._tree.body:
            if (isinstance(item, ast.Assign) and any(isinstance(target, ast.Name) and target.id in globals_ for target in item.targets)
                    or isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.target.id in globals_):
                used.update(child.id for child in ast.walk(item) if isinstance(child, ast.Name))
        body = [item for item in helper_source._tree.body if
                isinstance(item,(ast.Import,ast.ImportFrom)) and any((alias.asname or alias.name.split(".")[0]) in used for alias in item.names)
                or isinstance(item,ast.Assign) and any(isinstance(target,ast.Name) and target.id in globals_ for target in item.targets)
                or isinstance(item,ast.AnnAssign) and isinstance(item.target,ast.Name) and item.target.id in globals_
                ]
        body.extend(selected_functions)
        helper_visitor = ModulePurityVisitor(policy=policy, source=source_info(helper_source),
                                            node_class_name="", known_node_modules=known_modules,
                                            node_call_sites=coupling_calls.get(helper_source.path, frozenset()), node_internal_read_sites=internal_reads.get(helper_source.path, frozenset()),
                                            effect_scope=scope, audit_all_definitions=True,
                                            authorized_resource_imports=_authorized_library_imports(context, helper_source.path, node),
                                            input_parameters={helper.name.rsplit(".",1)[-1]:input_parameters.get(helper.id,set()) for helper in helpers if helper.path == helper_source.path},
                                            resolved_calls=sources.resolved_function_calls(helper_source.path))
        helper_visitor.visit(helper_source._tree if support else ast.Module(body=body, type_ignores=[]))
        violations.extend(helper_visitor.violations)
    findings = [violation_finding(context, item) for item in violations]
    if scope == "none":
        from vibeflow.targets.python.quality.source_analysis.runtime_dispatch import analyze_source_runtime_dispatch
        dispatch = analyze_source_runtime_dispatch(sources, node)
        if dispatch is not None and dispatch.detected:
            first = dispatch.sites[0]
            findings.append(finding(context, "NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED",
                "runtime input supplies a callable whose effects are unknown to the selected source rule",
                path=first.path, line=first.line, column=first.column, severity="warning",
                details={"site_count":len(dispatch.sites), "sites":[site.to_dict() for site in dispatch.sites]}))
    return RuleResult(records={"effect_policy": policy_record}, findings=tuple(findings))


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
