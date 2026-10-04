"""An effect policy is a selected rule output, never a Node identity grant."""

import ast

from vibeflow.core.rules import EFFECT_POLICY_TYPE, RuleRecord, RuleResult
from vibeflow.targets.python.quality.rules.helpers import finding, source_info, source_policy, source_subject, violation_finding
from vibeflow.targets.python.quality.source_analysis.ast_rules import import_aliases, import_modules
from vibeflow.targets.python.quality.source_analysis.visitors import ModulePurityVisitor, NodePurityVisitor


def no_side_effects(context, inputs, params):
    scope = str(params.get("effect_scope", "none"))
    policy_record = RuleRecord(EFFECT_POLICY_TYPE, {"effect_scope": scope, "source": "vibeflow.no_side_effects"})
    if context.subject.get("kind") == "python_source":
        from vibeflow.targets.python.quality.rules.project_effects import source_effect_findings
        return RuleResult(records={"effect_policy":policy_record},findings=tuple(source_effect_findings(
            context.require("python_source"),context.require("source_file").tree)))
    if context.subject.get("kind") == "base_lib":
        from vibeflow.targets.python.quality.rules.base_lib_effects import _BaseLibAstScanner
        source = context.require("base_lib_file")
        if source.tree is None:
            return RuleResult(state="unavailable")
        tree = context.require("source_context").implementation_tree(source.path, context.facts.get("resource_symbol", ""))
        if tree is None:
            return RuleResult(state="unavailable")
        scanner = _BaseLibAstScanner(path=source.path,module=source.module,policy=source_policy(context,params),effect_scope=scope)
        scanner.visit(tree)
        diagnostics = list(scanner.findings)
        from vibeflow.targets.python.project.source_membership import subject_files
        for helper in subject_files(context):
            if helper.path != source.path and helper.tree is not None:
                support_scanner = _BaseLibAstScanner(path=helper.path,module=helper.module,
                    policy=source_policy(context,params),effect_scope=scope)
                support_scanner.visit(helper.tree)
                diagnostics.extend(support_scanner.findings)
        return RuleResult(records={"effect_policy":policy_record},findings=tuple(finding(context,item.rule_id,item.message,
            path=str(item.source_location.get("path",source.path)),line=int(item.source_location.get("line",1)),column=int(item.source_location.get("column",1)),
            details=item.details) for item in diagnostics))
    if context.subject.get("kind") == "plugin":
        findings = []
        sources = context.require("source_context")
        from vibeflow.targets.python.project.source_membership import implementation_review_files
        for source in implementation_review_files(context):
            if source.tree is None:
                return RuleResult(state="unavailable")
            selected = source.path == context.require("resource_source_file").path
            tree = sources.implementation_tree(source.path, context.facts.get("resource_symbol", "")) if selected else source.tree
            if tree is None:
                return RuleResult(state="unavailable")
            visitor = ModulePurityVisitor(policy=source_policy(context,params), source=source_info(source),
                node_class_name="", known_node_modules=(), known_node_class_names=(),
                audit_all_definitions=True, effect_scope=scope)
            visitor.visit(tree)
            findings.extend(violation_finding(context,item) for item in visitor.violations)
        return RuleResult(records={"effect_policy":policy_record},findings=tuple(findings))
    sources, node, symbol = source_subject(context)
    if symbol is None or not isinstance(symbol.node, ast.ClassDef):
        return RuleResult(records={"effect_policy": policy_record}, state="unavailable")
    source = sources.file(node.path)
    other_nodes = tuple(item for item in context.facts.get("node_catalog",()) if item.type_key != node.type_key)
    known_classes = tuple(implementation.source.export.split(".")[-1] for item in other_nodes for implementation in item.implementations if implementation.language == "python" and implementation.source.export)
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
    visitor = NodePurityVisitor(
        policy=source_policy(context,params), source=source_info(source, symbol), contract=node.descriptor.contract,
        known_node_modules=known_modules, known_node_class_names=known_classes, line_offset=0, effect_scope=scope,
        initial_aliases=import_aliases(source.tree),
        authorized_resource_imports=_authorized_library_imports(context, source.path, node),
        imported_roots={module.split(".", 1)[0] for item in ast.walk(source.tree) if isinstance(item, (ast.Import, ast.ImportFrom)) for module in import_modules(item)},
        module_state_names={target.id for item in source.tree.body if isinstance(item,(ast.Assign,ast.AnnAssign)) for target in (item.targets if isinstance(item,ast.Assign) else (item.target,)) if isinstance(target, ast.Name)},
        input_parameters={item.name.rsplit(".",1)[-1]:input_parameters.get(item.id,set()) for item in sources.helpers(node.type_key) if item.path == node.path and item.name.startswith(node.symbol+".")},
    )
    referenced_names = {item.id for item in ast.walk(symbol.node) if isinstance(item,ast.Name)}
    package_file = any(item["path"] == source.path and item["kind"] == "plugin_declaration"
                       for item in context.facts.get("source_owners", ()))
    for statement in source.tree.body:
        if isinstance(statement,(ast.Import,ast.ImportFrom)):
            for module in import_modules(statement):
                if module in known_modules and (not package_file or any(
                    (alias.asname or alias.name.split(".")[0]) in referenced_names for alias in statement.names)):
                    visitor._check_import(module,statement)
    visitor.visit(ast.Module(body=[symbol.node], type_ignores=[]))
    violations = list(visitor.violations)
    helpers = sources.helpers(node.type_key)
    for helper_source in sources.files:
        selected = {helper.name for helper in helpers if helper.path == helper_source.path and "." not in helper.name}
        globals_ = {helper.name for helper in helpers if helper.path == helper_source.path and helper.kind == "global"}
        support = any(item["kind"] == "node" and item["id"] == node.type_key and item["role"] == "support" and item["path"] == helper_source.path for item in context.facts.get("source_owners", ()))
        if (not selected and not support) or helper_source.tree is None:
            continue
        selected_functions = [item for item in helper_source.tree.body if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)) and item.name in selected]
        used = {name.id for function in selected_functions for name in ast.walk(function) if isinstance(name,ast.Name)}
        body = [item for item in helper_source.tree.body if
                isinstance(item,(ast.Import,ast.ImportFrom)) and any((alias.asname or alias.name.split(".")[0]) in used for alias in item.names)
                or isinstance(item,ast.Assign) and any(isinstance(target,ast.Name) and target.id in globals_ for target in item.targets)
                or isinstance(item,ast.AnnAssign) and isinstance(item.target,ast.Name) and item.target.id in globals_
                or isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)) and item.name in selected]
        helper_visitor = ModulePurityVisitor(policy=source_policy(context,params), source=source_info(helper_source),
                                            node_class_name="", known_node_modules=known_modules, known_node_class_names=known_classes,
                                            effect_scope=scope, audit_all_definitions=True,
                                            authorized_resource_imports=_authorized_library_imports(context, helper_source.path, node),
                                            input_parameters={helper.name:input_parameters.get(helper.id,set()) for helper in helpers if helper.path == helper_source.path})
        helper_visitor.visit(helper_source.tree if support else ast.Module(body=body, type_ignores=[]))
        violations.extend(helper_visitor.violations)
    findings = [violation_finding(context, item) for item in violations]
    from vibeflow.targets.python.quality.rules.base_lib_effects import _BaseLibAstScanner
    library_paths = {helper.path for helper in helpers if "base_lib" in sources.file(helper.path).module.split(".")}
    for path in sorted(library_paths):
        library = sources.file(path)
        scanner = _BaseLibAstScanner(path=library.path,module=library.module,policy=source_policy(context,params),effect_scope=scope)
        scanner.visit(library.tree)
        for item in scanner.findings:
            findings.append(finding(context,item.rule_id,item.message,path=path,line=int(item.source_location.get("line",1)),
                column=int(item.source_location.get("column",1)),details=item.details))
        if scanner.findings:
            findings.append(finding(context,"NODE.BASE_LIB.INDIRECT_VIOLATION",
                f"Node references a library that violates the selected effect rule: {library.module}",
                path=node.path,line=symbol.line,details={"module":library.module,"findings":[item.rule_id for item in scanner.findings]}))
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
