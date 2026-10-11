from __future__ import annotations
from vibeflow.core.contracts import provider_keys, requirement_types
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.quality.source_analysis.helpers import _looks_structured_key, _looks_temporary_key, _violation
from vibeflow.targets.python.quality.source_analysis.types import NodeMetrics, PurityViolation, _SourceInfo


def _validate_architecture_smells(
    info: NodeDescriptor,
    contract: NodeContractDescriptor,
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
