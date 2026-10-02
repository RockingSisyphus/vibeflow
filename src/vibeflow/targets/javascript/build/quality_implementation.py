"""Descriptor-owned JavaScript implementation facts and shared numeric rules."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vibeflow.core.descriptors import DescriptorCatalogs
from vibeflow.core.findings import HealthFinding
from vibeflow.core.quality.implementation import (
    ImplementationLimits,
    ImplementationMetrics,
    analyze_call_graph,
    evaluate_base_lib_dependency_chain,
    evaluate_base_lib_implementation,
    evaluate_node_implementation,
)
from vibeflow.targets.javascript.build.project_paths import safe_project_path
from vibeflow.targets.javascript.build.toolchain import DriverQualityResult, run_quality_facts_driver


def inspect_registered_implementations(
    catalogs: DescriptorCatalogs,
    *,
    project_root: Path,
    package_root: Path,
    selected_files: tuple[str, ...],
    policy_data: Mapping[str, Any],
    node_command: str = "node",
    prefetched_facts: DriverQualityResult | None = None,
) -> tuple[HealthFinding, ...]:
    """Inspect only the selected registered files, never unregistered source."""

    ownership, descriptors = registered_implementation_requests(
        catalogs, project_root=project_root, selected_files=selected_files,
    )
    if not ownership:
        return ()
    expected_paths = {
        Path(item["path"]).relative_to(project_root).as_posix() for item in ownership
    }
    if prefetched_facts is not None and not expected_paths.issubset(
        {str(item["path"]) for item in prefetched_facts.files}
    ):
        prefetched_facts = None
    result = prefetched_facts or run_quality_facts_driver(
        {
            "qualityRoot": str(project_root),
            "qualityFiles": sorted({item["path"] for item in ownership}),
            "qualityImplementations": ownership,
        },
        package_root=package_root,
        node_command=node_command,
    )
    return evaluate_registered_facts(
        result, ownership, descriptors,
        project_root=project_root, policy_data=policy_data,
    )


def registered_implementation_requests(
    catalogs: DescriptorCatalogs,
    *,
    project_root: Path,
    selected_files: tuple[str, ...],
) -> tuple[list[dict[str, str]], dict[tuple[str, str, str], object]]:
    """Describe each descriptor/export while preserving one source file identity."""

    selected = {str(Path(value).resolve()) for value in selected_files}
    ownership: list[dict[str, str]] = []
    descriptors: dict[tuple[str, str, str], object] = {}
    for descriptor in catalogs.nodes:
        for implementation in descriptor.implementations:
            if implementation.language not in {"javascript", "typescript"} or implementation.source.kind != "file":
                continue
            if str((project_root / implementation.source.ref).resolve()) not in selected:
                continue
            source = safe_project_path(project_root, implementation.source.ref, subject=f"node '{descriptor.type_key}' source", require_file=True)
            if str(source) not in selected:
                continue
            export = implementation.source.export or "run"
            key = (descriptor.type_key, str(source), export)
            if key not in descriptors:
                descriptors[key] = descriptor
                ownership.append({"type_key": descriptor.type_key, "path": str(source), "export": export, "kind": "node"})
    for descriptor in catalogs.base_libs:
        for implementation in descriptor.implementations:
            if implementation.language not in {"javascript", "typescript"} or implementation.source.kind != "file":
                continue
            if str((project_root / implementation.source.ref).resolve()) not in selected:
                continue
            source = safe_project_path(project_root, implementation.source.ref, subject=f"base_lib '{descriptor.id}' source", require_file=True)
            if str(source) not in selected:
                continue
            export = implementation.source.export or ""
            key = (descriptor.id, str(source), export)
            if key not in descriptors:
                descriptors[key] = descriptor
                ownership.append({"type_key": descriptor.id, "path": str(source), "export": export, "kind": "base_lib"})
    return ownership, descriptors


def evaluate_registered_facts(
    result,
    ownership: list[dict[str, str]],
    descriptors: Mapping[tuple[str, str, str], object],
    *,
    project_root: Path,
    policy_data: Mapping[str, Any],
) -> tuple[HealthFinding, ...]:
    """Apply the shared Core rules to one already extracted Program result."""

    files = {str(item["path"]): item for item in result.files}
    edges = {
        path: tuple(str(target) for target in item["imports"] if str(target) in files)
        for path, item in files.items()
    }
    base_roots = {
        Path(item["path"]).relative_to(project_root).as_posix()
        for item in ownership if item["kind"] == "base_lib"
    }
    base_modules = set(base_roots)
    pending = list(base_roots)
    while pending:
        for target in edges.get(pending.pop(), ()):
            if target not in base_modules:
                base_modules.add(target)
                pending.append(target)
    limits = _implementation_limits(policy_data)
    findings: list[HealthFinding] = []
    for item in result.findings:
        findings.append(HealthFinding(
            rule_id=str(item["code"]),
            severity="error",
            object_type="file",
            object_id=str(item.get("object_id", "")),
            source_location={
                "path": str(item.get("path", "")),
                "line": int(item.get("line", 1)),
                "column": int(item.get("column", 1)),
            },
            message=str(item.get("message", "JavaScript syntax error")),
            suggested_fix_type="fix_syntax",
        ))
    expected = {Path(item["path"]).relative_to(project_root).as_posix() for item in ownership}
    if not expected.issubset(files):
        raise ValueError("JavaScript parser omitted registered implementation source")
    for fact in result.implementations:
        relative = str(fact["path"])
        absolute = str((project_root / relative).resolve())
        kind = str(fact["kind"])
        key = (str(fact["type_key"]), absolute, str(fact["export"]))
        descriptor = descriptors.get(key)
        file = files.get(relative)
        if descriptor is None or file is None:
            continue
        contract = getattr(descriptor, "contract", None)
        call_graph = fact.get("calls", {})
        if not isinstance(call_graph, Mapping):
            call_graph = {}
        metrics = ImplementationMetrics(
            source_lines=int(file["lines"]),
            source_bytes=int(file["bytes"]),
            function_count=int(file["function_count"]),
            branch_count=int(file["branch_count"]),
            max_nesting_depth=int(file["max_nesting_depth"]),
            param_count=len(contract.params_schema) if contract is not None else 0,
            contract_key_count=(len(contract.requires) + len(contract.provides)) if contract is not None else 0,
            call_chain=analyze_call_graph(call_graph, entry=str(fact.get("entry", ""))),
            report_metrics={
                "function_count": int(file["function_count"]),
                "branch_count": int(file["branch_count"]),
                "max_nesting_depth": int(file["max_nesting_depth"]),
                "param_count": len(contract.params_schema) if contract is not None else 0,
                "contract_key_count": (len(contract.requires) + len(contract.provides)) if contract is not None else 0,
            },
        )
        evaluated = (
            evaluate_node_implementation(metrics, limits)
            if kind == "node"
            else evaluate_base_lib_implementation(metrics, limits)
        )
        if kind == "node":
            starts: set[str] = set()
            visited = {relative}
            pending = [relative]
            while pending:
                for target in edges.get(pending.pop(), ()):
                    if target in base_modules:
                        starts.add(target)
                    elif target not in visited:
                        visited.add(target)
                        pending.append(target)
            graph = {
                module: tuple(target for target in edges.get(module, ()) if target in base_modules)
                for module in base_modules
            }
            graph["node"] = tuple(sorted(starts))
            dependency = evaluate_base_lib_dependency_chain(
                analyze_call_graph(graph, entry="node") if starts else analyze_call_graph({}, entry="node"),
                limits,
            )
            if dependency is not None:
                evaluated = (*evaluated, dependency)
        for item in evaluated:
            findings.append(HealthFinding(
                rule_id=item.rule_id,
                severity=item.severity,
                object_type=kind,
                object_id=str(fact["type_key"]),
                source_location={"path": absolute, "line": 1},
                message=item.message,
                suggested_fix_type=item.suggested_fix_type,
                details={**dict(item.details), "source": relative, "export": str(fact["export"])},
            ))
    return tuple(findings)


def _implementation_limits(data: Mapping[str, Any]) -> ImplementationLimits:
    source = data.get("node_source", {})
    complexity = data.get("complexity", {})
    maintenance = data.get("maintainability", {})
    return ImplementationLimits(
        max_source_lines=int(source.get("max_lines", 500)),
        max_source_bytes=int(source.get("max_bytes", 60000)),
        warn_source_lines=source.get("warn_lines", 450),
        warn_source_bytes=source.get("warn_bytes", 54000),
        max_functions=complexity.get("max_functions"),
        max_branches=complexity.get("max_branches"),
        max_nesting_depth=complexity.get("max_nesting_depth"),
        max_params=complexity.get("max_params"),
        max_contract_keys=complexity.get("max_contract_keys"),
        warn_call_chain_length=int(maintenance.get("warn_call_chain_length", 4)),
        max_call_chain_length=int(maintenance.get("max_call_chain_length", 4)),
        warn_dependency_chain_length=int(maintenance.get("warn_dependency_chain_length", 4)),
        max_dependency_chain_length=int(maintenance.get("max_dependency_chain_length", 6)),
    )


__all__ = ["evaluate_registered_facts", "inspect_registered_implementations", "registered_implementation_requests"]
