from __future__ import annotations
import inspect
from typing import Mapping
from vibeflow.core.quality.implementation import (
    CallChain,
    ImplementationLimits,
    ImplementationMetrics,
    evaluate_node_implementation,
)
from vibeflow.core.contracts import CARDINALITIES, DataProvider, DataRequirement, provider_keys, requirement_types
from vibeflow.core.constants import FLOW_KIND_DECISION, FLOW_KINDS
from vibeflow.targets.python.project.node import NodeContract, NodeInfo, PureNode
from vibeflow.targets.python.quality.source_analysis.helpers import (
    _looks_structured_key,
    _looks_temporary_key,
    _non_empty_string,
    _validate_key_tuple,
    _validate_semantics,
    _violation,
)
from vibeflow.targets.python.quality.source_analysis.types import NodeMetrics, PurityPolicy, PurityViolation, _SourceInfo

def _validate_source_size(source_text: str, *, policy: PurityPolicy, source: _SourceInfo) -> list[PurityViolation]:
    facts = ImplementationMetrics(
        source_lines=len(source_text.splitlines()),
        source_bytes=len(source_text.encode("utf-8")),
    )
    return _numeric_violations(facts, policy, source, prefix="source_")


def _validate_complexity_metrics(metrics: NodeMetrics, *, policy: PurityPolicy, source: _SourceInfo) -> list[PurityViolation]:
    return _numeric_violations(_core_metrics(metrics), policy, source, prefix="complexity_")


def _validate_call_chain_metrics(metrics: NodeMetrics, *, policy: PurityPolicy, source: _SourceInfo) -> list[PurityViolation]:
    return [
        violation for violation in _numeric_violations(_core_metrics(metrics), policy, source)
        if violation.code in {"call_chain_too_deep", "recursive_call_chain"}
    ]


def _core_metrics(metrics: NodeMetrics) -> ImplementationMetrics:
    return ImplementationMetrics(
        source_lines=metrics.source_lines,
        source_bytes=metrics.source_bytes,
        function_count=metrics.function_count,
        branch_count=metrics.branch_count,
        max_nesting_depth=metrics.max_nesting_depth,
        param_count=metrics.param_count,
        contract_key_count=metrics.contract_key_count,
        call_chain=CallChain(
            metrics.call_chain_length,
            metrics.call_chain_path,
            metrics.recursive_call_chains,
        ),
        report_metrics=metrics.to_dict(),
    )


def _numeric_violations(
    metrics: ImplementationMetrics,
    policy: PurityPolicy,
    source: _SourceInfo,
    *,
    prefix: str | None = None,
) -> list[PurityViolation]:
    return [
        _violation(
            finding.code,
            finding.message,
            source=source,
            severity=finding.severity,
            suggested_fix_type=finding.suggested_fix_type,
            details=finding.details,
        )
        for finding in evaluate_node_implementation(
            metrics, ImplementationLimits.from_policy(policy)
        )
        if prefix is None or finding.code.startswith(prefix)
    ]


def _validate_architecture_smells(
    info: NodeInfo,
    contract: NodeContract,
    *,
    source: _SourceInfo,
    metrics: NodeMetrics,
) -> list[PurityViolation]:
    warnings: list[PurityViolation] = []
    require_types = requirement_types(contract.requires)
    provide_keys = provider_keys(contract.provides)
    for key in (*require_types, *provide_keys):
        if _looks_temporary_key(key):
            warnings.append(
                _violation(
                    "temporary_key",
                    f"contract key looks temporary or unstable: {key}",
                    source=source,
                    severity="warning",
                    failure_layer="contract",
                    suggested_fix_type="fix_contract",
                    details={"key": key},
                )
            )
        if not _looks_structured_key(key):
            warnings.append(
                _violation(
                    "confusing_key_name",
                    f"contract key should use lowercase dot/underscore segments: {key}",
                    source=source,
                    severity="warning",
                    failure_layer="contract",
                    suggested_fix_type="fix_contract",
                    details={"key": key},
                )
            )
    if metrics.contract_key_count > 10:
        warnings.append(
            _violation(
                "wide_contract",
                f"node contract is wide with {metrics.contract_key_count} keys",
                source=source,
                severity="warning",
                failure_layer="contract",
                suggested_fix_type="split_node",
                details={"metrics": metrics.to_dict()},
            )
        )
    return warnings


def _validate_contract_examples_shape(value: object, *, source: _SourceInfo) -> list[PurityViolation]:
    if not isinstance(value, tuple):
        return [_violation("example_shape", "descriptor contract.examples must be a tuple of example mappings", source=source, severity="warning", failure_layer="contract", suggested_fix_type="fix_contract")]
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            return [_violation("example_shape", f"descriptor contract.examples[{index}] must be a mapping", source=source, severity="warning", failure_layer="contract", suggested_fix_type="fix_contract")]
        for field_name in ("inputs", "params"):
            if field_name not in item or not isinstance(item[field_name], Mapping):
                return [_violation("example_shape", f"descriptor contract.examples[{index}].{field_name} must be a mapping", source=source, severity="warning", failure_layer="contract", suggested_fix_type="fix_contract")]
        if "outputs" in item:
            return [_violation("example_outputs_removed", f"descriptor contract.examples[{index}].outputs is removed; examples only declare inputs and params", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    return []
