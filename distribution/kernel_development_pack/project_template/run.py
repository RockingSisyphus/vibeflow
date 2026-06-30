from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "kernel"))
sys.path.insert(0, str(ROOT / "project"))

from topology_kernel import (  # noqa: E402
    CheckedRunError,
    GraphCompiler,
    HealthReport,
    export_ascii_flowchart,
    export_mermaid,
    load_config_document,
    load_plugins_from_config,
    parse_graph_config,
    resolve_effective_policy,
    run_checked,
    validate_graph_health,
)

from topology_kernel.config_schema import collect_config_schema_findings  # noqa: E402

from registry import build_boundary_registry, build_node_registry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="project-runner")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_config_command(sub, "validate")
    _add_config_command(sub, "inspect-config")
    run_cmd = _add_config_command(sub, "run")
    run_cmd.add_argument("--run-root", default="runs")
    run_cmd.add_argument("--input", required=False)
    mermaid = _add_config_command(sub, "mermaid")
    mermaid.add_argument("--output", required=False)
    mermaid.add_argument("--expand-nodesets", action="store_true")
    ascii_chart = _add_config_command(sub, "ascii")
    ascii_chart.add_argument("--output", required=False)
    ascii_chart.add_argument("--expand-nodesets", action="store_true")
    inspect_node = sub.add_parser("inspect-node")
    inspect_node.add_argument("--type", required=True, dest="node_type")
    inspect_node.add_argument("--module", required=True)
    inspect_node.add_argument("--class", required=True, dest="class_name")
    inspect_node.add_argument("--policy", required=False)
    quality = sub.add_parser("quality")
    quality.add_argument("--path", default="project")
    args = parser.parse_args()
    return _dispatch(args)


def _add_config_command(sub, name: str):
    command = sub.add_parser(name)
    command.add_argument("--config", required=True)
    command.add_argument("--policy", required=False)
    return command


def _dispatch(args) -> int:
    handlers = {
        "validate": _validate,
        "inspect-config": _inspect_config,
        "run": _run,
        "ascii": _ascii,
        "mermaid": _mermaid,
        "inspect-node": _inspect_node,
        "quality": _quality,
    }
    return handlers[args.command](args)


def _validate(args) -> int:
    graph, plugin_registry, effective_policy, schema_report = _preflight(args.config, args.policy)
    if schema_report is not None:
        print(schema_report.to_json())
        return 1
    report = validate_graph_health(
        graph,
        registry=build_node_registry(),
        boundary_registry=build_boundary_registry(),
        plugin_registry=plugin_registry,
        purity_policy=effective_policy.to_purity_policy(),
    )
    report = replace(report, effective_policy=effective_policy.to_dict())
    print(report.to_json())
    return 0 if report.status in {"PASS", "CONCERNS"} else 1


def _inspect_config(args) -> int:
    graph = _load_graph(args.config)
    payload = {
        "nodes": [node.__dict__ for node in graph.nodes],
        "edges": [edge.__dict__ for edge in graph.edges],
        "loops": [loop.__dict__ for loop in graph.loops],
        "nodesets": sorted(graph.nodesets),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run(args) -> int:
    initial = _load_input(args.input) if args.input else {}
    try:
        result = run_checked(
            args.config,
            registry=build_node_registry(),
            boundary_registry=build_boundary_registry(),
            initial=initial,
            policy_path=args.policy,
            run_root=args.run_root,
        )
    except CheckedRunError as exc:
        print(exc.result.health.to_json())
        return 1
    print(json.dumps({"status": result.health.status, "run_dir": str(result.run_dir)}, ensure_ascii=False))
    return 0


def _mermaid(args) -> int:
    return _export_graph(args, exporter=export_mermaid)


def _ascii(args) -> int:
    return _export_graph(args, exporter=export_ascii_flowchart)


def _export_graph(args, *, exporter) -> int:
    graph = _load_graph(args.config)
    registry = build_node_registry()
    compiled = GraphCompiler().compile(graph, registry=registry)
    text = exporter(graph, compiled=compiled, registry=registry, expand_nodesets=bool(args.expand_nodesets))
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def _inspect_node(args) -> int:
    from topology_kernel.cli import main as kernel_cli_main

    return kernel_cli_main(
        [
            "inspect-node",
            "--type",
            args.node_type,
            "--module",
            args.module,
            "--class",
            args.class_name,
            *(["--policy", args.policy] if args.policy else []),
        ]
    )


def _quality(args) -> int:
    from topology_kernel.cli import main as kernel_cli_main

    return kernel_cli_main(["quality-check", "--path", args.path])


def _preflight(config_path: str, policy_path: str | None):
    path = Path(config_path)
    document = load_config_document(path)
    plugin_registry, plugin_findings = load_plugins_from_config(document.data, base_path=path.parent)
    policy_result = resolve_effective_policy(
        document.data,
        config_path=path,
        explicit_policy_path=Path(policy_path) if policy_path else None,
        plugin_registry=plugin_registry,
    )
    findings = (*plugin_findings, *collect_config_schema_findings(document.data), *policy_result.findings)
    if findings:
        return None, plugin_registry, policy_result.effective_policy, _report_findings(
            findings,
            policy_result.effective_policy.to_dict(),
        )
    return parse_graph_config(document.data), plugin_registry, policy_result.effective_policy, None


def _report_findings(findings, effective_policy: dict[str, object]) -> HealthReport:
    errors = []
    warnings = []
    source_or_plugin_error = False
    for item in findings:
        if item.severity == "error":
            errors.append(item)
        elif item.severity == "warning":
            warnings.append(item)
        if item.failure_layer in {"source", "syntax", "plugin"}:
            source_or_plugin_error = True
    return HealthReport(
        status="ERROR" if source_or_plugin_error else "FAIL",
        errors=tuple(errors),
        warnings=tuple(warnings),
        effective_policy=effective_policy,
    )


def _load_graph(config_path: str):
    document = load_config_document(Path(config_path))
    return parse_graph_config(document.data)


def _load_input(path: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input JSON root must be an object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
