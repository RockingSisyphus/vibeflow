from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class BaseLibFinding:
    rule_id: str
    message: str
    severity: str = "error"
    object_type: str = "base_lib"
    object_id: str = ""
    source_location: Mapping[str, object] = field(default_factory=dict)
    failure_layer: str = "base_lib"
    suggested_fix_type: str = "fix_base_lib"
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BaseLibModuleReport:
    module: str
    path: str
    source_lines: int
    source_bytes: int
    function_count: int
    branch_count: int
    max_nesting_depth: int
    imports: tuple[str, ...]
    findings: tuple[BaseLibFinding, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module,
            "path": self.path,
            "source_lines": self.source_lines,
            "source_bytes": self.source_bytes,
            "function_count": self.function_count,
            "branch_count": self.branch_count,
            "max_nesting_depth": self.max_nesting_depth,
            "imports": list(self.imports),
            "findings": [finding.__dict__ | {"source_location": dict(finding.source_location), "details": dict(finding.details)} for finding in self.findings],
        }


@dataclass(frozen=True)
class BaseLibScanReport:
    roots: tuple[str, ...]
    modules: tuple[BaseLibModuleReport, ...]
    dependency_edges: tuple[tuple[str, str], ...]
    findings: tuple[BaseLibFinding, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "roots": list(self.roots),
            "modules": [module.to_dict() for module in self.modules],
            "dependency_edges": [list(edge) for edge in self.dependency_edges],
            "findings": [finding.__dict__ | {"source_location": dict(finding.source_location), "details": dict(finding.details)} for finding in self.findings],
        }


@dataclass(frozen=True)
class BaseLibDependencySummary:
    imported_modules: tuple[str, ...] = ()
    longest_chain_length: int = 0
    longest_chain: tuple[str, ...] = ()
    recursive_chains: tuple[tuple[str, ...], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "imported_modules": list(self.imported_modules),
            "longest_chain_length": self.longest_chain_length,
            "longest_chain": list(self.longest_chain),
            "recursive_chains": [list(chain) for chain in self.recursive_chains],
        }
