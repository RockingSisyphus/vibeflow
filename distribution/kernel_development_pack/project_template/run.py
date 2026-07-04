from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "kernel" / "MANIFEST.sha256"
KERNEL_ARCHIVE_PATH = ROOT / "kernel" / "vibeflow-kernel.zip"
# Treat unpacked kernel sources as unexpected so AI work stays focused on project/.
PROTECTED_PREFIXES = ("kernel/vibeflow/",)
PROTECTED_FILES = {
    "run.py",
    "kernel/README.md",
    "AGENTS.md",
    "README.md",
}


class KernelIntegrityError(RuntimeError):
    def __init__(self, *, changed: list[str], missing: list[str], unexpected: list[str]) -> None:
        super().__init__("kernel integrity check failed")
        self.changed = changed
        self.missing = missing
        self.unexpected = unexpected


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_protected_relative(relative: str) -> bool:
    return relative in PROTECTED_FILES or any(relative.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def _iter_protected_files() -> list[str]:
    paths: list[str] = []
    for relative in PROTECTED_FILES:
        if (ROOT / relative).is_file():
            paths.append(relative)
    if KERNEL_ARCHIVE_PATH.is_file():
        paths.append(KERNEL_ARCHIVE_PATH.relative_to(ROOT).as_posix())
    kernel_root = ROOT / "kernel" / "vibeflow"
    if kernel_root.exists():
        for path in kernel_root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc"):
                paths.append(path.relative_to(ROOT).as_posix())
    return sorted(set(paths))


def _read_manifest() -> dict[str, str]:
    if not MANIFEST_PATH.is_file():
        raise KernelIntegrityError(changed=[], missing=[MANIFEST_PATH.relative_to(ROOT).as_posix()], unexpected=[])
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(MANIFEST_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as exc:
            raise KernelIntegrityError(
                changed=[f"{MANIFEST_PATH.relative_to(ROOT).as_posix()}:{line_number}"],
                missing=[],
                unexpected=[],
            ) from exc
        entries[relative] = digest
    return entries


def _verify_kernel_manifest() -> None:
    entries = _read_manifest()
    changed: list[str] = []
    missing: list[str] = []
    unexpected: list[str] = []
    for relative, expected in entries.items():
        path = ROOT / relative
        if not path.is_file():
            missing.append(relative)
        elif _hash_file(path) != expected:
            changed.append(relative)
    recorded = set(entries)
    for relative in _iter_protected_files():
        if _is_protected_relative(relative) and relative not in recorded:
            unexpected.append(relative)
    if changed or missing or unexpected:
        raise KernelIntegrityError(changed=changed, missing=missing, unexpected=unexpected)


def _format_integrity_error(exc: KernelIntegrityError) -> str:
    lines = [
        "KERNEL INTEGRITY CHECK FAILED",
        "",
        "The distributed kernel file, launcher, or guide files were modified.",
        "This may mean an AI or developer changed kernel rules to bypass validation.",
        "",
    ]
    for title, items in (("Changed", exc.changed), ("Missing", exc.missing), ("Unexpected", exc.unexpected)):
        if items:
            lines.append(f"{title}:")
            lines.extend(f"- {item}" for item in sorted(items))
            lines.append("")
    lines.append("Rebuild or restore the distribution from a trusted source.")
    return "\n".join(lines)


def _run_integrity_check() -> None:
    try:
        _verify_kernel_manifest()
    except KernelIntegrityError as exc:
        print(_format_integrity_error(exc), file=sys.stderr)
        raise SystemExit(2) from exc


_run_integrity_check()
sys.path.insert(0, str(KERNEL_ARCHIVE_PATH))
sys.path.insert(0, str(ROOT / "project"))

from vibeflow import (  # noqa: E402
    CheckedRunError,
    GraphCompiler,
    HealthReport,
    export_ascii_flowchart,
    export_mermaid,
    load_config_document,
    load_config_resources,
    load_plugins_from_config,
    parse_graph_config,
    resolve_effective_policy,
    render_mermaid_svg,
    RuntimeOptions,
    run_checked,
    validate_graph_health,
)

from vibeflow.config_schema import collect_config_schema_findings  # noqa: E402
from vibeflow.mermaid_review_svg import render_review_columns_svg  # noqa: E402
from vibeflow.mermaid_render import (  # noqa: E402
    DEFAULT_MERMAID_MAX_EDGES,
    DEFAULT_MERMAID_MAX_TEXT_SIZE,
    EXPANDED_MERMAID_MAX_EDGES,
    EXPANDED_MERMAID_MAX_TEXT_SIZE,
)
from vibeflow.planned_behavior import project_root_for_config  # noqa: E402

from registry import build_node_registry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="project-runner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify-kernel")
    _add_config_command(sub, "validate")
    _add_config_command(sub, "inspect-config")
    run_cmd = _add_config_command(sub, "run")
    run_cmd.add_argument("--run-root", default="runs")
    run_cmd.add_argument("--input", required=False)
    _add_runtime_options(run_cmd)
    mermaid = _add_config_command(sub, "mermaid")
    mermaid.add_argument("--output", required=False)
    mermaid.add_argument(
        "--expand-nodesets",
        action="store_true",
        help="write expanded Mermaid source only; do not render this .mmd directly with mmdc for review SVG",
    )
    ascii_chart = _add_config_command(sub, "ascii")
    ascii_chart.add_argument("--output", required=False)
    ascii_chart.add_argument("--expand-nodesets", action="store_true")
    svg = _add_config_command(sub, "svg")
    svg.add_argument("--output", required=True)
    svg.add_argument(
        "--expand-nodesets",
        action="store_true",
        help="render expanded review-columns/detail-panel SVG; use this instead of mmdc on graph.expanded.mmd",
    )
    svg.add_argument("--mermaid-max-text-size", type=int, default=None)
    svg.add_argument("--mermaid-max-edges", type=int, default=None)
    svg.add_argument("--review-fragment-max-width", type=float, default=None)
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


def _add_runtime_options(command) -> None:
    command.add_argument("--runtime-profile", choices=("debug", "train"), default=None)
    command.add_argument("--trace", choices=("full", "boundary", "off"), default=None)
    command.add_argument("--execution", choices=("plan", "block", "compiled"), default=None)
    command.add_argument("--run-hooks", action=argparse.BooleanOptionalAction, default=None)
    command.add_argument("--node-hooks", action=argparse.BooleanOptionalAction, default=None)
    command.add_argument("--nodeset-hooks", action=argparse.BooleanOptionalAction, default=None)
    command.add_argument("--block-hooks", action=argparse.BooleanOptionalAction, default=None)
    command.add_argument("--async-flush-timeout", type=float, default=None)
    command.add_argument("--allow-planned-stub", action="store_true")


def _runtime_options_from_args(args) -> RuntimeOptions:
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


def _dispatch(args) -> int:
    handlers = {
        "validate": _validate,
        "inspect-config": _inspect_config,
        "run": _run,
        "ascii": _ascii,
        "mermaid": _mermaid,
        "svg": _svg,
        "inspect-node": _inspect_node,
        "quality": _quality,
        "verify-kernel": _verify_kernel,
    }
    return handlers[args.command](args)


def _verify_kernel(args) -> int:
    print("kernel integrity: OK")
    return 0


def _validate(args) -> int:
    graph, plugin_registry, effective_policy, resources, schema_report = _preflight(args.config, args.policy)
    if schema_report is not None:
        print(schema_report.to_json())
        return 1
    report = validate_graph_health(
        graph,
        registry=build_node_registry(),
        plugin_registry=plugin_registry,
        global_config=resources.global_config,
        purity_policy=effective_policy.to_purity_policy(),
    )
    report = replace(report, effective_policy=effective_policy.to_dict())
    print(report.to_json())
    return 0 if report.status in {"PASS", "CONCERNS"} else 1


def _inspect_config(args) -> int:
    graph, resources = _load_graph_and_resources(args.config)
    payload = {
        "nodes": [
            {
                "name": node.name,
                "type": node.node_type,
                "requires": [_requirement_payload(item) for item in node.requires],
                "provides": [_provider_payload(item) for item in node.provides],
                "status": node.status,
                "flow_kind": node.flow_kind,
                "planned_behavior": node.planned_behavior.to_dict(),
            }
            for node in graph.nodes
        ],
        "edges": [edge.__dict__ for edge in graph.edges],
        "max_steps": graph.max_steps,
        "nodesets": [
            {
                "name": nodeset.name,
                "status": nodeset.status,
                "planned_behavior": nodeset.planned_behavior.to_dict(),
                "requires": [_requirement_payload(item) for item in nodeset.requires],
                "provides": [_provider_payload(item) for item in nodeset.provides],
                "exports": [_provider_payload(item) for item in nodeset.exports],
            }
            for nodeset in graph.nodesets.values()
        ],
        "resources": resources.to_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _provider_payload(item) -> dict[str, str]:
    return {"key": item.key, "type": item.type}


def _requirement_payload(item) -> dict[str, str]:
    return {"type": item.type, "cardinality": item.cardinality}


def _run(args) -> int:
    initial = _load_input(args.input) if args.input else {}
    try:
        result = run_checked(
            args.config,
            registry=build_node_registry(),
            initial=initial,
            policy_path=args.policy,
            run_root=args.run_root,
            runtime_options=_runtime_options_from_args(args),
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


def _svg(args) -> int:
    graph, resources = _load_graph_and_resources(args.config)
    registry = build_node_registry()
    compiled = GraphCompiler().compile(graph, registry=registry)
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
    if bool(args.expand_nodesets):
        review_kwargs = {}
        if args.review_fragment_max_width is not None:
            review_kwargs["review_fragment_max_width"] = float(args.review_fragment_max_width)
        render_review_columns_svg(
            graph,
            compiled,
            Path(args.output),
            registry=registry,
            resources=resources,
            expand_nodesets=True,
            max_text_size=max_text_size,
            max_edges=max_edges,
            **review_kwargs,
        )
        return 0
    text = export_mermaid(graph, compiled=compiled, registry=registry, expand_nodesets=False, resources=resources)
    render_mermaid_svg(text, Path(args.output), max_text_size=max_text_size, max_edges=max_edges)
    return 0


def _export_graph(args, *, exporter) -> int:
    graph, resources = _load_graph_and_resources(args.config)
    registry = build_node_registry()
    compiled = GraphCompiler().compile(graph, registry=registry)
    kwargs = {"resources": resources} if exporter is export_mermaid else {}
    text = exporter(graph, compiled=compiled, registry=registry, expand_nodesets=bool(args.expand_nodesets), **kwargs)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def _inspect_node(args) -> int:
    from vibeflow.cli import main as kernel_cli_main

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
    from vibeflow.cli import main as kernel_cli_main

    return kernel_cli_main(["quality-check", "--path", args.path])


def _preflight(config_path: str, policy_path: str | None):
    path = Path(config_path)
    document = load_config_document(path)
    plugin_registry, plugin_findings = load_plugins_from_config(document.data, base_path=path.parent)
    resources, resource_findings = load_config_resources(document.data, base_path=path.parent, plugin_registry=plugin_registry)
    policy_result = resolve_effective_policy(
        document.data,
        config_path=path,
        explicit_policy_path=Path(policy_path) if policy_path else None,
        plugin_registry=plugin_registry,
    )
    findings = (*plugin_findings, *resource_findings, *collect_config_schema_findings(document.data), *policy_result.findings)
    if findings:
        return None, plugin_registry, policy_result.effective_policy, resources, _report_findings(
            findings,
            policy_result.effective_policy.to_dict(),
        )
    return parse_graph_config(document.data, project_root=project_root_for_config(path)), plugin_registry, policy_result.effective_policy, resources, None


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
    path = Path(config_path)
    document = load_config_document(path)
    return parse_graph_config(document.data, project_root=project_root_for_config(path))


def _load_graph_and_resources(config_path: str):
    path = Path(config_path)
    document = load_config_document(path)
    plugin_registry, plugin_findings = load_plugins_from_config(document.data, base_path=path.parent)
    resources, resource_findings = load_config_resources(document.data, base_path=path.parent, plugin_registry=plugin_registry)
    findings = (*plugin_findings, *resource_findings, *collect_config_schema_findings(document.data))
    if findings:
        raise ValueError("; ".join(f"{finding.rule_id}: {finding.message}" for finding in findings))
    return parse_graph_config(document.data, project_root=project_root_for_config(path)), resources


def _load_input(path: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input JSON root must be an object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
