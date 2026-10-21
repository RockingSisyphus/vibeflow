from __future__ import annotations
from vibeflow.tooling.project.diagnostics import workspace_or_report

import tempfile
from pathlib import Path


def handle_export_graph(args, *, export_kind: str) -> int:
    from vibeflow.tooling.application.python.presentation.ascii_flowchart import export_ascii_flowchart
    from vibeflow.core.findings import HealthReport
    from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
    loaded = _workspace_graph_or_report(args, validate_health=export_kind == "architecture")
    if isinstance(loaded, HealthReport):
        print(loaded.to_json())
        return 1
    graph, compiled, registry, resources, prepared = loaded

    if export_kind == "architecture":
        return _export_architecture(args, graph=graph, compiled=compiled, registry=registry, resources=resources, prepared=prepared)
    if export_kind == "svg":
        return _export_svg(args, graph=graph, compiled=compiled, registry=registry, resources=resources, prepared=prepared)
    if export_kind == "ascii":
        text = export_ascii_flowchart(
            graph,
            compiled=compiled,
            expand_nodesets=bool(args.expand_nodesets),
            show_contract=not bool(args.hide_contract),
            show_semantics=not bool(args.hide_semantics),
            registry=registry,
            prepared=prepared,
        )
    else:
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
    from vibeflow.tooling.application.python.presentation.architecture_validation import architecture_finding_status, check_architecture_document
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
        output_path.write_text(text, encoding="utf-8")
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



def _export_svg(args, *, graph, compiled, registry, resources, prepared=None) -> int:
    from vibeflow.tooling.application.python.reports import fail_report
    from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
    from vibeflow.tooling.presentation.mermaid import (
        DEFAULT_MERMAID_MAX_EDGES,
        DEFAULT_MERMAID_MAX_TEXT_SIZE,
        EXPANDED_MERMAID_MAX_EDGES,
        EXPANDED_MERMAID_MAX_TEXT_SIZE,
        MermaidRenderError,
        render_mermaid_svg,
    )
    from vibeflow.targets.python.project.policy import default_effective_policy

    max_text_size = int(args.mermaid_max_text_size) if args.mermaid_max_text_size is not None else (EXPANDED_MERMAID_MAX_TEXT_SIZE if bool(args.expand_nodesets) else DEFAULT_MERMAID_MAX_TEXT_SIZE)
    max_edges = int(args.mermaid_max_edges) if args.mermaid_max_edges is not None else (EXPANDED_MERMAID_MAX_EDGES if bool(args.expand_nodesets) else DEFAULT_MERMAID_MAX_EDGES)
    try:
        if bool(args.expand_nodesets) or str(args.mermaid_layout) == "review-columns":
            _render_review_svg(args, graph=graph, compiled=compiled, registry=registry, resources=resources, max_text_size=max_text_size, max_edges=max_edges, prepared=prepared)
            return 0
        mermaid_text = export_mermaid(
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
            render_mermaid_svg(mermaid_text, Path(args.output), theme=str(args.theme), background=str(args.background), max_text_size=max_text_size, max_edges=max_edges)
        else:
            with tempfile.TemporaryDirectory(prefix="vibeflow-svg-") as temp_dir:
                output = Path(temp_dir) / "graph.svg"
                render_mermaid_svg(mermaid_text, output, theme=str(args.theme), background=str(args.background), max_text_size=max_text_size, max_edges=max_edges)
                print(output.read_text(encoding="utf-8"), end="")
    except MermaidRenderError as exc:
        report = fail_report("MERMAID.RENDER.SVG", str(exc), "pipeline", "pipeline", "render", effective_policy=default_effective_policy().to_dict())
        print(report.to_json())
        return 1
    return 0


def _render_review_svg(args, *, graph, compiled, registry, resources, max_text_size: int, max_edges: int, prepared=None) -> None:
    from vibeflow.tooling.application.python.presentation.mermaid.review_svg import render_review_columns_svg

    review_kwargs = {"prepared":prepared}
    if args.review_fragment_max_width is not None:
        review_kwargs["review_fragment_max_width"] = float(args.review_fragment_max_width)
    if args.output:
        render_review_columns_svg(
            graph,
            compiled,
            Path(args.output),
            registry=registry,
            resources=resources,
            expand_nodesets=bool(args.expand_nodesets),
            show_contract=not bool(args.hide_contract),
            show_semantics=not bool(args.hide_semantics),
            theme=str(args.theme),
            background=str(args.background),
            max_text_size=max_text_size,
            max_edges=max_edges,
            **review_kwargs,
        )
        return
    with tempfile.TemporaryDirectory(prefix="vibeflow-svg-") as temp_dir:
        output = Path(temp_dir) / "graph.svg"
        render_review_columns_svg(
            graph,
            compiled,
            output,
            registry=registry,
            resources=resources,
            expand_nodesets=bool(args.expand_nodesets),
            show_contract=not bool(args.hide_contract),
            show_semantics=not bool(args.hide_semantics),
            theme=str(args.theme),
            background=str(args.background),
            max_text_size=max_text_size,
            max_edges=max_edges,
            **review_kwargs,
        )
        print(output.read_text(encoding="utf-8"), end="")
