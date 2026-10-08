"""Health decisions using the same measurements as public implementation Rules."""

from dataclasses import replace

from vibeflow.core.quality.implementation import ImplementationLimits
from vibeflow.builtin.implementation import check_node_implementation, check_base_lib_implementation, check_base_lib_dependency_chain
from vibeflow.core.rules import RuleRecord, RuleResult
from vibeflow.builtin.implementation import implementation_handlers
from vibeflow.targets.python.quality.analysis_metrics import PythonSourceAnalysis
from vibeflow.targets.python.quality.rules.helpers import finding, source_policy, source_subject, source_info, violation_finding


def _located(context, item, path, line=1):
    return finding(context, item.rule_id, item.message, path=path, line=line,
        severity=item.severity, details=dict(item.details), suggested_fix_type=item.suggested_fix_type)


def maintainability(context, inputs, params, *, analysis=None):
    analysis = analysis or PythonSourceAnalysis()
    measured = analysis.measurements(context)
    if measured is None:
        return RuleResult(state="unavailable")
    metrics = measured.metrics
    limits = ImplementationLimits.from_policy(source_policy(params, sections=("node_source", "complexity", "maintainability")))
    is_library = context.subject.get("kind") != "node"
    evaluator = check_base_lib_implementation if is_library else check_node_implementation
    findings = [_located(context, item, measured.path, measured.line) for item in evaluator(metrics, limits)]
    if not is_library:
        sources, node, symbol = source_subject(context)
        from vibeflow.targets.python.quality.source_analysis.validators import _validate_architecture_smells
        from vibeflow.targets.python.quality.source_analysis.types import NodeMetrics
        findings.extend(violation_finding(context, item) for item in _validate_architecture_smells(
            node.descriptor, node.descriptor.contract, source=source_info(sources.file(node.path), symbol),
            metrics=NodeMetrics(contract_key_count=metrics.contract_key_count)))

        item = check_base_lib_dependency_chain(measured.dependency_chain, limits)
        if item is not None:
            diagnostic = _located(context, item, measured.path, measured.line)
            findings.append(replace(diagnostic, details={**diagnostic.details,
                "longest_chain_length": measured.dependency_chain.length, "longest_chain": measured.dependency_chain.path,
                "imported_modules": measured.imported_modules, "recursive_chains": measured.dependency_chain.recursive_paths}))
    for path, helper_metrics in measured.helpers:
        findings.extend(_located(context, item, path) for item in check_base_lib_implementation(helper_metrics, limits))
    record = {"source_lines": metrics.source_lines, "source_bytes": metrics.source_bytes,
        "function_count": metrics.function_count, "branch_count": metrics.branch_count,
        "max_nesting_depth": metrics.max_nesting_depth, "param_count": metrics.param_count,
        "contract_key_count": metrics.contract_key_count, "function_names": measured.function_names,
        "call_chain_length": metrics.call_chain.length, "call_chain_path": metrics.call_chain.path,
        "recursive_call_chains": metrics.call_chain.recursive_paths,
        "max_dependency_chain_length": measured.dependency_chain.length, "max_dependency_chain": measured.dependency_chain.path,
        "imported_base_lib_modules": measured.imported_modules, "run_pure_fingerprint": measured.fingerprint,
        "run_pure_shape": measured.shape}
    if not is_library:
        record.update(requires_count=len(node.descriptor.contract.requires), provides_count=len(node.descriptor.contract.provides))
    return RuleResult({"metrics": RuleRecord("vibeflow.node_metrics.v1", record)}, tuple(findings))


def source_implementation_handlers(analysis):
    handlers = implementation_handlers()
    def check(name):
        def invoke(context, inputs, params):
            measured = analysis.measurements(context)
            if measured is None:
                return RuleResult(state="unavailable")
            limits = ImplementationLimits.from_policy(source_policy(params, sections=("node_source", "complexity", "maintainability")))
            if name == "base_lib" and context.subject.get("kind") != "base_lib":
                from vibeflow.core.rules.models import plain
                returned = []
                for path, metrics in measured.helpers:
                    result = handlers["vibeflow.implementation.base_lib"](replace(context, facts={**context.facts, "metrics": metrics, "limits": limits}), inputs, params)
                    returned.append((path, result))
                return RuleResult({"diagnostics": RuleRecord("vibeflow.implementation_diagnostics.v1",
                    [plain(item) for _, result in returned for item in result.records["diagnostics"].value])},
                    tuple(replace(item, source_location={"path":path,"line":1,"column":1}) for path,result in returned for item in result.findings))
            result = handlers["vibeflow.implementation." + name](replace(context, facts={**context.facts,
                "metrics": measured.metrics, "chain": measured.dependency_chain, "limits": limits}), inputs, params)
            return replace(result, findings=tuple(replace(item,
                source_location={"path":measured.path,"line":measured.line,"column":1}) for item in result.findings))
        return invoke
    return {"vibeflow.implementation." + name: check(name) for name in ("node", "base_lib", "dependency_chain")}
