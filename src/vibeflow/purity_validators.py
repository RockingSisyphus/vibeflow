from __future__ import annotations

import inspect
import json
from copy import deepcopy
from typing import Mapping

from .node import FLOW_KIND_DECISION, FLOW_KINDS, NodeContract, NodeInfo, PureNode
from .purity_helpers import (
    _looks_structured_key,
    _looks_temporary_key,
    _non_empty_string,
    _tokens,
    _validate_key_tuple,
    _validate_schema_mapping,
    _validate_semantics,
    _violation,
)
from .purity_types import NodeMetrics, PurityPolicy, PurityViolation, _SourceInfo


def _validate_node_info(info: object, *, expected_type: str | None, source: _SourceInfo) -> list[PurityViolation]:
    if not isinstance(info, NodeInfo):
        return [_violation("missing_node_info", "node must define NODE_INFO: NodeInfo", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    violations: list[PurityViolation] = []
    for field_name in ("type_key", "display_name", "category", "description", "version", "flow_kind", "purity"):
        if not _non_empty_string(getattr(info, field_name, None)):
            violations.append(_violation(f"node_info_{field_name}", f"NODE_INFO.{field_name} must be a non-empty string", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    if _non_empty_string(getattr(info, "flow_kind", None)) and info.flow_kind not in FLOW_KINDS:
        violations.append(_violation("node_flow_kind_invalid", f"NODE_INFO.flow_kind must be one of {sorted(FLOW_KINDS)}", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    if not isinstance(getattr(info, "external", False), bool):
        violations.append(_violation("node_external_invalid", "NODE_INFO.external must be a boolean", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    if info.purity != "pure":
        violations.append(_violation("non_pure_node", "NODE_INFO.purity must be 'pure'", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    if expected_type and info.type_key != expected_type:
        violations.append(_violation("type_mismatch", f"NODE_INFO.type_key {info.type_key!r} does not match expected type {expected_type!r}", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    return violations


def _validate_contract(contract: object, *, source: _SourceInfo) -> list[PurityViolation]:
    if not isinstance(contract, NodeContract):
        return [_violation("missing_contract", "node must define CONTRACT: NodeContract", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    violations: list[PurityViolation] = []
    requires = _validate_key_tuple(contract.requires, "CONTRACT.requires", source=source, violations=violations)
    provides = _validate_key_tuple(contract.provides, "CONTRACT.provides", source=source, violations=violations)
    if set(requires) & set(provides):
        violations.append(_violation("contract_overlap", "CONTRACT.requires and CONTRACT.provides must not overlap", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    violations.extend(_validate_semantics(contract.input_semantics, requires, "CONTRACT.input_semantics", required=bool(requires), source=source))
    violations.extend(_validate_semantics(contract.output_semantics, provides, "CONTRACT.output_semantics", required=bool(provides), source=source))
    violations.extend(_validate_schema_mapping(contract.params_schema, (), "CONTRACT.params_schema", source=source, require_all=False))
    violations.extend(_validate_schema_mapping(contract.output_schema, provides, "CONTRACT.output_schema", source=source, require_all=bool(provides)))
    violations.extend(_validate_contract_examples_shape(contract.examples, source=source))
    return violations


def _validate_flow_kind_contract(info: NodeInfo, contract: NodeContract, *, source: _SourceInfo) -> list[PurityViolation]:
    if info.flow_kind != FLOW_KIND_DECISION:
        return []
    route_keys = tuple(key for key in contract.provides if _looks_route_key(key))
    if route_keys:
        return []
    return [
        _violation(
            "node_decision_missing_route_output",
            "decision nodes must provide a route/decision/branch output key",
            source=source,
            failure_layer="contract",
            suggested_fix_type="fix_contract",
        )
    ]


def _looks_route_key(key: str) -> bool:
    leaf = key.rsplit(".", 1)[-1].rsplit("_", 1)[-1]
    return leaf in {"route", "decision", "branch", "selected", "done", "should_retry"} or key.endswith("selected_branch")


def _validate_interface(node_cls: type[PureNode], *, source: _SourceInfo) -> list[PurityViolation]:
    violations: list[PurityViolation] = []
    if "run" in node_cls.__dict__:
        violations.append(_violation("context_run_forbidden", "pure node must not define run(context, ...)", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    run_pure = node_cls.__dict__.get("run_pure")
    if run_pure is None:
        violations.append(_violation("missing_run_pure", "node must define run_pure(self, inputs, params)", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    elif inspect.iscoroutinefunction(run_pure):
        violations.append(_violation("async_run_pure", "run_pure must not be async", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    else:
        violations.extend(_validate_signature(run_pure, ("self", "inputs", "params"), "run_pure", source=source))
    init = node_cls.__dict__.get("__init__")
    if init is not None:
        violations.extend(_validate_signature(init, ("self",), "__init__", source=source, allow_defaulted=False))
    for name, value in node_cls.__dict__.items():
        if name.startswith("_") or name in {"run_pure"}:
            continue
        if callable(value):
            violations.append(_violation("public_callable", f"node must not expose public callable method: {name}", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    return violations


def _validate_signature(
    func: object,
    expected_names: tuple[str, ...],
    function_name: str,
    *,
    source: _SourceInfo,
    allow_defaulted: bool = True,
) -> list[PurityViolation]:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError) as exc:
        return [_violation("signature_unavailable", f"{function_name} signature is unavailable: {exc}", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    params = list(signature.parameters.values())
    valid_kinds = {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY}
    if len(params) != len(expected_names) or tuple(param.name for param in params) != expected_names:
        return [_violation("run_pure_signature" if function_name == "run_pure" else "init_signature", f"{function_name} must have signature ({', '.join(expected_names)})", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    for param in params:
        if param.kind not in valid_kinds:
            return [_violation("run_pure_signature" if function_name == "run_pure" else "init_signature", f"{function_name} must not use *args, **kwargs, or keyword-only parameters", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
        if not allow_defaulted and param.default is not inspect.Parameter.empty:
            return [_violation("init_signature", "__init__ must not accept configured parameters", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    return []


def _validate_source_size(source_text: str, *, policy: PurityPolicy, source: _SourceInfo) -> list[PurityViolation]:
    violations: list[PurityViolation] = []
    line_count = len(source_text.splitlines())
    byte_count = len(source_text.encode("utf-8"))
    if line_count > policy.max_source_lines:
        violations.append(_violation("source_too_large", f"node source has {line_count} lines > {policy.max_source_lines}", source=source, suggested_fix_type="split_node", details={"lines": line_count, "limit": policy.max_source_lines}))
    elif policy.warn_source_lines is not None and line_count >= policy.warn_source_lines:
        violations.append(_violation("source_near_limit", f"node source has {line_count} lines >= warning threshold {policy.warn_source_lines}", source=source, severity="warning", suggested_fix_type="split_node", details={"lines": line_count, "limit": policy.warn_source_lines}))
    if byte_count > policy.max_source_bytes:
        violations.append(_violation("source_bytes_too_large", f"node source has {byte_count} bytes > {policy.max_source_bytes}", source=source, suggested_fix_type="split_node", details={"bytes": byte_count, "limit": policy.max_source_bytes}))
    elif policy.warn_source_bytes is not None and byte_count >= policy.warn_source_bytes:
        violations.append(_violation("source_bytes_near_limit", f"node source has {byte_count} bytes >= warning threshold {policy.warn_source_bytes}", source=source, severity="warning", suggested_fix_type="split_node", details={"bytes": byte_count, "limit": policy.warn_source_bytes}))
    return violations


def _validate_complexity_metrics(metrics: NodeMetrics, *, policy: PurityPolicy, source: _SourceInfo) -> list[PurityViolation]:
    checks = (
        ("max_functions", policy.max_functions, metrics.function_count, "function_count", "split_node"),
        ("max_branches", policy.max_branches, metrics.branch_count, "branch_count", "split_node"),
        ("max_nesting_depth", policy.max_nesting_depth, metrics.max_nesting_depth, "max_nesting_depth", "split_node"),
        ("max_params", policy.max_params, metrics.param_count, "param_count", "fix_contract"),
        ("max_contract_keys", policy.max_contract_keys, metrics.contract_key_count, "contract_key_count", "fix_contract"),
    )
    violations: list[PurityViolation] = []
    for code, limit, actual, detail_key, fix_type in checks:
        if limit is not None and actual > limit:
            violations.append(
                _violation(
                    f"complexity_{code}",
                    f"node {detail_key} is {actual} > policy limit {limit}",
                    source=source,
                    suggested_fix_type=fix_type,
                    details={detail_key: actual, "limit": limit, "metrics": metrics.to_dict()},
                )
            )
    return violations


def _validate_call_chain_metrics(metrics: NodeMetrics, *, policy: PurityPolicy, source: _SourceInfo) -> list[PurityViolation]:
    violations: list[PurityViolation] = []
    for path in metrics.recursive_call_chains:
        violations.append(
            _violation(
                "recursive_call_chain",
                "node internal helper calls must not be recursive: " + " -> ".join(path),
                source=source,
                suggested_fix_type="split_node",
                details={"path": list(path), "metrics": metrics.to_dict()},
            )
        )
    if metrics.call_chain_length > policy.max_call_chain_length:
        violations.append(
            _violation(
                "call_chain_too_deep",
                f"node internal call chain length is {metrics.call_chain_length} > {policy.max_call_chain_length}",
                source=source,
                suggested_fix_type="split_node",
                details={"length": metrics.call_chain_length, "limit": policy.max_call_chain_length, "path": list(metrics.call_chain_path)},
            )
        )
    elif metrics.call_chain_length >= policy.warn_call_chain_length:
        violations.append(
            _violation(
                "call_chain_too_deep",
                f"node internal call chain length is {metrics.call_chain_length} >= warning threshold {policy.warn_call_chain_length}",
                source=source,
                severity="warning",
                suggested_fix_type="split_node",
                details={"length": metrics.call_chain_length, "limit": policy.warn_call_chain_length, "path": list(metrics.call_chain_path)},
            )
        )
    return violations


def _validate_architecture_smells(
    info: NodeInfo,
    contract: NodeContract,
    *,
    source: _SourceInfo,
    metrics: NodeMetrics,
) -> list[PurityViolation]:
    warnings: list[PurityViolation] = []
    metadata_tokens = _tokens(" ".join((info.type_key, info.display_name, info.category, info.description)))
    contract_tokens = _tokens(" ".join((*contract.requires, *contract.provides)))
    semantic_tokens = _tokens(" ".join(part for values in (*contract.input_semantics.values(), *contract.output_semantics.values()) for part in values))
    if contract_tokens and not (contract_tokens & (metadata_tokens | semantic_tokens)):
        warnings.append(
            _violation(
                "responsibility_mismatch",
                "node metadata/semantics do not visibly describe contract keys",
                source=source,
                severity="warning",
                failure_layer="contract",
                suggested_fix_type="fix_contract",
                details={"metadata_tokens": sorted(metadata_tokens), "contract_tokens": sorted(contract_tokens)},
            )
        )
    for key in (*contract.requires, *contract.provides):
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
        return [_violation("example_shape", "CONTRACT.examples must be a tuple of example mappings", source=source, severity="warning", failure_layer="contract", suggested_fix_type="fix_contract")]
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            return [_violation("example_shape", f"CONTRACT.examples[{index}] must be a mapping", source=source, severity="warning", failure_layer="contract", suggested_fix_type="fix_contract")]
        for field_name in ("inputs", "params", "outputs"):
            if field_name not in item or not isinstance(item[field_name], Mapping):
                return [_violation("example_shape", f"CONTRACT.examples[{index}].{field_name} must be a mapping", source=source, severity="warning", failure_layer="contract", suggested_fix_type="fix_contract")]
    return []


def _validate_examples(node_cls: type[PureNode], contract: NodeContract, *, source: _SourceInfo) -> list[PurityViolation]:
    if not contract.examples:
        return [_missing_examples_violation(source)]
    findings: list[PurityViolation] = []
    covers_contract = False
    for index, example in enumerate(contract.examples):
        if not isinstance(example, Mapping):
            continue
        inputs, params, expected_outputs = _example_payload(example)
        if _example_covers_contract(contract, inputs, expected_outputs):
            covers_contract = True
        else:
            findings.append(_example_gap_violation(index, source=source))
            continue
        findings.extend(_validate_example_output(node_cls, inputs, params, expected_outputs, index, source=source))
    if not covers_contract:
        findings.append(_no_covering_example_violation(source))
    return findings


def _example_payload(example: Mapping[str, object]) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    return (
        dict(example.get("inputs", {})),
        dict(example.get("params", {})),
        dict(example.get("outputs", {})),
    )


def _example_covers_contract(contract: NodeContract, inputs: Mapping[str, object], outputs: Mapping[str, object]) -> bool:
    return set(contract.requires) <= set(inputs) and set(outputs) == set(contract.provides)


def _validate_example_output(
    node_cls: type[PureNode],
    inputs: Mapping[str, object],
    params: Mapping[str, object],
    expected_outputs: Mapping[str, object],
    index: int,
    *,
    source: _SourceInfo,
) -> list[PurityViolation]:
    actual_outputs, failure = _run_example(node_cls, inputs, params, index, source=source)
    if failure is not None:
        return [failure]
    findings = _compare_example_outputs(actual_outputs, expected_outputs, index, source=source)
    findings.extend(_validate_example_snapshot(actual_outputs, index, source=source))
    return findings


def _run_example(
    node_cls: type[PureNode],
    inputs: Mapping[str, object],
    params: Mapping[str, object],
    index: int,
    *,
    source: _SourceInfo,
) -> tuple[object, PurityViolation | None]:
    try:
        return node_cls().run_pure(deepcopy(dict(inputs)), deepcopy(dict(params))), None
    except Exception as exc:  # noqa: BLE001 - health report must contain checker-visible failure.
        return None, _violation(
            "example_failed",
            f"CONTRACT.examples[{index}] raised {type(exc).__name__}: {exc}",
            source=source,
            failure_layer="contract",
            suggested_fix_type="fix_node",
            details={"example_index": index},
        )


def _compare_example_outputs(actual_outputs: object, expected_outputs: Mapping[str, object], index: int, *, source: _SourceInfo) -> list[PurityViolation]:
    if actual_outputs == expected_outputs:
        return []
    return [
        _violation(
            "example_failed",
            f"CONTRACT.examples[{index}] expected outputs do not match run_pure outputs",
            source=source,
            failure_layer="contract",
            suggested_fix_type="fix_node",
            details={"example_index": index, "expected": dict(expected_outputs), "actual": actual_outputs},
        )
    ]


def _validate_example_snapshot(actual_outputs: object, index: int, *, source: _SourceInfo) -> list[PurityViolation]:
    try:
        json.dumps(actual_outputs, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        return [
            _violation(
                "example_failed",
                f"CONTRACT.examples[{index}] output is not JSON snapshot serializable: {exc}",
                source=source,
                failure_layer="contract",
                suggested_fix_type="fix_contract",
                details={"example_index": index},
            )
        ]
    return []


def _missing_examples_violation(source: _SourceInfo) -> PurityViolation:
    return _contract_example_warning("missing_examples", "node should provide at least one minimal example in CONTRACT.examples", source=source)


def _example_gap_violation(index: int, *, source: _SourceInfo) -> PurityViolation:
    return _violation(
        "example_contract_gap",
        f"CONTRACT.examples[{index}] does not cover requires/provides",
        source=source,
        severity="warning",
        failure_layer="contract",
        suggested_fix_type="fix_contract",
        details={"example_index": index},
    )


def _no_covering_example_violation(source: _SourceInfo) -> PurityViolation:
    return _contract_example_warning("example_contract_gap", "node examples exist but none covers all requires/provides", source=source)


def _contract_example_warning(code: str, message: str, *, source: _SourceInfo) -> PurityViolation:
    return _violation(
        code,
        message,
        source=source,
        severity="warning",
        failure_layer="contract",
        suggested_fix_type="fix_contract",
    )


