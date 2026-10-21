"""Assemble native Python bindings from one workflow's selected plugins."""
from __future__ import annotations

from dataclasses import replace, fields
from pathlib import Path

from vibeflow.core.findings import Finding, HealthFinding
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.project.policy import default_effective_policy
from vibeflow.tooling.application.python.project.types import WorkspaceEnvironment
from vibeflow.tooling.project.workspace_model import WorkspaceConfig, WorkspaceRoot
from vibeflow.tooling.application.python.project.declarations import declared_python_registry as build_workspace_node_registry
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def build_workspace_environment(workspace: WorkspaceConfig, config_path=None, *, preparation=None, governance=None) -> WorkspaceEnvironment:
    from vibeflow.tooling.project.preparation import ProjectPreparation
    root = workspace.root_for_path(Path(config_path).resolve())
    preparation = preparation or ProjectPreparation(workspace, root=root, workflow=config_path)
    prepared = preparation.workflow_resources(config_path)
    governance = governance or preparation.review()
    registry = build_workspace_node_registry(workspace, config_path=config_path, prepared_resources=prepared)
    from vibeflow.tooling.application.python.project.resource_selection import select_python_resources
    available_resources, resource_findings = select_python_resources({}, registry=registry)
    return WorkspaceEnvironment(registry=registry, plugin_registry=PluginRegistry(),
        resources=available_resources, available_resources=available_resources,
        effective_policy=default_effective_policy(), findings=(*resource_findings, *governance.findings))


def load_workspace_resources(workspace: WorkspaceConfig, config_path=None):
    from vibeflow.tooling.application.python.project.resource_selection import select_python_resources
    return select_python_resources({}, registry=build_workspace_node_registry(workspace, config_path=config_path))


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
        if not isinstance(finding, Finding):
            raise TypeError("workspace diagnostics must be Finding values")
        if not isinstance(finding, HealthFinding):
            finding = HealthFinding(**{item.name:getattr(finding, item.name) for item in fields(Finding)},
                failure_layer="governance", rule_source="rule:" + finding.definition_id)
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
