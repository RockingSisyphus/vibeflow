"""Filesystem adapter for Python Target workflow-quality facts."""

from __future__ import annotations

import inspect
from pathlib import Path

from vibeflow.core.flow import GraphConfig
from vibeflow.targets.python.project.base_lib import (
    node_base_lib_imports,
    scan_base_lib,
)
from vibeflow.targets.python.project.registry import NodeRegistry, NodeRegistryError
from vibeflow.targets.python.quality.source_analysis import PurityPolicy
from vibeflow.targets.python.quality.workflow.facts import PythonNodeQualityFacts


def collect_python_workflow_quality_facts(
    graph: GraphConfig,
    *,
    registry: NodeRegistry,
    policy: PurityPolicy | None = None,
) -> dict[str, PythonNodeQualityFacts]:
    """Read project files and return plain facts keyed by node type."""

    effective_policy = policy or PurityPolicy()
    reports_by_root = {}
    facts: dict[str, PythonNodeQualityFacts] = {}
    type_keys = sorted({spec.type_used for spec in graph.nodes})
    for type_key in type_keys:
        try:
            node_cls = registry.get(type_key)
        except NodeRegistryError:
            continue
        source_file = inspect.getsourcefile(node_cls)
        report = None
        if source_file:
            root = Path(source_file).parent.resolve()
            if root not in reports_by_root:
                default_base_lib = root / "base_lib"
                reports_by_root[root] = (
                    scan_base_lib(root, policy=effective_policy)
                    if effective_policy.allowed_base_lib_paths
                    or default_base_lib.exists()
                    else None
                )
            report = reports_by_root[root]
        facts[type_key] = PythonNodeQualityFacts(
            type_key=type_key,
            base_lib_imports=node_base_lib_imports(node_cls),
            base_lib_report=report,
        )
    return facts


__all__ = ["collect_python_workflow_quality_facts"]
