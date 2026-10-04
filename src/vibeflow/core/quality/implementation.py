"""Pure numeric maintainability rules shared by source-language targets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CallChain:
    length: int = 0
    path: tuple[str, ...] = ()
    recursive_paths: tuple[tuple[str, ...], ...] = ()


def analyze_call_graph(
    calls: Mapping[str, Sequence[str]], *, entry: str
) -> CallChain:
    """Follow statically known local calls, counting the entry as one step."""

    if not entry or entry not in calls:
        return CallChain()
    best: tuple[str, ...] = (entry,)
    cycles: set[tuple[str, ...]] = set()

    def visit(name: str, path: tuple[str, ...]) -> None:
        nonlocal best
        if len(path) > len(best):
            best = path
        for target in sorted(set(calls.get(name, ()))):
            if target not in calls:
                continue
            if target in path:
                cycles.add((*path[path.index(target):], target))
            else:
                visit(target, (*path, target))

    visit(entry, (entry,))
    return CallChain(len(best), best, tuple(sorted(cycles)))


@dataclass(frozen=True)
class ImplementationMetrics:
    source_lines: int = 0
    source_bytes: int = 0
    function_count: int = 0
    branch_count: int = 0
    max_nesting_depth: int = 0
    param_count: int = 0
    contract_key_count: int = 0
    call_chain: CallChain = field(default_factory=CallChain)
    report_metrics: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ImplementationLimits:
    max_source_lines: int = 500
    max_source_bytes: int = 60000
    warn_source_lines: int | None = 450
    warn_source_bytes: int | None = 54000
    max_functions: int | None = None
    max_branches: int | None = None
    max_nesting_depth: int | None = None
    max_params: int | None = None
    max_contract_keys: int | None = None
    warn_call_chain_length: int = 4
    max_call_chain_length: int = 4
    warn_dependency_chain_length: int = 4
    max_dependency_chain_length: int = 6

    @classmethod
    def from_policy(cls, policy: object) -> ImplementationLimits:
        """Copy the common numeric fields from a target policy value."""

        return cls(
            **{
                name: getattr(policy, name)
                for name in cls.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class ImplementationFinding:
    code: str
    rule_id: str
    severity: str
    message: str
    suggested_fix_type: str
    details: Mapping[str, object]


def _node_implementation_facts(
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
    for path in chain.recursive_paths:
        findings.append(_node_finding("recursive_call_chain", "error", "node internal helper calls must not be recursive: " + " -> ".join(path), "split_node", {"path": list(path), "metrics": dict(metrics.report_metrics)}))
    if chain.length > limits.max_call_chain_length:
        findings.append(_node_finding("call_chain_too_deep", "error", f"node internal call chain length is {chain.length} > {limits.max_call_chain_length}", "split_node", {"length": chain.length, "limit": limits.max_call_chain_length, "path": list(chain.path)}))
    elif chain.length >= limits.warn_call_chain_length:
        findings.append(_node_finding("call_chain_too_deep", "warning", f"node internal call chain length is {chain.length} >= warning threshold {limits.warn_call_chain_length}", "split_node", {"length": chain.length, "limit": limits.warn_call_chain_length, "path": list(chain.path)}))
    return tuple(findings)


def _base_lib_implementation_facts(
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


def _base_lib_dependency_facts(
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


def evaluate_node_implementation(metrics: ImplementationMetrics, limits: ImplementationLimits) -> tuple[ImplementationFinding, ...]:
    from vibeflow.core.rules.builtin.implementation import evaluate_implementation_rule
    return evaluate_implementation_rule("node", metrics=metrics, limits=limits)


def evaluate_base_lib_implementation(metrics: ImplementationMetrics, limits: ImplementationLimits) -> tuple[ImplementationFinding, ...]:
    from vibeflow.core.rules.builtin.implementation import evaluate_implementation_rule
    return evaluate_implementation_rule("base_lib", metrics=metrics, limits=limits)


def evaluate_base_lib_dependency_chain(chain: CallChain, limits: ImplementationLimits) -> ImplementationFinding | None:
    from vibeflow.core.rules.builtin.implementation import evaluate_implementation_rule
    findings = evaluate_implementation_rule("dependency_chain", chain=chain, limits=limits)
    return findings[0] if findings else None


def _node_finding(
    code: str, severity: str, message: str, suggested_fix_type: str,
    details: Mapping[str, object],
) -> ImplementationFinding:
    prefix = "NODE.MAINTAINABILITY" if code.startswith("complexity_") or code in {"call_chain_too_deep", "recursive_call_chain"} else "NODE.PURITY"
    return ImplementationFinding(code, f"{prefix}.{code.upper()}", severity, message, suggested_fix_type, details)


__all__ = ["CallChain", "ImplementationFinding", "ImplementationLimits", "ImplementationMetrics", "analyze_call_graph", "evaluate_base_lib_dependency_chain", "evaluate_base_lib_implementation", "evaluate_node_implementation"]
