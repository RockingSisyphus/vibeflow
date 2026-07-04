from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vibeflow")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate topology config structure and compile graph")
    validate.add_argument("--config", required=True)
    validate.add_argument("--policy", required=False, help="explicit kernel_policy.jsonc/governance.jsonc path")
    validate.add_argument("--json", action="store_true", help="emit full HealthReport JSON")

    inspect_node = sub.add_parser("inspect-node", help="inspect a node class and static purity findings")
    inspect_node.add_argument("--type", required=True, dest="node_type")
    inspect_node.add_argument("--module", required=False, help="Python file containing the node class")
    inspect_node.add_argument("--class", required=False, dest="class_name", help="Class name to inspect inside --module")
    inspect_node.add_argument("--policy", required=False, help="explicit kernel_policy.jsonc/governance.jsonc path")

    inspect_config = sub.add_parser("inspect-config", help="inspect parsed topology config and compiled edges")
    inspect_config.add_argument("--config", required=True)
    inspect_config.add_argument("--policy", required=False, help="explicit kernel_policy.jsonc/governance.jsonc path")

    mermaid = sub.add_parser("export-mermaid", help="export topology config to Mermaid flowchart")
    mermaid.add_argument("--config", required=True)
    mermaid.add_argument("--output", required=False)
    mermaid.add_argument("--expand-nodesets", dest="expand_nodesets", action="store_true")
    mermaid.add_argument("--collapse-nodesets", dest="expand_nodesets", action="store_false")
    mermaid.add_argument("--hide-contract", action="store_true")
    mermaid.add_argument("--hide-semantics", action="store_true")
    mermaid.add_argument(
        "--mermaid-layout",
        choices=("default", "review-columns"),
        default="default",
        help="Mermaid layout strategy: default inline layout or review-columns audit layout",
    )
    mermaid.set_defaults(expand_nodesets=False)

    ascii_chart = sub.add_parser("export-ascii", help="export topology config to ASCII flowchart")
    ascii_chart.add_argument("--config", required=True)
    ascii_chart.add_argument("--output", required=False)
    ascii_chart.add_argument("--expand-nodesets", dest="expand_nodesets", action="store_true")
    ascii_chart.add_argument("--collapse-nodesets", dest="expand_nodesets", action="store_false")
    ascii_chart.add_argument("--hide-contract", action="store_true")
    ascii_chart.add_argument("--hide-semantics", action="store_true")
    ascii_chart.set_defaults(expand_nodesets=False)

    svg = sub.add_parser("export-svg", help="render topology config Mermaid flowchart to SVG")
    svg.add_argument("--config", required=True)
    svg.add_argument("--output", required=False)
    svg.add_argument("--expand-nodesets", dest="expand_nodesets", action="store_true")
    svg.add_argument("--collapse-nodesets", dest="expand_nodesets", action="store_false")
    svg.add_argument("--hide-contract", action="store_true")
    svg.add_argument("--hide-semantics", action="store_true")
    svg.add_argument("--theme", default="default")
    svg.add_argument("--background", default="transparent")
    svg.add_argument(
        "--mermaid-layout",
        choices=("default", "review-columns"),
        default="default",
        help="Mermaid layout strategy for collapsed SVG rendering; expanded SVG always uses review-columns",
    )
    svg.add_argument(
        "--mermaid-max-text-size",
        type=int,
        default=None,
        help="override Mermaid maxTextSize for SVG rendering",
    )
    svg.add_argument(
        "--mermaid-max-edges",
        type=int,
        default=None,
        help="override Mermaid maxEdges for SVG rendering",
    )
    svg.set_defaults(expand_nodesets=False)

    run = sub.add_parser("run", help="run topology config after mandatory health checks")
    run.add_argument("--config", required=True)
    run.add_argument("--policy", required=False, help="explicit kernel_policy.jsonc/governance.jsonc path")
    run.add_argument("--input", required=False, help="optional JSON object file for initial context")
    run.add_argument("--run-root", required=False, help="directory where run artifacts are created")
    run.add_argument("--run-id", required=False, help="optional deterministic run id for tests or controlled runs")
    _add_runtime_options(run)

    quality = sub.add_parser("quality-check", help="run standalone Python code quality checks")
    quality.add_argument("--path", required=False, default=".", help="project directory or Python file to inspect")
    quality.add_argument("--json", action="store_true", help="emit full quality report JSON")
    quality.add_argument("--check-side-effects", action="store_true", help="also warn about side-effect capable imports and calls")
    quality.add_argument("--max-lines", type=int, default=500, help="maximum Python file lines before error")
    quality.add_argument("--warn-lines", type=int, default=450, help="Python file lines before warning")
    quality.add_argument("--max-bytes", type=int, default=60000, help="maximum Python file bytes before error")
    quality.add_argument("--max-file-branches", type=int, default=150, help="maximum Python file branch count before warning")
    quality.add_argument("--max-directory-fanout", type=int, default=25, help="maximum directory fanout before warning")
    quality.add_argument("--max-directory-fanin", type=int, default=25, help="maximum directory fanin before warning")
    quality.add_argument("--max-prefix-cluster-files", type=int, default=12, help="maximum same-prefix files before package warning")
    quality.add_argument("--max-public-entry-bypass-imports", type=int, default=3, help="maximum direct internal imports from one cluster before warning")
    quality.add_argument("--max-dependency-distance", type=int, default=3, help="maximum module path distance before warning")
    quality.add_argument("--max-scattered-dependency-directories", type=int, default=6, help="maximum far dependency directories before warning")
    quality.add_argument("--max-function-lines", type=int, default=80, help="maximum function lines before warning")
    quality.add_argument("--max-function-branches", type=int, default=12, help="maximum function branch count before warning")
    quality.add_argument("--max-function-nesting", type=int, default=4, help="maximum function nesting depth before warning")
    quality.add_argument("--max-function-params", type=int, default=6, help="maximum function parameter count before warning")
    quality.add_argument("--warn-dependency-depth", type=int, default=6, help="dependency chain length before warning")
    quality.add_argument("--max-dependency-depth", type=int, default=10, help="dependency chain length before error")
    quality.add_argument("--include-references", action="store_true", help="also scan references/ directories")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "validate": _handle_validate,
        "inspect-node": _handle_inspect_node,
        "inspect-config": _handle_inspect_config,
        "export-ascii": _handle_export_ascii,
        "export-svg": _handle_export_svg,
        "export-mermaid": _handle_export_mermaid,
        "run": _handle_run,
        "quality-check": _handle_quality_check,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.error(f"unknown command: {args.command}")
        return 2
    return handler(args)


