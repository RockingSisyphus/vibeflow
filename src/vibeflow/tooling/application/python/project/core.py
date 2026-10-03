"""Assemble native Python bindings from one workflow's selected plugins."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.tooling.application.python.project.policy import resolve_workspace_effective_policy
from vibeflow.tooling.application.python.project.types import WorkspaceConfig, WorkspaceEnvironment, WorkspaceRoot
from vibeflow.tooling.project.workspace_loader import load_workspace_config as _load_neutral_workspace_config


def load_workspace_config(path: str | Path) -> WorkspaceConfig:
    return _load_neutral_workspace_config(path)


def build_workspace_environment(workspace: WorkspaceConfig, config_path=None) -> WorkspaceEnvironment:
    registry = build_workspace_node_registry(workspace, config_path=config_path)
    from vibeflow.tooling.application.python.project.contributions import contributed_resources
    resource_registries, available_resources, resource_findings = contributed_resources(workspace, registry)
    policy_result = resolve_workspace_effective_policy(workspace.policy, workspace_path=workspace.path)
    return WorkspaceEnvironment(registry=registry, plugin_registry=PluginRegistry(),
        resources=available_resources, available_resources=available_resources,
        resource_registries=resource_registries, effective_policy=policy_result.effective_policy,
        findings=(*resource_findings, *policy_result.findings))


def build_workspace_node_registry(workspace: WorkspaceConfig, config_path=None) -> NodeRegistry:
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry
    return declared_python_registry(workspace, config_path=config_path)


def load_workspace_resources(workspace: WorkspaceConfig, config_path=None):
    from vibeflow.tooling.application.python.project.contributions import contributed_resources
    return contributed_resources(workspace, build_workspace_node_registry(workspace, config_path=config_path))


def workspace_finding(
    rule_id: str,
    message: str,
    *,
    root: WorkspaceRoot,
    source_path: Path,
    object_id: str = "workspace",
    failure_layer: str = "workspace",
    severity: str = "error",
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity=severity,
        object_type=failure_layer,
        object_id=object_id,
        source_location={"path": str(source_path)},
        failure_layer=failure_layer,
        message=message,
        suggested_fix_type="fix_config",
        root_id=root.id,
        root_path=str(root.path),
        source_path=str(source_path),
    )


def annotate_findings(findings, *, root: WorkspaceRoot, source_path: Path) -> tuple[HealthFinding, ...]:
    out: list[HealthFinding] = []
    for finding in findings:
        if isinstance(finding, HealthFinding):
            out.append(with_health_source(finding, root=root, source_path=source_path))
    return tuple(out)


def with_health_source(finding: HealthFinding, *, root: WorkspaceRoot, source_path: Path) -> HealthFinding:
    return replace(
        finding,
        root_id=finding.root_id or root.id,
        root_path=finding.root_path or str(root.path),
        source_path=finding.source_path or str(source_path),
    )


__all__ = [
    "annotate_findings",
    "build_workspace_environment",
    "build_workspace_node_registry",
    "load_workspace_config",
    "load_workspace_resources",
    "with_health_source",
    "workspace_finding",
]
