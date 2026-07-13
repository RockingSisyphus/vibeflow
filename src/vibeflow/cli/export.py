from __future__ import annotations

import tempfile
from pathlib import Path


def handle_export_graph(args, *, export_kind: str) -> int:
    from vibeflow.rendering.ascii_flowchart import export_ascii_flowchart
    from vibeflow.cli.reports import config_load_error_report, dedupe_findings, fail_report, graph_config_error_report
    from vibeflow.compiler import GraphCompiler, GraphCompileError
    from vibeflow.config.loader import ConfigLoadError, load_config_document
    from vibeflow.config.resources import load_config_resources
    from vibeflow.config.schema import collect_config_schema_findings
    from vibeflow.graph_config import GraphConfigError, parse_graph_config
    from vibeflow.health.types import HealthReport
    from vibeflow.rendering.mermaid import export_mermaid
    from vibeflow.rendering.mermaid.render import (
        DEFAULT_MERMAID_MAX_EDGES,
        DEFAULT_MERMAID_MAX_TEXT_SIZE,
        EXPANDED_MERMAID_MAX_EDGES,
        EXPANDED_MERMAID_MAX_TEXT_SIZE,
        MermaidRenderError,
        render_mermaid_svg,
    )
    from vibeflow.graph_config.planned_behavior import project_root_for_config
    from vibeflow.policy import default_effective_policy
    from vibeflow.plugin import load_plugins_from_config

    if getattr(args, "workspace", None):
        loaded = _workspace_graph_or_report(args, validate_health=export_kind == "architecture")
        if isinstance(loaded, HealthReport):
            print(loaded.to_json())
            return 1
        graph, compiled, registry, resources = loaded
    else:
        registry = None
        try:
            graph, compiled, resources = _load_legacy_graph(args, validate_health=export_kind == "architecture")
        except ConfigLoadError as exc:
            report = config_load_error_report(exc, object_type="config", object_id=str(args.config))
            print(report.to_json())
            return 1
        except GraphConfigError as exc:
            report = graph_config_error_report(exc, path=Path(args.config), effective_policy=default_effective_policy().to_dict())
            print(report.to_json())
            return 1
        except GraphCompileError as exc:
            report = fail_report(exc.rule_id, str(exc), "pipeline", "pipeline", "topology", effective_policy=default_effective_policy().to_dict())
            print(report.to_json())
            return 1
        except _SchemaExportError as exc:
            print(exc.report.to_json())
            return 1
        except _HealthExportError as exc:
            print(exc.report.to_json())
            return 1

    if export_kind == "architecture":
        return _export_architecture(args, graph=graph, compiled=compiled, registry=registry, resources=resources)
    if export_kind == "svg":
        return _export_svg(args, graph=graph, compiled=compiled, registry=registry, resources=resources)
    if export_kind == "ascii":
        text = export_ascii_flowchart(
            graph,
            compiled=compiled,
            expand_nodesets=bool(args.expand_nodesets),
            show_contract=not bool(args.hide_contract),
            show_semantics=not bool(args.hide_semantics),
        )
    else:
        text = export_mermaid(
            graph,
            compiled=compiled,
            expand_nodesets=bool(args.expand_nodesets),
            show_contract=not bool(args.hide_contract),
            show_semantics=not bool(args.hide_semantics),
            resources=resources,
            mermaid_layout=str(args.mermaid_layout),
        )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def _export_architecture(args, *, graph, compiled, registry, resources) -> int:
    from vibeflow.architecture_validation import architecture_finding_status, check_architecture_document
    from vibeflow.cli.reports import fail_report
    from vibeflow.compiler import GraphCompileError
    from vibeflow.health.types import HealthFinding, HealthReport
    from vibeflow.policy import default_effective_policy
    from vibeflow.rendering.architecture_document import build_architecture_document, render_architecture_payload

    try:
        payload = build_architecture_document(graph, compiled=compiled, registry=registry, resources=resources)
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


class _SchemaExportError(Exception):
    def __init__(self, report):
        super().__init__("schema export error")
        self.report = report


class _HealthExportError(Exception):
    def __init__(self, report):
        super().__init__("architecture health check failed")
        self.report = report


def _workspace_graph_or_report(args, *, validate_health: bool = False):
    from vibeflow.health.types import HealthReport
    from vibeflow.workspace import load_workspace_graph_for_export

    workspace = _load_workspace_for_export(Path(args.workspace))
    if isinstance(workspace, HealthReport):
        return workspace
    graph, compiled, registry, resources, error = load_workspace_graph_for_export(
        Path(args.config),
        workspace=workspace,
        validate_health=validate_health,
    )
    if error is not None:
        return error
    return graph, compiled, registry, resources