def _handle_validate(args: argparse.Namespace) -> int:
    from .cli_config import validate_config_path
    from .cli_reports import format_finding_text

    report = validate_config_path(Path(args.config), policy_path=Path(args.policy) if args.policy else None)
    if args.json:
        print(report.to_json())
    else:
        print(report.status)
        for finding in (*report.errors, *report.warnings):
            print(format_finding_text(finding))
    return 0 if report.status in {"PASS", "CONCERNS"} else 1


def _handle_inspect_node(args: argparse.Namespace) -> int:
    from .cli_node import inspect_node_payload

    payload, status = inspect_node_payload(
        node_type=args.node_type,
        module_path=Path(args.module) if args.module else None,
        class_name=args.class_name,
        policy_path=Path(args.policy) if args.policy else None,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return status


def _handle_inspect_config(args: argparse.Namespace) -> int:
    from .cli_config import inspect_config_payload

    payload, status = inspect_config_payload(Path(args.config), policy_path=Path(args.policy) if args.policy else None)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return status


def _handle_export_mermaid(args: argparse.Namespace) -> int:
    return _handle_export_graph(args, export_kind="mermaid")


def _handle_export_ascii(args: argparse.Namespace) -> int:
    return _handle_export_graph(args, export_kind="ascii")


def _handle_export_svg(args: argparse.Namespace) -> int:
    return _handle_export_graph(args, export_kind="svg")


def _handle_export_graph(args: argparse.Namespace, *, export_kind: str) -> int:
    from .cli_reports import config_load_error_report, dedupe_findings, fail_report, graph_config_error_report
    from .compiler import GraphCompiler, GraphCompileError
    from .config_loader import ConfigLoadError, load_config_document
    from .config_resources import load_config_resources
    from .config_schema import collect_config_schema_findings
    from .graph_config import GraphConfigError, parse_graph_config
    from .health_types import HealthReport
    from .ascii_flowchart import export_ascii_flowchart
    from .mermaid import export_mermaid
    from .mermaid_render import (
        DEFAULT_MERMAID_MAX_EDGES,
        DEFAULT_MERMAID_MAX_TEXT_SIZE,
        EXPANDED_MERMAID_MAX_EDGES,
        EXPANDED_MERMAID_MAX_TEXT_SIZE,
        MermaidRenderError,
        render_mermaid_svg,
    )
    from .planned_behavior import project_root_for_config
    from .policy import default_effective_policy
    from .plugin import load_plugins_from_config

    try:
        config_path = Path(args.config)
        document = load_config_document(config_path)
        plugin_registry, plugin_findings = load_plugins_from_config(document.data, base_path=config_path.parent)
        resources, resource_findings = load_config_resources(document.data, base_path=config_path.parent, plugin_registry=plugin_registry)
        schema_findings = dedupe_findings((*collect_config_schema_findings(document.data), *plugin_findings, *resource_findings))
        if schema_findings:
            status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin", "base_lib"} for finding in schema_findings) else "FAIL"
            report = HealthReport(
                status=status,
                errors=tuple(finding for finding in schema_findings if finding.severity == "error"),
                warnings=tuple(finding for finding in schema_findings if finding.severity == "warning"),
                effective_policy=default_effective_policy().to_dict(),
            )
            print(report.to_json())
            return 1
        graph = parse_graph_config(document.data, project_root=project_root_for_config(config_path))
        compiled = GraphCompiler().compile(graph)
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
    if export_kind == "svg":
        max_text_size = (
            int(args.mermaid_max_text_size)
            if args.mermaid_max_text_size is not None
            else (EXPANDED_MERMAID_MAX_TEXT_SIZE if bool(args.expand_nodesets) else DEFAULT_MERMAID_MAX_TEXT_SIZE)
        )
        max_edges = (
            int(args.mermaid_max_edges)
            if args.mermaid_max_edges is not None
            else (EXPANDED_MERMAID_MAX_EDGES if bool(args.expand_nodesets) else DEFAULT_MERMAID_MAX_EDGES)
        )
        try:
            use_review_columns_svg = bool(args.expand_nodesets) or str(args.mermaid_layout) == "review-columns"
            if use_review_columns_svg:
                from .mermaid_review_svg import render_review_columns_svg

                if args.output:
                    render_review_columns_svg(
                        graph,
                        compiled,
                        Path(args.output),
                        registry=None,
                        resources=resources,
                        expand_nodesets=bool(args.expand_nodesets),
                        show_contract=not bool(args.hide_contract),
                        show_semantics=not bool(args.hide_semantics),
                        theme=str(args.theme),
                        background=str(args.background),
                        max_text_size=max_text_size,
                        max_edges=max_edges,
                    )
                else:
                    with tempfile.TemporaryDirectory(prefix="vibeflow-svg-") as temp_dir:
                        output = Path(temp_dir) / "graph.svg"
                        render_review_columns_svg(
                            graph,
                            compiled,
                            output,
                            registry=None,
                            resources=resources,
                            expand_nodesets=bool(args.expand_nodesets),
                            show_contract=not bool(args.hide_contract),
                            show_semantics=not bool(args.hide_semantics),
                            theme=str(args.theme),
                            background=str(args.background),
                            max_text_size=max_text_size,
                            max_edges=max_edges,
                        )
                        print(output.read_text(encoding="utf-8"), end="")
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
                render_mermaid_svg(
                    mermaid_text,
                    Path(args.output),
                    theme=str(args.theme),
                    background=str(args.background),
                    max_text_size=max_text_size,
                    max_edges=max_edges,
                )
            else:
                with tempfile.TemporaryDirectory(prefix="vibeflow-svg-") as temp_dir:
                    output = Path(temp_dir) / "graph.svg"
                    render_mermaid_svg(
                        mermaid_text,
                        output,
                        theme=str(args.theme),
                        background=str(args.background),
                        max_text_size=max_text_size,
                        max_edges=max_edges,
                    )
                    print(output.read_text(encoding="utf-8"), end="")
        except MermaidRenderError as exc:
            report = fail_report("MERMAID.RENDER.SVG", str(exc), "pipeline", "pipeline", "render", effective_policy=default_effective_policy().to_dict())
            print(report.to_json())
            return 1
        return 0
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


def _handle_run(args: argparse.Namespace) -> int:
    from .registry import GLOBAL_NODE_REGISTRY
    from .runner import CheckedRunError, run_checked

    try:
        initial = _load_initial_input(Path(args.input)) if args.input else {}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    try:
        result = run_checked(
            Path(args.config),
            registry=GLOBAL_NODE_REGISTRY,
            initial=initial,
            policy_path=Path(args.policy) if args.policy else None,
            run_root=Path(args.run_root) if args.run_root else None,
            run_id=args.run_id,
            runtime_options=_runtime_options_from_args(args),
        )
    except CheckedRunError as exc:
        payload = {"status": exc.result.health.status, "run_id": exc.result.run_id, "run_dir": str(exc.result.run_dir), "error": str(exc), "health": exc.result.health.to_dict()}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    payload = {"status": result.health.status, "run_id": result.run_id, "run_dir": str(result.run_dir)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _handle_quality_check(args: argparse.Namespace) -> int:
    from .devtools.code_quality import DEFAULT_EXCLUDED_DIRS, QualityThresholds, format_quality_summary, scan_code_quality

    root = Path(args.path)
    thresholds = QualityThresholds(
        max_file_lines=args.max_lines,
        warn_file_lines=args.warn_lines,
        max_file_bytes=args.max_bytes,
        max_file_branches=args.max_file_branches,
        max_directory_fanout=args.max_directory_fanout,
        max_directory_fanin=args.max_directory_fanin,
        max_prefix_cluster_files=args.max_prefix_cluster_files,
        max_public_entry_bypass_imports=args.max_public_entry_bypass_imports,
        max_dependency_distance=args.max_dependency_distance,
        max_scattered_dependency_directories=args.max_scattered_dependency_directories,
        max_function_lines=args.max_function_lines,
        max_function_branches=args.max_function_branches,
        max_function_nesting=args.max_function_nesting,
        max_function_params=args.max_function_params,
        warn_dependency_chain=args.warn_dependency_depth,
        max_dependency_chain=args.max_dependency_depth,
    )
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    if args.include_references:
        excluded_dirs.discard("references")
    report = scan_code_quality(
        root,
        thresholds=thresholds,
        excluded_dirs=excluded_dirs,
        check_side_effects=bool(args.check_side_effects),
    )
    print(report.to_json() if args.json else format_quality_summary(report))
    return 0 if report.status in {"PASS", "CONCERNS"} else 1


def _load_initial_input(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("--input JSON root must be an object")
    return {str(key): value for key, value in payload.items()}


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runtime-profile", choices=("debug", "train"), default=None, help="runtime option preset")
    parser.add_argument("--trace", choices=("full", "boundary", "off"), default=None, help="runtime trace policy")
    parser.add_argument("--execution", choices=("plan", "block", "compiled"), default=None, help="runtime execution mode")
    parser.add_argument("--run-hooks", action=argparse.BooleanOptionalAction, default=None, help="enable or disable run-level runtime plugin hooks")
    parser.add_argument("--node-hooks", action=argparse.BooleanOptionalAction, default=None, help="enable or disable node-level runtime plugin hooks")
    parser.add_argument("--nodeset-hooks", action=argparse.BooleanOptionalAction, default=None, help="enable or disable nodeset-level runtime plugin hooks")
    parser.add_argument("--block-hooks", action=argparse.BooleanOptionalAction, default=None, help="enable or disable block-level runtime plugin hooks")
    parser.add_argument("--async-flush-timeout", type=float, default=None, help="seconds to wait for detached async tasks at run end")
    parser.add_argument("--allow-planned-stub", action="store_true", help="development only: execute planned python_stub nodes")


def _runtime_options_from_args(args: argparse.Namespace):
    from .runtime_options import RuntimeOptions

    values: dict[str, object] = {}
    if args.runtime_profile == "train":
        values.update(
            {
                "trace": "boundary",
                "run_hooks": True,
                "node_hooks": False,
                "nodeset_hooks": False,
                "block_hooks": True,
                "execution": "compiled",
                "async_flush_timeout": 30.0,
            }
        )
    elif args.runtime_profile == "debug":
        values.update({"trace": "full", "run_hooks": True, "node_hooks": True, "nodeset_hooks": True, "block_hooks": True, "execution": "plan"})
    if args.trace is not None:
        values["trace"] = args.trace
    if args.execution is not None:
        values["execution"] = args.execution
    if args.run_hooks is not None:
        values["run_hooks"] = args.run_hooks
    if args.node_hooks is not None:
        values["node_hooks"] = args.node_hooks
    if args.nodeset_hooks is not None:
        values["nodeset_hooks"] = args.nodeset_hooks
    if args.block_hooks is not None:
        values["block_hooks"] = args.block_hooks
    if args.async_flush_timeout is not None:
        values["async_flush_timeout"] = args.async_flush_timeout
    if args.allow_planned_stub:
        values["allow_planned_stub"] = True
    return RuntimeOptions(**values)
