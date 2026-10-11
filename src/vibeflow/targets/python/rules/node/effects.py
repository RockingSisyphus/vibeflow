"""An effect policy is a selected rule output, never a Node identity grant."""

import ast

from vibeflow.targets.shared.rule_support.effect_records import EFFECT_POLICY_TYPE
from vibeflow.core.rules import RuleRecord, RuleResult
from vibeflow.targets.python.rules.node.helpers import finding, rule_effect_scope, source_info, source_policy, source_subject, violation_finding
from vibeflow.targets.python.rules.node.effect_visitors import ModulePurityVisitor


def no_side_effects(context, inputs, params):
    scope = rule_effect_scope(params)
    policy = source_policy(params, sections=("imports",))
    policy_record = RuleRecord(EFFECT_POLICY_TYPE, {"effect_scope": scope, "source": "vibeflow.no_side_effects"})
    if context.subject.get("kind") == "python_source":
        from vibeflow.targets.python.rules.node.project_effects import source_effect_findings
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
        from vibeflow.targets.python.rules.node.base_lib_effects import _BaseLibEffectVisitor
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
                node_class_name="",
                audit_all_definitions=True, effect_scope=scope,
                resolved_calls=sources.resolved_function_calls(source.path))
            visitor.visit(tree)
            findings.extend(violation_finding(context,item) for item in visitor.violations)
        return RuleResult(records={"effect_policy":policy_record},findings=tuple(findings))
    sources, node, symbol = source_subject(context)
    if symbol is None or not isinstance(symbol._node, ast.ClassDef):
        return RuleResult(records={"effect_policy": policy_record}, state="unavailable")
    from vibeflow.targets.python.quality.source_analysis.resource_slices import node_source_slices
    violations = []
    for source, tree in node_source_slices(context, node, symbol):
        visitor = ModulePurityVisitor(policy=policy, source=source_info(source),
            effect_scope=scope, audit_all_definitions=True, resolved_calls=sources.resolved_function_calls(source.path))
        visitor.visit(tree)
        violations.extend(visitor.violations)
    return RuleResult(records={"effect_policy": policy_record}, findings=tuple(
        violation_finding(context, item) for item in violations))
