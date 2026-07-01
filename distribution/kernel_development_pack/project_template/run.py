from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "kernel" / "MANIFEST.sha256"
PROTECTED_PREFIXES = ("kernel/vibeflow/",)
PROTECTED_FILES = {"run.py", "kernel/README.md", "AGENTS.md", "README.md"}


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
        "The distributed kernel or launcher files were modified.",
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
sys.path.insert(0, str(ROOT / "kernel"))
sys.path.insert(0, str(ROOT / "project"))

from vibeflow import (  # noqa: E402
    CheckedRunError,
    GraphCompiler,
    HealthReport,
    export_ascii_flowchart,
    export_mermaid,
    load_config_document,
    load_plugins_from_config,
    parse_graph_config,
    resolve_effective_policy,
    render_mermaid_svg,
    run_checked,
    validate_graph_health,
)

from vibeflow.config_schema import collect_config_schema_findings  # noqa: E402

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
    mermaid = _add_config_command(sub, "mermaid")
    mermaid.add_argument("--output", required=False)
    mermaid.add_argument("--expand-nodesets", action="store_true")
    ascii_chart = _add_config_command(sub, "ascii")
    ascii_chart.add_argument("--output", required=False)
    ascii_chart.add_argument("--expand-nodesets", action="store_true")
    svg = _add_config_command(sub, "svg")
    svg.add_argument("--output", required=True)
    svg.add_argument("--expand-nodesets", action="store_true")
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
    graph, plugin_registry, effective_policy, schema_report = _preflight(args.config, args.policy)
    if schema_report is not None:
        print(schema_report.to_json())
        return 1
    report = validate_graph_health(
        graph,
        registry=build_node_registry(),
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
        "max_steps": graph.max_steps,
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


def _svg(args) -> int:
    graph = _load_graph(args.config)
    registry = build_node_registry()
    compiled = GraphCompiler().compile(graph, registry=registry)
    text = export_mermaid(graph, compiled=compiled, registry=registry, expand_nodesets=bool(args.expand_nodesets))
    render_mermaid_svg(text, Path(args.output))
    return 0


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
