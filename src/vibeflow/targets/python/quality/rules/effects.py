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
        scanner = _BaseLibAstScanner(path=source.path,module=source.module,policy=source_policy(context,params),effect_scope=scope)
        scanner.visit(source.tree)
        return RuleResult(records={"effect_policy":policy_record},findings=tuple(finding(context,item.rule_id,item.message,
            path=source.path,line=int(item.source_location.get("line",1)),column=int(item.source_location.get("column",1)),
            details=item.details) for item in scanner.findings))
    if context.subject.get("kind") == "plugin":
        findings = []
        for source in context.require("source_context").files:
            if source.tree is None:
                return RuleResult(state="unavailable")
            visitor = ModulePurityVisitor(policy=source_policy(context,params), source=source_info(source),
                node_class_name="", known_node_modules=(), known_node_class_names=(),
                audit_all_definitions=True, effect_scope=scope)
            visitor.visit(source.tree)
            findings.extend(violation_finding(context,item) for item in visitor.violations)
        return RuleResult(records={"effect_policy":policy_record},findings=tuple(findings))
    sources, node, symbol = source_subject(context)
    if symbol is None or not isinstance(symbol.node, ast.ClassDef):
        return RuleResult(records={"effect_policy": policy_record}, state="unavailable")
    source = sources.file(node.path)
    other_nodes = tuple(item for item in context.facts.get("node_catalog",()) if item.type_key != node.type_key)
    known_classes = tuple(implementation.source.export.split(".")[-1] for item in other_nodes for implementation in item.implementations if implementation.language == "python" and implementation.source.export)
    known_modules = tuple(implementation.source.ref.removesuffix(".py").replace("/",".") for item in other_nodes for implementation in item.implementations if implementation.language == "python")
    from vibeflow.targets.python.quality.source_analysis.input_tracking import source_input_parameters
    input_parameters = source_input_parameters(sources,node)
    visitor = NodePurityVisitor(
        policy=source_policy(context,params), source=source_info(source, symbol), contract=node.descriptor.contract,
        known_node_modules=known_modules, known_node_class_names=known_classes, line_offset=0, effect_scope=scope,
        initial_aliases=import_aliases(source.tree),
        imported_roots={module.split(".", 1)[0] for item in ast.walk(source.tree) if isinstance(item, (ast.Import, ast.ImportFrom)) for module in import_modules(item)},
        module_state_names={target.id for item in source.tree.body if isinstance(item,(ast.Assign,ast.AnnAssign)) for target in (item.targets if isinstance(item,ast.Assign) else (item.target,)) if isinstance(target, ast.Name)},
        input_parameters={item.name.rsplit(".",1)[-1]:input_parameters.get(item.id,set()) for item in sources.helpers(node.type_key) if item.path == node.path and item.name.startswith(node.symbol+".")},
    )
    for statement in source.tree.body:
        if isinstance(statement,(ast.Import,ast.ImportFrom)):
            for module in import_modules(statement):
                if module in known_modules:
                    visitor._check_import(module,statement)
    visitor.visit(ast.Module(body=[symbol.node], type_ignores=[]))
    violations = list(visitor.violations)
    helpers = sources.helpers(node.type_key)
    for helper_source in sources.files:
        selected = {helper.name for helper in helpers if helper.path == helper_source.path and "." not in helper.name}
        globals_ = {helper.name for helper in helpers if helper.path == helper_source.path and helper.kind == "global"}
        if not selected or helper_source.tree is None:
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
                                            input_parameters={helper.name:input_parameters.get(helper.id,set()) for helper in helpers if helper.path == helper_source.path})
        helper_visitor.visit(ast.Module(body=body, type_ignores=[]))
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
