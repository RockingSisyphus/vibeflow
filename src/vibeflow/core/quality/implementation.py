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



__all__ = ["CallChain", "ImplementationFinding", "ImplementationLimits", "ImplementationMetrics", "analyze_call_graph"]
