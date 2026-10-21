from __future__ import annotations

from pathlib import Path

from vibeflow.tooling.application.python.reports import (
    config_load_error_report,
    graph_config_error_report,
)
from vibeflow.targets.python.project.compiler import GraphCompiler, GraphCompileError
from vibeflow.tooling.project.config_schema import collect_config_schema_findings
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts
from vibeflow.core.flow import GraphConfigError
from vibeflow.core.findings import HealthReport, HealthFinding


def validate_config_path(path: Path) -> HealthReport:
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
    from vibeflow.tooling.project.diagnostics import workspace_or_report
    workspace = workspace_or_report(path, registered_source=True)
    return workspace if isinstance(workspace, HealthReport) else validate_workspace_config_path(path, workspace=workspace)


def inspect_config_payload(path: Path) -> tuple[dict[str, object], int]:
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.project.diagnostics import workspace_or_report
    workspace = workspace_or_report(path, registered_source=True)
    if isinstance(workspace, HealthReport):
        return {"health":workspace.to_dict()}, 1
    prepared = _inspect_workspace_graph(path, workspace=workspace)
    if isinstance(prepared, HealthReport):
        report = prepared
    else:
        report = prepared.health
        document, graph, compiled = prepared.document, prepared.graph, prepared.compiled
    payload: dict[str, object] = {"health": report.to_dict()}
    if report.status not in {"PASS", "CONCERNS"}:
        return payload, 1
    payload["config"] = {
        "inputs": providers_to_dicts(graph.inputs),
        "outputs": requirements_to_dicts(graph.outputs),
        "nodes": [
            {
                "id": node.id,
                "definition_id": node.definition_id,
                "requires": requirements_to_dicts(node.requires),
                "provides": providers_to_dicts(node.provides),
                "status": node.status,
                "planned_behavior": node.planned_behavior.to_dict(),
                "similar_to": node.similar_to.to_dict(),
            }
            for node in graph.nodes
        ],
        "nodeset_types": [
            {
                "type_key": nodeset.type_key,
                "expand": nodeset.expand,
                "display_name": nodeset.display_name,
                "description": nodeset.description,
                "requires": requirements_to_dicts(nodeset.requires),
                "provides": providers_to_dicts(nodeset.provides),
                "status": nodeset.status,
                "planned_behavior": nodeset.planned_behavior.to_dict(),
                "node_count": len(nodeset.graph.nodes),
            }
            for nodeset in graph.nodeset_types.values()
        ],
        "nodeset_imports": [dict(item) for item in document.nodeset_imports],
        "resources": report.info.get("resources", {}),
        "max_steps": graph.max_steps,
        "effective_edges": [{"from": edge.source, "to": edge.target, "when": edge.when} for edge in compiled.effective_edges],
    }
    return payload, 0


def _inspect_workspace_graph(path, *, workspace):
    """Consume one prepared/check result without invoking the export pipeline."""
    from dataclasses import replace
    from vibeflow.tooling.application.python.workspace_service import (
        _environment_or_report, _prepare_workspace_graph, _validate_prepared_workspace_graph,
        _workspace_runtime_options, _python_check_scope,
    )
    env = _environment_or_report(workspace, path)
    if isinstance(env, HealthReport):
        return env
    with _python_check_scope(env.registry):
        prepared = _prepare_workspace_graph(path, workspace=workspace, env=env)
        if isinstance(prepared, HealthReport):
            return prepared
        _validate_prepared_workspace_graph(prepared, env=env, workspace=workspace,
            runtime_options=_workspace_runtime_options(path, workspace=workspace))
        return prepared


__all__ = ["inspect_config_payload", "validate_config_path"]
