from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .data_contract import DataProvider, DataRequirement
from .node import NodeContract, NodeInfo, PureNode
from .purity_helpers import _dedupe_violations, _violation
from .purity_metrics import _ComplexityCounter, _analyze_internal_call_chain
from .purity_source import _parse_source, _source_info
from .purity_types import (
    BANNED_ATTR_CALLS,
    BANNED_CALL_NAMES,
    BANNED_IMPORT_ROOTS,
    NodeMetrics,
    PurityPolicy,
    PurityViolation,
)
from .purity_validators import (
    _validate_architecture_smells,
    _validate_call_chain_metrics,
    _validate_complexity_metrics,
    _validate_contract,
    _validate_examples,
    _validate_flow_kind_contract,
    _validate_interface,
    _validate_node_info,
    _validate_source_size,
)
from .purity_visitors import ModulePurityVisitor, NodePurityVisitor


@dataclass(frozen=True)
class _ClassVisitorContext:
    class_tree: object
    contract: object
    policy: PurityPolicy
    source: object
    known_node_modules: tuple[str, ...]
    known_node_class_names: tuple[str, ...]


def validate_node_class(
    node_cls: type[PureNode],
    *,
    policy: PurityPolicy | None = None,
    expected_type: str | None = None,
    known_node_modules: tuple[str, ...] = (),
    known_node_class_names: tuple[str, ...] = (),
    scan_module: bool = False,
) -> list[PurityViolation]:
    policy = policy or PurityPolicy()
    source = _source_info(node_cls)
    violations: list[PurityViolation] = []
    info = getattr(node_cls, "NODE_INFO", None)
    contract = getattr(node_cls, "CONTRACT", None)

    _append_contract_violations(node_cls, info, contract, expected_type, source, violations)

    if source.class_text is None:
        violations.append(_source_unavailable_violation(source))
        return violations

    if isinstance(info, NodeInfo) and info.external:
        _append_examples_if_clean(node_cls, contract, source, violations)
        return _dedupe_violations(violations)

    violations.extend(_validate_source_size(source.class_text, policy=policy, source=source))
    class_tree = _parse_source(source.class_text, source=source)
    if isinstance(class_tree, PurityViolation):
        violations.append(class_tree)
        return violations
    metrics = collect_node_metrics(node_cls)
    violations.extend(_validate_complexity_metrics(metrics, policy=policy, source=source))
    violations.extend(_validate_call_chain_metrics(metrics, policy=policy, source=source))
    if isinstance(info, NodeInfo) and isinstance(contract, NodeContract) and _contract_items_valid(contract):
        violations.extend(_validate_architecture_smells(info, contract, source=source, metrics=metrics))

    visitor_context = _ClassVisitorContext(class_tree, contract, policy, source, known_node_modules, known_node_class_names)
    _append_class_visitor_violations(visitor_context, violations)
    _append_examples_if_clean(node_cls, contract, source, violations)

    if scan_module:
        _append_module_violations(node_cls, source, policy, known_node_modules, known_node_class_names, violations)

    return _dedupe_violations(violations)


def _append_contract_violations(node_cls, info, contract, expected_type, source, violations: list[PurityViolation]) -> None:
    violations.extend(_validate_node_info(info, expected_type=expected_type, source=source))
    violations.extend(_validate_contract(contract, source=source))
    violations.extend(_validate_interface(node_cls, source=source))
    if isinstance(info, NodeInfo) and isinstance(contract, NodeContract) and _contract_items_valid(contract):
        violations.extend(_validate_flow_kind_contract(info, contract, source=source))


def _source_unavailable_violation(source) -> PurityViolation:
    return _violation(
        "source_unavailable",
        "node source is unavailable for static purity check",
        source=source,
        suggested_fix_type="fix_node",
    )


def _append_examples_if_clean(node_cls, contract, source, violations: list[PurityViolation]) -> None:
    if isinstance(contract, NodeContract) and not any(violation.severity == "error" for violation in violations):
        violations.extend(_validate_examples(node_cls, contract, source=source))


def _append_class_visitor_violations(context: _ClassVisitorContext, violations: list[PurityViolation]) -> None:
    contract = context.contract if isinstance(context.contract, NodeContract) and _contract_items_valid(context.contract) else None
    visitor = NodePurityVisitor(
        policy=context.policy,
        source=context.source,
        contract=contract,
        known_node_modules=context.known_node_modules,
        known_node_class_names=context.known_node_class_names,
        line_offset=context.source.class_start_line - 1,
    )
    visitor.visit(context.class_tree)
    violations.extend(visitor.violations)


def _contract_items_valid(contract: NodeContract) -> bool:
    return all(isinstance(item, DataRequirement) for item in contract.requires) and all(isinstance(item, DataProvider) for item in contract.provides)


def _append_module_violations(
    node_cls: type[PureNode],
    source,
    policy: PurityPolicy,
    known_node_modules: tuple[str, ...],
    known_node_class_names: tuple[str, ...],
    violations: list[PurityViolation],
) -> None:
    if not source.module_text:
        return
    module_tree = _parse_source(source.module_text, source=source)
    if isinstance(module_tree, PurityViolation):
        violations.append(module_tree)
        return
    module_visitor = ModulePurityVisitor(
        policy=policy,
        source=source,
        node_class_name=node_cls.__name__,
        known_node_modules=known_node_modules,
        known_node_class_names=known_node_class_names,
    )
    module_visitor.visit(module_tree)
    violations.extend(module_visitor.violations)



def collect_node_metrics(node_cls: type[Any]) -> NodeMetrics:
    source = _source_info(node_cls)
    contract = getattr(node_cls, "CONTRACT", None)
    if source.class_text is None:
        return NodeMetrics()
    tree = _parse_source(source.class_text, source=source)
    if isinstance(tree, PurityViolation):
        return NodeMetrics(source_lines=len(source.class_text.splitlines()), source_bytes=len(source.class_text.encode("utf-8")))
    counter = _ComplexityCounter()
    counter.visit(tree)
    call_chain = _analyze_internal_call_chain(tree)
    requires = getattr(contract, "requires", ()) if isinstance(contract, NodeContract) else ()
    provides = getattr(contract, "provides", ()) if isinstance(contract, NodeContract) else ()
    params_schema = getattr(contract, "params_schema", {}) if isinstance(contract, NodeContract) else {}
    return NodeMetrics(
        source_lines=len(source.class_text.splitlines()),
        source_bytes=len(source.class_text.encode("utf-8")),
        function_count=counter.function_count,
        branch_count=counter.branch_count,
        max_nesting_depth=counter.max_nesting_depth,
        param_count=len(params_schema) if isinstance(params_schema, Mapping) else 0,
        requires_count=len(requires),
        provides_count=len(provides),
        contract_key_count=len(requires) + len(provides),
        function_names=tuple(counter.function_names),
        run_pure_fingerprint=counter.run_pure_fingerprint,
        run_pure_shape=counter.run_pure_shape,
        call_chain_length=call_chain.length,
        call_chain_path=call_chain.path,
        recursive_call_chains=call_chain.recursive_paths,
    )

