from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="topology-kernel")
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
    mermaid.add_argument("--hide-boundary", action="store_true")
    mermaid.set_defaults(expand_nodesets=False)

    run = sub.add_parser("run", help="run topology config after mandatory health checks")
    run.add_argument("--config", required=True)
    run.add_argument("--policy", required=False, help="explicit kernel_policy.jsonc/governance.jsonc path")
    run.add_argument("--input", required=False, help="optional JSON object file for initial context")
    run.add_argument("--run-root", required=False, help="directory where run artifacts are created")
    run.add_argument("--run-id", required=False, help="optional deterministic run id for tests or controlled runs")

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
    from .cli_reports import config_load_error_report, fail_report, graph_config_error_report
    from .compiler import GraphCompiler, GraphCompileError
    from .config_loader import ConfigLoadError, load_config_document
    from .graph_config import GraphConfigError, parse_graph_config
    from .mermaid import export_mermaid
    from .policy import default_effective_policy

    try:
        document = load_config_document(Path(args.config))
        graph = parse_graph_config(document.data)
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
        report = fail_report("GRAPH.COMPILE", str(exc), "pipeline", "pipeline", "topology", effective_policy=default_effective_policy().to_dict())
        print(report.to_json())
        return 1
    text = export_mermaid(
        graph,
        compiled=compiled,
        expand_nodesets=bool(args.expand_nodesets),
        show_contract=not bool(args.hide_contract),
        show_semantics=not bool(args.hide_semantics),
        show_boundary=not bool(args.hide_boundary),
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def _handle_run(args: argparse.Namespace) -> int:
    from .boundary import GLOBAL_BOUNDARY_REGISTRY
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
            boundary_registry=GLOBAL_BOUNDARY_REGISTRY,
            initial=initial,
            policy_path=Path(args.policy) if args.policy else None,
            run_root=Path(args.run_root) if args.run_root else None,
            run_id=args.run_id,
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
