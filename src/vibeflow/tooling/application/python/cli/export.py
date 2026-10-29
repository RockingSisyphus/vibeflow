from __future__ import annotations
from vibeflow.tooling.project.diagnostics import workspace_or_report

from pathlib import Path


def handle_export_graph(args, *, export_kind: str) -> int:
    from vibeflow.core.findings import HealthReport
    from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
    loaded = _workspace_graph_or_report(args, validate_health=export_kind == "architecture")
    if isinstance(loaded, HealthReport):
        print(loaded.to_json())
        return 1
    graph, compiled, registry, resources, prepared = loaded

    if export_kind == "architecture":
        return _export_architecture(args, graph=graph, compiled=compiled, registry=registry, resources=resources, prepared=prepared)
    text = export_mermaid(
        graph,
        compiled=compiled,
        registry=registry,
        expand_nodesets=bool(args.expand_nodesets),
        show_contract=not bool(args.hide_contract),
        show_semantics=not bool(args.hide_semantics),
        resources=resources,
        mermaid_layout=str(args.mermaid_layout),
        prepared=prepared,
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def _export_architecture(args, *, graph, compiled, registry, resources, prepared=None) -> int:
    from vibeflow.tooling.architecture.documents import architecture_finding_status, check_architecture_document
    from vibeflow.tooling.application.python.reports import fail_report
    from vibeflow.targets.python.project.compiler import GraphCompileError
    from vibeflow.core.findings import HealthFinding, HealthReport
    from vibeflow.targets.python.project.policy import default_effective_policy
    from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_document, render_architecture_payload

    try:
        payload = build_architecture_document(graph, compiled=compiled, registry=registry, resources=resources, prepared=prepared)
    except GraphCompileError as exc:
        report = fail_report(
            exc.rule_id,
            str(exc),
            "nodeset",
            "architecture",
            "topology",
            effective_policy=default_effective_policy().to_dict(),
        )
        print(report.to_json())
        return 1
    text = render_architecture_payload(payload)
    output_value = str(getattr(args, "output", "") or "").strip()
    if bool(getattr(args, "check", False)):
        if not output_value:
            finding = HealthFinding(
                rule_id="ARCHITECTURE.DOCUMENT.READ",
                severity="error",
                object_type="architecture_document",
                object_id="--output",
                failure_layer="source",
                message="export-architecture --check requires --output to name the registered architecture document",
                suggested_fix_type="regenerate_architecture",
                details={"required_argument": "--output"},
            )
            print(HealthReport(status="ERROR", errors=(finding,)).to_json())
            return 1
        finding = check_architecture_document(
            Path(output_value),
            expected_payload=payload,
            expected_text=text,
            workflow_path=Path(args.config),
            workspace_path=Path(args.workspace) if getattr(args, "workspace", None) else None,
        )
        if finding is None:
            return 0
        print(HealthReport(status=architecture_finding_status(finding), errors=(finding,)).to_json())
        return 1
    if output_value:
        output_path = Path(output_value)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        from vibeflow.tooling.file_io import atomic_write
        atomic_write(output_path, text)
    else:
        print(text, end="")
    return 0


def _workspace_graph_or_report(args, *, validate_health: bool = False):
    from vibeflow.core.findings import HealthReport
    from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export

    if getattr(args, "workspace", None):
        workspace = workspace_or_report(Path(args.workspace))
    else:
        from vibeflow.tooling.project.workspace_loader import load_project_workspace
        workspace = workspace_or_report(Path(args.config), registered_source=True)
    if isinstance(workspace, HealthReport):
        return workspace
    graph, compiled, registry, resources, error, _, prepared = load_workspace_graph_for_export(
        Path(args.config),
        workspace=workspace,
        validate_health=validate_health,
        _include_presentation=True,
    )
    if error is not None:
        return error
    return graph, compiled, registry, resources, prepared