def _load_workspace_for_export(path: Path):
    from vibeflow.health.types import HealthFinding, HealthReport
    from vibeflow.workspace import WorkspaceConfigError, load_workspace_config

    try:
        return load_workspace_config(path)
    except WorkspaceConfigError as exc:
        return HealthReport(
            status="ERROR",
            errors=(
                HealthFinding(
                    rule_id=exc.rule_id,
                    severity="error",
                    object_type="workspace",
                    object_id=str(path),
                    source_location=dict(exc.source_location),
                    failure_layer=exc.failure_layer,
                    message=exc.message,
                    suggested_fix_type="fix_config",
                ),
            ),
        )


def _load_legacy_graph(args, *, validate_health: bool = False):
    from vibeflow.cli.reports import dedupe_findings
    from vibeflow.compiler import GraphCompiler
    from vibeflow.config.loader import load_config_document
    from vibeflow.config.resource_registries import discover_config_resource_registry_context
    from vibeflow.config.resources import load_config_resources
    from vibeflow.config.schema import collect_config_schema_findings
    from vibeflow.graph_config import parse_graph_config
    from vibeflow.health.types import HealthReport
    from vibeflow.graph_config.planned_behavior import project_root_for_config
    from vibeflow.policy import default_effective_policy
    from vibeflow.plugin import load_plugins_from_config

    config_path = Path(args.config)
    document = load_config_document(config_path)
    registry_context = discover_config_resource_registry_context(document.data, config_path=config_path)
    plugin_registry, plugin_findings = load_plugins_from_config(
        document.data,
        base_path=registry_context.base_path,
        plugin_resource_registry=registry_context.plugin_resource_registry,
    )
    resources, resource_findings = load_config_resources(
        document.data,
        base_path=registry_context.base_path,
        plugin_registry=plugin_registry,
        base_lib_registry=registry_context.base_lib_registry,
        plugin_resource_registry=registry_context.plugin_resource_registry,
        base_lib_paths=registry_context.base_lib_paths,
    )
    schema_findings = dedupe_findings((*collect_config_schema_findings(document.data), *registry_context.findings, *plugin_findings, *resource_findings))
    schema_errors = tuple(finding for finding in schema_findings if finding.severity == "error")
    if schema_errors:
        status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin", "base_lib"} for finding in schema_errors) else "FAIL"
        raise _SchemaExportError(
            HealthReport(
                status=status,
                errors=schema_errors,
                warnings=tuple(finding for finding in schema_findings if finding.severity == "warning"),
                effective_policy=default_effective_policy().to_dict(),
            )
        )
    project_root = project_root_for_config(config_path)
    graph = parse_graph_config(
        document.data,
        project_root=project_root,
        root_path=project_root,
        source_path=config_path,
    )
    if validate_health:
        from vibeflow.health import validate_graph_health

        health = validate_graph_health(
            graph,
            registry=None,
            plugin_registry=plugin_registry,
            global_config=resources.global_config,
            effective_policy=default_effective_policy(),
        )
        if health.status in {"FAIL", "ERROR"}:
            raise _HealthExportError(health)
    return graph, GraphCompiler().compile(graph), resources


def _export_svg(args, *, graph, compiled, registry, resources) -> int:
    from vibeflow.cli.reports import fail_report
    from vibeflow.rendering.mermaid import export_mermaid
    from vibeflow.rendering.mermaid.render import (
        DEFAULT_MERMAID_MAX_EDGES,
        DEFAULT_MERMAID_MAX_TEXT_SIZE,
        EXPANDED_MERMAID_MAX_EDGES,
        EXPANDED_MERMAID_MAX_TEXT_SIZE,
        MermaidRenderError,
        render_mermaid_svg,
    )
    from vibeflow.policy import default_effective_policy

    max_text_size = int(args.mermaid_max_text_size) if args.mermaid_max_text_size is not None else (EXPANDED_MERMAID_MAX_TEXT_SIZE if bool(args.expand_nodesets) else DEFAULT_MERMAID_MAX_TEXT_SIZE)
    max_edges = int(args.mermaid_max_edges) if args.mermaid_max_edges is not None else (EXPANDED_MERMAID_MAX_EDGES if bool(args.expand_nodesets) else DEFAULT_MERMAID_MAX_EDGES)
    try:
        if bool(args.expand_nodesets) or str(args.mermaid_layout) == "review-columns":
            _render_review_svg(args, graph=graph, compiled=compiled, registry=registry, resources=resources, max_text_size=max_text_size, max_edges=max_edges)
            return 0
        mermaid_text = export_mermaid(
            graph,
            compiled=compiled,
            expand_nodesets=bool(args.expand_nodesets),
            show_contract=not bool(args.hide_contract),
            show_semantics=not bool(args.hide_semantics),
            resources=resources,
            mermaid_layout=str(args.mermaid_layout),
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


def _render_review_svg(args, *, graph, compiled, registry, resources, max_text_size: int, max_edges: int) -> None:
    from vibeflow.rendering.mermaid.review_svg import render_review_columns_svg

    review_kwargs = {}
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
