"""Rules over portable implementation metrics, without source inspection."""

from dataclasses import asdict, replace, fields
from typing import Mapping
from vibeflow.core.quality.implementation import ImplementationMetrics, ImplementationLimits, ImplementationFinding, CallChain

from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleDescriptor, RuleRecord, RuleResult


def _result(context, items):
    return RuleResult({"diagnostics": RuleRecord("vibeflow.implementation_diagnostics.v1", [
        {**asdict(item), "code": item.rule_id, "internal_code": item.code} for item in items])},
        tuple(HealthFinding(rule_id=item.rule_id, severity=item.severity, object_type="implementation",
                            object_id=str(context.subject.get("id", "")), message=item.message,
                            suggested_fix_type=item.suggested_fix_type, details=item.details) for item in items))


def _node(context, inputs, params):
    return _result(context, check_node_implementation(context.require("metrics"), _limits(context, params)))


def _base_lib(context, inputs, params):
    return _result(context, check_base_lib_implementation(context.require("metrics"), _limits(context, params)))


def _chain(context, inputs, params):
    item = check_base_lib_dependency_chain(context.require("chain"), _limits(context, params))
    return _result(context, () if item is None else (item,))


def implementation_resources():
    return tuple(RuleDescriptor("vibeflow.implementation." + name,
                               params_schema={"policy": {"type": "object"}}, params_defaults={"policy": {}},
                               outputs={"diagnostics": "vibeflow.implementation_diagnostics.v1"})
                 for name in ("node", "base_lib", "dependency_chain"))


def implementation_handlers():
    return {"vibeflow.implementation.node": _node, "vibeflow.implementation.base_lib": _base_lib,
            "vibeflow.implementation.dependency_chain": _chain}



def _limits(context, params):
    base = context.facts.get("limits", ImplementationLimits())
    policy = params.get("policy", {})
    aliases = {"max_lines": "max_source_lines", "max_bytes": "max_source_bytes",
               "warn_lines": "warn_source_lines", "warn_bytes": "warn_source_bytes"}
    names = {item.name for item in fields(ImplementationLimits)}
    updates = {}
    for section in ("node_source", "complexity", "maintainability"):
        for name, value in policy.get(section, {}).items():
            field = aliases.get(name, name)
            if field not in names:
                raise ValueError(f"unknown implementation policy parameter: {section}.{name}")
            updates[field] = value
    return replace(base, **updates)


def check_node_implementation(
    metrics: ImplementationMetrics, limits: ImplementationLimits
) -> tuple[ImplementationFinding, ...]:
    findings: list[ImplementationFinding] = []
    if metrics.source_lines > limits.max_source_lines:
        findings.append(_node_finding("source_too_large", "error", f"node source has {metrics.source_lines} lines > {limits.max_source_lines}", "split_node", {"lines": metrics.source_lines, "limit": limits.max_source_lines}))
    elif limits.warn_source_lines is not None and metrics.source_lines >= limits.warn_source_lines:
        findings.append(_node_finding("source_near_limit", "warning", f"node source has {metrics.source_lines} lines >= warning threshold {limits.warn_source_lines}", "split_node", {"lines": metrics.source_lines, "limit": limits.warn_source_lines}))
    if metrics.source_bytes > limits.max_source_bytes:
        findings.append(_node_finding("source_bytes_too_large", "error", f"node source has {metrics.source_bytes} bytes > {limits.max_source_bytes}", "split_node", {"bytes": metrics.source_bytes, "limit": limits.max_source_bytes}))
    elif limits.warn_source_bytes is not None and metrics.source_bytes >= limits.warn_source_bytes:
        findings.append(_node_finding("source_bytes_near_limit", "warning", f"node source has {metrics.source_bytes} bytes >= warning threshold {limits.warn_source_bytes}", "split_node", {"bytes": metrics.source_bytes, "limit": limits.warn_source_bytes}))
    for name, actual, fix_type in (
        ("max_functions", metrics.function_count, "split_node"),
        ("max_branches", metrics.branch_count, "split_node"),
        ("max_nesting_depth", metrics.max_nesting_depth, "split_node"),
        ("max_params", metrics.param_count, "fix_contract"),
        ("max_contract_keys", metrics.contract_key_count, "fix_contract"),
    ):
        limit = getattr(limits, name)
        if limit is None or actual <= limit:
            continue
        key = {"max_functions": "function_count", "max_branches": "branch_count", "max_nesting_depth": "max_nesting_depth", "max_params": "param_count", "max_contract_keys": "contract_key_count"}[name]
        findings.append(_node_finding(f"complexity_{name}", "error", f"node {key} is {actual} > policy limit {limit}", fix_type, {key: actual, "limit": limit, "metrics": dict(metrics.report_metrics)}))
    chain = metrics.call_chain
    if chain.length > limits.max_call_chain_length:
        findings.append(_node_finding("call_chain_too_deep", "error", f"node internal call chain length is {chain.length} > {limits.max_call_chain_length}", "split_node", {"length": chain.length, "limit": limits.max_call_chain_length, "path": list(chain.path)}))
    elif chain.length >= limits.warn_call_chain_length:
        findings.append(_node_finding("call_chain_too_deep", "warning", f"node internal call chain length is {chain.length} >= warning threshold {limits.warn_call_chain_length}", "split_node", {"length": chain.length, "limit": limits.warn_call_chain_length, "path": list(chain.path)}))
    return tuple(findings)


