from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Sequence

from vibeflow.run_directory import parse_run_id_argument


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vibeflow")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate topology config structure and compile graph")
    validate.add_argument("--config", required=True)
    validate.add_argument("--workspace", required=False, help="workspace vibeflow_config.jsonc path")
    validate.add_argument("--policy", required=False, help="explicit kernel_policy.jsonc/governance.jsonc path")
    validate.add_argument("--json", action="store_true", help="emit full HealthReport JSON")

    inspect_node = sub.add_parser("inspect-node", help="inspect a node class and static purity findings")
    inspect_node.add_argument("--type", required=True, dest="node_type")
    inspect_node.add_argument("--module", required=False, help="Python file containing the node class")
    inspect_node.add_argument("--class", required=False, dest="class_name", help="Class name to inspect inside --module")
    inspect_node.add_argument("--policy", required=False, help="explicit kernel_policy.jsonc/governance.jsonc path")

    inspect_config = sub.add_parser("inspect-config", help="inspect parsed topology config and compiled edges")
    inspect_config.add_argument("--config", required=True)
    inspect_config.add_argument("--workspace", required=False, help="workspace vibeflow_config.jsonc path")
    inspect_config.add_argument("--policy", required=False, help="explicit kernel_policy.jsonc/governance.jsonc path")

    mermaid = sub.add_parser("export-mermaid", help="export topology config to Mermaid flowchart")
    mermaid.add_argument("--config", required=True)
    mermaid.add_argument("--workspace", required=False, help="workspace vibeflow_config.jsonc path")
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

    architecture = sub.add_parser("export-architecture", help="export a generated non-executable architecture review document")
    architecture.add_argument("--config", required=True)
    architecture.add_argument("--workspace", required=False, help="workspace vibeflow_config.jsonc path")
    architecture.add_argument("--output", required=False)
    architecture.add_argument("--check", action="store_true", help="check that --output is canonical and current without writing it")

    ascii_chart = sub.add_parser("export-ascii", help="export topology config to ASCII flowchart")
    ascii_chart.add_argument("--config", required=True)
    ascii_chart.add_argument("--workspace", required=False, help="workspace vibeflow_config.jsonc path")
    ascii_chart.add_argument("--output", required=False)
    ascii_chart.add_argument("--expand-nodesets", dest="expand_nodesets", action="store_true")
    ascii_chart.add_argument("--collapse-nodesets", dest="expand_nodesets", action="store_false")
    ascii_chart.add_argument("--hide-contract", action="store_true")
    ascii_chart.add_argument("--hide-semantics", action="store_true")
    ascii_chart.set_defaults(expand_nodesets=False)

    svg = sub.add_parser("export-svg", help="render topology config Mermaid flowchart to SVG")
    svg.add_argument("--config", required=True)
    svg.add_argument("--workspace", required=False, help="workspace vibeflow_config.jsonc path")
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
    svg.add_argument(
        "--review-fragment-max-width",
        type=float,
        default=None,
        help="override review-columns SVG fragment display width cap",
    )
    svg.set_defaults(expand_nodesets=False)

    run = sub.add_parser("run", help="run topology config after mandatory health checks")
    run.add_argument("--config", required=True)
    run.add_argument("--workspace", required=False, help="workspace vibeflow_config.jsonc path")
    run.add_argument("--policy", required=False, help="explicit kernel_policy.jsonc/governance.jsonc path")
    run.add_argument("--input", required=False, help="optional JSON object file for initial context")
    run.add_argument("--run-root", required=False, help="directory where run artifacts are created")
    run.add_argument(
        "--run-id",
        required=False,
        type=parse_run_id_argument,
        help="optional deterministic run id for tests or controlled runs",
    )
    _add_runtime_options(run)

    from vibeflow.cli.delegate_cli import add_delegate_cli_parser

    add_delegate_cli_parser(sub, _add_runtime_options)

    from vibeflow.cli.review import add_review_parser

    add_review_parser(sub)

    from vibeflow.cli.quality import add_quality_parser

    add_quality_parser(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] == "delegate-cli":
        if "--" in raw_args:
            separator = raw_args.index("--")
            kernel_args = raw_args[:separator]
            delegated_args = raw_args[separator + 1 :]
        else:
            kernel_args = raw_args
            delegated_args = []
        args, unknown = parser.parse_known_args(kernel_args)
        args.delegate_argv = [*unknown, *delegated_args]
        if args.policy is not None:
            parser.error("delegate-cli does not accept --policy; configure workspace policy in vibeflow_config.jsonc")
    else:
        args = parser.parse_args(raw_args)
    handlers = {
        "validate": _handle_validate,
        "inspect-node": _handle_inspect_node,
        "inspect-config": _handle_inspect_config,
        "export-ascii": _handle_export_ascii,
        "export-architecture": _handle_export_architecture,
        "export-svg": _handle_export_svg,
        "export-mermaid": _handle_export_mermaid,
        "review": _handle_review,
        "run": _handle_run,
        "delegate-cli": _handle_delegate_cli,
        "quality-check": _handle_quality_check,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.error(f"unknown command: {args.command}")
        return 2
    return handler(args)


def _handle_validate(args: argparse.Namespace) -> int:
    from vibeflow.cli.config import validate_config_path
    from vibeflow.cli.reports import format_finding_text

    if getattr(args, "workspace", None):
        if args.policy:
            return _workspace_policy_arg_error()
        from vibeflow.health.types import HealthReport
        from vibeflow.workspace import validate_workspace_config_path

        workspace = _load_workspace_for_cli(Path(args.workspace))
        if isinstance(workspace, HealthReport):
            report = workspace
        else:
            report = validate_workspace_config_path(Path(args.config), workspace=workspace)
    else:
        report = validate_config_path(Path(args.config), policy_path=Path(args.policy) if args.policy else None)
    if args.json:
        print(report.to_json())
    else:
        print(report.status)
        for finding in (*report.errors, *report.warnings):
            print(format_finding_text(finding))
    return 0 if report.status in {"PASS", "CONCERNS"} else 1


def _handle_inspect_node(args: argparse.Namespace) -> int:
    from vibeflow.cli.node import inspect_node_payload

    payload, status = inspect_node_payload(
        node_type=args.node_type,
        module_path=Path(args.module) if args.module else None,
        class_name=args.class_name,
        policy_path=Path(args.policy) if args.policy else None,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return status


def _handle_inspect_config(args: argparse.Namespace) -> int:
    from vibeflow.cli.config import inspect_config_payload

    if getattr(args, "workspace", None):
        if args.policy:
            return _workspace_policy_arg_error()
        payload, status = _inspect_workspace_config_payload(Path(args.config), Path(args.workspace))
    else:
        payload, status = inspect_config_payload(Path(args.config), policy_path=Path(args.policy) if args.policy else None)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return status


def _handle_export_mermaid(args: argparse.Namespace) -> int:
    return _handle_export_graph(args, export_kind="mermaid")


def _handle_export_ascii(args: argparse.Namespace) -> int:
    return _handle_export_graph(args, export_kind="ascii")


def _handle_export_architecture(args: argparse.Namespace) -> int:
    return _handle_export_graph(args, export_kind="architecture")


def _handle_export_svg(args: argparse.Namespace) -> int:
    return _handle_export_graph(args, export_kind="svg")


def _handle_review(args: argparse.Namespace) -> int:
    from vibeflow.cli.review import handle_review

    return handle_review(args)


def _handle_export_graph(args: argparse.Namespace, *, export_kind: str) -> int:
    from vibeflow.cli.export import handle_export_graph

    return handle_export_graph(args, export_kind=export_kind)


def _handle_run(args: argparse.Namespace) -> int:
    from vibeflow.registry import GLOBAL_NODE_REGISTRY
    from vibeflow.runner import CheckedRunError, run_checked

    try:
        initial = _load_initial_input(Path(args.input)) if args.input else {}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    try:
        if getattr(args, "workspace", None):
            if args.policy:
                return _workspace_policy_arg_error()
            from vibeflow.health.types import HealthReport
            from vibeflow.workspace import run_workspace_checked

            workspace = _load_workspace_for_cli(Path(args.workspace))
            if isinstance(workspace, HealthReport):
                print(json.dumps({"status": workspace.status, "error": "workspace load failed", "health": workspace.to_dict()}, ensure_ascii=False, indent=2))
                return 1

            result = run_workspace_checked(
                Path(args.config),
                workspace=workspace,
                initial=initial,
                run_root=Path(args.run_root) if args.run_root else None,
                run_id=args.run_id,
                runtime_options=_runtime_options_from_args(args),
            )
        else:
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


def _handle_delegate_cli(args: argparse.Namespace) -> int:
    from vibeflow.cli.delegate_cli import handle_delegate_cli

    return handle_delegate_cli(args)


def _handle_quality_check(args: argparse.Namespace) -> int:
    from vibeflow.cli.quality import handle_quality_check

    return handle_quality_check(args)


def _inspect_workspace_config_payload(config_path: Path, workspace_path: Path) -> tuple[dict[str, object], int]:
    from vibeflow.compiler import GraphCompiler
    from vibeflow.config.loader import load_workspace_config_document
    from vibeflow.data_contract import providers_to_dicts, requirements_to_dicts
    from vibeflow.graph_config import parse_graph_config
    from vibeflow.health.types import HealthReport
    from vibeflow.workspace import load_workspace_graph_for_export, validate_workspace_config_path

    workspace = _load_workspace_for_cli(workspace_path)
    if isinstance(workspace, HealthReport):
        return {"health": workspace.to_dict()}, 1
    report = validate_workspace_config_path(config_path, workspace=workspace)
    payload: dict[str, object] = {"health": report.to_dict(), "workspace": report.info.get("workspace", {})}
    if report.status not in {"PASS", "CONCERNS"}:
        return payload, 1
    document = load_workspace_config_document(config_path, workspace=workspace)
    root = workspace.root_for_path(config_path)
    graph = parse_graph_config(
        document.data,
        project_root=root.path if root is not None else config_path.parent,
        root_id=root.id if root is not None else "",
        root_path=root.path if root is not None else None,
        source_path=config_path,
    )
    _, compiled, registry, resources, error = load_workspace_graph_for_export(config_path, workspace=workspace)
    if error is not None:
        return {"health": error.to_dict(), "workspace": error.info.get("workspace", {})}, 1
    if compiled is None:
        compiled = GraphCompiler().compile(graph, registry=registry)
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
                "root_id": graph.root_id,
                "source_path": graph.source_path,
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
                "root_id": nodeset.root_id,
                "root_path": nodeset.root_path,
                "source_path": nodeset.source_path,
            }
            for nodeset in graph.nodesets.values()
        ],
        "nodeset_imports": [dict(item) for item in document.nodeset_imports],
        "resources": resources.to_dict(),
        "max_steps": graph.max_steps,
        "effective_edges": [{"from": edge.source, "to": edge.target, "when": edge.when} for edge in compiled.effective_edges],
    }
    return payload, 0


def _load_workspace_for_cli(path: Path):
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


def _workspace_policy_arg_error() -> int:
    print(
        json.dumps(
            {
                "status": "ERROR",
                "error": "--policy is not supported with --workspace; move workspace policy to vibeflow_config.jsonc",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1


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
    parser.add_argument(
        "--async-flush-timeout",
        type=_non_negative_finite_float,
        default=None,
        help="non-negative finite seconds to wait for detached async tasks at run end",
    )
    parser.add_argument("--allow-planned-stub", action="store_true", help="development only: execute planned python_stub nodes")


def _non_negative_finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a non-negative finite number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative finite number")
    return parsed


def _runtime_options_from_args(args: argparse.Namespace):
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
    return values
