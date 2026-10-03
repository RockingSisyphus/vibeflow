from __future__ import annotations

from pathlib import Path

from vibeflow.tooling.application.python.reports import (
    config_load_error_report,
    dedupe_findings,
    fail_report,
    graph_config_error_report,
)
from vibeflow.targets.python.project.compiler import GraphCompiler, GraphCompileError
from vibeflow.tooling.project.config_loader import ConfigLoadError, load_config_document
from vibeflow.tooling.application.python.project.resources import load_config_resources
from vibeflow.tooling.project.config_schema import collect_config_schema_findings
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts
from vibeflow.core.flow import GraphConfigError
from vibeflow.core.findings import HealthReport, HealthFinding
from vibeflow.targets.python.quality.workflow.nodesets import validate_nodeset_depth
from vibeflow.tooling.project.graph_config import parse_graph_config, project_root_for_config
from vibeflow.tooling.application.python.project.effective_policy import default_effective_policy, resolve_effective_policy


def validate_config_path(path: Path, *, policy_path: Path | None = None) -> HealthReport:
    try:
        document = load_config_document(path)
    except ConfigLoadError as exc:
        return config_load_error_report(exc, object_type="config", object_id=str(path))

    from dataclasses import replace
    from vibeflow.tooling.project.workspace_loader import load_project_workspace, find_project_config
    policy_result = resolve_effective_policy(document.data, config_path=path, explicit_policy_path=policy_path)
    if policy_result.findings:
        return HealthReport(status="FAIL", errors=tuple(policy_result.findings))
    if find_project_config(path) is not None:
        from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
        workspace = load_project_workspace(path)
        workspace = replace(workspace, policy=policy_result.effective_policy.data)
        return validate_workspace_config_path(path, workspace=workspace)
    schema_findings = collect_config_schema_findings(document.data)
    errors = tuple(item for item in schema_findings if item.severity == "error")
    if errors:
        return HealthReport(status="FAIL", errors=errors)
    if document.data.get("plugins"):
        return HealthReport(status="ERROR", errors=(HealthFinding(
            rule_id="PLUGIN.CONFIG.ROOT", severity="error", object_type="config", object_id=str(path),
            message="custom plugins require an owning vibeflow_project.jsonc", failure_layer="workspace"),))
    try:
        graph = parse_graph_config(document.data, project_root=project_root_for_config(path))
    except GraphConfigError as exc:
        return graph_config_error_report(exc, path=path, effective_policy=policy_result.effective_policy.to_dict())
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
    return validate_graph_health(graph, effective_policy=policy_result.effective_policy)


def _configured_nodeset_depth(path: Path) -> int:
    from vibeflow.tooling.project.workspace_loader import find_project_config, load_project_workspace

    project = find_project_config(path)
    if project is None:
        return 4
    workspace = load_project_workspace(project)
    return int(workspace.roots[0].runtime_options.get("nodeset_max_depth", 4))


def inspect_config_payload(path: Path, *, policy_path: Path | None = None) -> tuple[dict[str, object], int]:
    from dataclasses import replace
    from vibeflow.tooling.project.workspace_loader import find_project_config, load_project_workspace
    compiled = None
    if find_project_config(path) is not None:
        from vibeflow.tooling.application.python.workspace_service import (
            _environment_or_report, _prepare_workspace_graph, _validate_prepared_workspace_graph,
            _workspace_runtime_options,
        )
        document = load_config_document(path)
        policy = resolve_effective_policy(document.data, config_path=path, explicit_policy_path=policy_path)
        workspace = replace(load_project_workspace(path), policy=policy.effective_policy.data)
        env = _environment_or_report(workspace, path) if not policy.findings else HealthReport(status="FAIL", errors=tuple(policy.findings))
        prepared = env if isinstance(env, HealthReport) else _prepare_workspace_graph(path, workspace=workspace, env=env)
        if isinstance(prepared, HealthReport):
            report = prepared
        else:
            report = _validate_prepared_workspace_graph(prepared, env=env, workspace=workspace,
                runtime_options=_workspace_runtime_options(path, workspace=workspace))
            document, graph = prepared[:2]
            compiled = GraphCompiler().compile(graph, registry=env.registry)
    else:
        report = validate_config_path(path, policy_path=policy_path)
    payload: dict[str, object] = {"health": report.to_dict()}
    if report.status not in {"PASS", "CONCERNS"}:
        return payload, 1
    if compiled is None:
        document = load_config_document(path)
        graph = parse_graph_config(document.data, project_root=project_root_for_config(path))
        compiled = GraphCompiler().compile(graph)
    payload["config"] = {
        "inputs": providers_to_dicts(graph.inputs),
        "outputs": requirements_to_dicts(graph.outputs),
        "nodes": [
            {
                "id": node.id,
                "type_used": node.type_used,
                "requires": requirements_to_dicts(node.requires),
                "provides": providers_to_dicts(node.provides),
                "status": node.status,
                "planned_behavior": node.planned_behavior.to_dict(),
                "similar_to": node.similar_to.to_dict(),
            }
            for node in graph.nodes
        ],
        "nodesets": [
            {
                "type_key": nodeset.type_key,
                "display_name": nodeset.display_name,
                "description": nodeset.description,
                "requires": requirements_to_dicts(nodeset.requires),
                "provides": providers_to_dicts(nodeset.provides),
                "status": nodeset.status,
                "planned_behavior": nodeset.planned_behavior.to_dict(),
                "node_count": len(nodeset.graph.nodes),
            }
            for nodeset in graph.nodesets.values()
        ],
        "nodeset_imports": [dict(item) for item in document.nodeset_imports],
        "resources": report.info.get("resources", {}),
        "max_steps": graph.max_steps,
        "effective_edges": [{"from": edge.source, "to": edge.target, "when": edge.when} for edge in compiled.effective_edges],
    }
    return payload, 0


__all__ = ["inspect_config_payload", "validate_config_path"]