def check_base_lib_implementation(
    metrics: ImplementationMetrics, limits: ImplementationLimits
) -> tuple[ImplementationFinding, ...]:
    findings: list[ImplementationFinding] = []
    for field, rule_id, actual, limit in (
        ("lines", "BASE_LIB.SOURCE.MAX_LINES", metrics.source_lines, limits.max_source_lines),
        ("bytes", "BASE_LIB.SOURCE.MAX_BYTES", metrics.source_bytes, limits.max_source_bytes),
    ):
        if actual > limit:
            findings.append(ImplementationFinding(rule_id.lower(), rule_id, "error", f"base_lib file has {actual} {field} > {limit}", "split_module", {field: actual, "limit": limit}))
    for field, actual, limit, maximum in (("lines",metrics.source_lines,limits.warn_source_lines,limits.max_source_lines),
                                         ("bytes",metrics.source_bytes,limits.warn_source_bytes,limits.max_source_bytes)):
        if limit is not None and limit <= actual <= maximum:
            findings.append(ImplementationFinding("base_lib.source_near_limit", "BASE_LIB.SOURCE.NEAR_LIMIT", "warning",
                f"base_lib file has {actual} {field} >= warning threshold {limit}","split_module",{field:actual,"limit":limit}))
    for name, key, actual in (
        ("MAX_FUNCTIONS", "function_count", metrics.function_count),
        ("MAX_BRANCHES", "branch_count", metrics.branch_count),
        ("MAX_NESTING_DEPTH", "max_nesting_depth", metrics.max_nesting_depth),
    ):
        limit = getattr(limits, name.lower())
        if limit is not None and actual > limit:
            rule_id = f"BASE_LIB.COMPLEXITY.{name}"
            findings.append(ImplementationFinding(rule_id.lower(), rule_id, "error", f"base_lib {key} is {actual} > policy limit {limit}", "split_module", {key: actual, "limit": limit}))
    return tuple(findings)


def check_base_lib_dependency_chain(
    chain: CallChain, limits: ImplementationLimits
) -> ImplementationFinding | None:
    """Judge a Node's statically known path through base_lib modules."""

    if chain.length > limits.max_dependency_chain_length:
        severity, limit = "error", limits.max_dependency_chain_length
    elif chain.length > limits.warn_dependency_chain_length:
        severity, limit = "warning", limits.warn_dependency_chain_length
    else:
        return None
    return ImplementationFinding(
        "dependency_chain_too_deep",
        "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP",
        severity,
        f"node base_lib dependency chain length is {chain.length} > {limit}",
        "fix_base_lib",
        {"longest_chain_length": chain.length, "longest_chain": list(chain.path),
         "recursive_chains": [list(path) for path in chain.recursive_paths], "limit": limit},
    )


def _node_finding(
    code: str, severity: str, message: str, suggested_fix_type: str,
    details: Mapping[str, object],
) -> ImplementationFinding:
    prefix = "NODE.MAINTAINABILITY" if code.startswith("complexity_") or code == "call_chain_too_deep" else "NODE.PURITY"
    return ImplementationFinding(code, f"{prefix}.{code.upper()}", severity, message, suggested_fix_type, details)



__all__ = ["implementation_handlers", "implementation_resources", "check_node_implementation", "check_base_lib_implementation", "check_base_lib_dependency_chain"]
