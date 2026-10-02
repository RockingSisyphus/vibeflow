"""Judge AST metrics with the portable numeric implementation rules."""

import ast

from vibeflow.core.quality.implementation import CallChain, ImplementationLimits, ImplementationMetrics, analyze_call_graph, evaluate_node_implementation, evaluate_base_lib_implementation, evaluate_base_lib_dependency_chain
from vibeflow.core.rules import RuleRecord, RuleResult
from vibeflow.targets.python.quality.rules.helpers import finding, source_policy, source_subject
from vibeflow.targets.python.quality.source_analysis.metrics import _ComplexityCounter, _analyze_internal_call_chain


def maintainability(context, inputs, params):
    if context.subject.get("kind") == "base_lib":
        source = context.require("base_lib_file")
        if source.tree is None:
            return RuleResult(state="unavailable")
        counter = _ComplexityCounter()
        counter.visit(source.tree)
        metrics = ImplementationMetrics(source_lines=len(source.text.splitlines()),source_bytes=len(source.text.encode()),
            function_count=counter.function_count,branch_count=counter.branch_count,max_nesting_depth=counter.max_nesting_depth)
        findings = tuple(finding(context,item.rule_id,item.message,path=source.path,severity=item.severity,
            details=item.details,suggested_fix_type=item.suggested_fix_type)
            for item in evaluate_base_lib_implementation(metrics,ImplementationLimits.from_policy(source_policy(context,params))))
        return RuleResult(records={"metrics":RuleRecord("vibeflow.node_metrics.v1",{"source_lines":metrics.source_lines,
            "source_bytes":metrics.source_bytes,"function_count":metrics.function_count,"branch_count":metrics.branch_count,
            "max_nesting_depth":metrics.max_nesting_depth})},findings=findings)
    sources, node, symbol = source_subject(context)
    if symbol is None:
        return RuleResult(state="unavailable")
    tree = ast.Module(body=[symbol.node], type_ignores=[])
    counter = _ComplexityCounter()
    counter.visit(tree)
    text = "\n".join(sources.file(node.path).text.splitlines()[symbol.line - 1:symbol.end_line])
    chain = _analyze_internal_call_chain(tree)
    metrics = ImplementationMetrics(source_lines=len(text.splitlines()), source_bytes=len(text.encode("utf-8")),
        function_count=counter.function_count, branch_count=counter.branch_count, max_nesting_depth=counter.max_nesting_depth,
        param_count=len(node.descriptor.contract.params_schema), contract_key_count=len(node.descriptor.contract.requires) + len(node.descriptor.contract.provides),
        call_chain=CallChain(chain.length, chain.path, chain.recursive_paths))
    limits = ImplementationLimits.from_policy(source_policy(context,params))
    findings = [finding(context, item.rule_id, item.message, path=node.path, line=symbol.line, severity=item.severity, details=dict(item.details), suggested_fix_type=item.suggested_fix_type)
                     for item in evaluate_node_implementation(metrics, limits)]
    from vibeflow.targets.python.quality.source_analysis.validators import _validate_architecture_smells
    from vibeflow.targets.python.quality.source_analysis.types import NodeMetrics
    from vibeflow.targets.python.quality.rules.helpers import source_info, violation_finding
    findings.extend(violation_finding(context,item) for item in _validate_architecture_smells(
        node.descriptor,node.descriptor.contract,source=source_info(sources.file(node.path),symbol),
        metrics=NodeMetrics(contract_key_count=metrics.contract_key_count)))
    library_files = tuple(source for source in sources.files if "base_lib" in source.module.split("."))
    library_modules = {source.module:source for source in library_files}
    dependencies = {}
    from vibeflow.targets.python.quality.source_analysis.ast_rules import import_modules
    def local_imports(source):
        return tuple(dict.fromkeys(module for statement in ast.walk(source.tree) if isinstance(statement,(ast.Import,ast.ImportFrom))
                                  for module in import_modules(statement) if module in library_modules)) if source.tree is not None else ()
    starts = local_imports(sources.file(node.path))
    for source in library_files:
        dependencies[source.module] = local_imports(source)
        helper_counter = _ComplexityCounter()
        helper_counter.visit(source.tree)
        helper_metrics = ImplementationMetrics(source_lines=len(source.text.splitlines()),source_bytes=len(source.text.encode()),
            function_count=helper_counter.function_count,branch_count=helper_counter.branch_count,max_nesting_depth=helper_counter.max_nesting_depth)
        for item in evaluate_base_lib_implementation(helper_metrics,limits):
            findings.append(finding(context,item.rule_id,item.message,path=source.path,severity=item.severity,details=dict(item.details),suggested_fix_type=item.suggested_fix_type))
    dependencies["node"] = starts
    dependency_chain = analyze_call_graph(dependencies,entry="node") if starts else CallChain()
    dependency_finding = evaluate_base_lib_dependency_chain(dependency_chain,limits)
    if dependency_finding is not None:
        findings.append(finding(context,dependency_finding.rule_id,dependency_finding.message,path=node.path,line=symbol.line,
            severity=dependency_finding.severity,suggested_fix_type=dependency_finding.suggested_fix_type,
            details={**dependency_finding.details,"longest_chain_length":dependency_chain.length,"longest_chain":dependency_chain.path,
                     "imported_modules":starts,"recursive_chains":dependency_chain.recursive_paths}))
    record = RuleRecord("vibeflow.node_metrics.v1", {"source_lines": metrics.source_lines, "source_bytes": metrics.source_bytes,
        "function_count": metrics.function_count, "branch_count": metrics.branch_count, "max_nesting_depth": metrics.max_nesting_depth,
        "param_count": metrics.param_count, "contract_key_count": metrics.contract_key_count,
        "requires_count":len(node.descriptor.contract.requires), "provides_count":len(node.descriptor.contract.provides),
        "function_names":tuple(counter.function_names), "call_chain_length":chain.length,"call_chain_path":chain.path,"recursive_call_chains":chain.recursive_paths,
        "max_dependency_chain_length":dependency_chain.length,"max_dependency_chain":dependency_chain.path,
        "imported_base_lib_modules":starts, "run_pure_fingerprint": counter.run_pure_fingerprint, "run_pure_shape": counter.run_pure_shape})
    return RuleResult(records={"metrics": record}, findings=tuple(findings))
