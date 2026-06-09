from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

from .base_lib import BaseLibFinding, node_base_lib_imports, scan_base_lib
from .compiler import GraphCompiler, GraphCompileError
from .config_loader import ConfigLoadError, load_config_document
from .config_schema import collect_config_schema_findings
from .graph_config import GraphConfigError, parse_graph_config
from .health import HealthFinding, HealthReport
from .mermaid import export_mermaid
from .node import NodeContract, NodeInfo, PureNode
from .policy import default_effective_policy, resolve_effective_policy
from .plugin import load_plugins_from_config
from .purity import collect_node_metrics, validate_node_class
from .registry import GLOBAL_NODE_REGISTRY
from .boundary import GLOBAL_BOUNDARY_REGISTRY
from .runner import CheckedRunError, run_checked


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate":
        report = _validate_config_path(Path(args.config), policy_path=Path(args.policy) if args.policy else None)
        if args.json:
            print(report.to_json())
        else:
            print(report.status)
            for finding in (*report.errors, *report.warnings):
                print(f"{finding.severity}: {finding.rule_id}: {finding.message}")
        return 0 if report.status in {"PASS", "CONCERNS"} else 1
    if args.command == "inspect-node":
        payload, status = _inspect_node_payload(
            node_type=args.node_type,
            module_path=Path(args.module) if args.module else None,
            class_name=args.class_name,
            policy_path=Path(args.policy) if args.policy else None,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return status
    if args.command == "inspect-config":
        payload, status = _inspect_config_payload(Path(args.config), policy_path=Path(args.policy) if args.policy else None)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return status
    if args.command == "export-mermaid":
        document = load_config_document(Path(args.config))
        graph = parse_graph_config(document.data)
        compiled = GraphCompiler().compile(graph)
        text = export_mermaid(
            graph,
            compiled=compiled,
            expand_nodesets=bool(args.expand_nodesets),
            show_contract=not bool(args.hide_contract),
            show_semantics=not bool(args.hide_semantics),
            show_boundary=not bool(args.hide_boundary),
        )
        output = getattr(args, "output", None)
        if output:
            Path(output).write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0
    if args.command == "run":
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
            payload = {"status": result.health.status, "run_id": result.run_id, "run_dir": str(result.run_dir)}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        except CheckedRunError as exc:
            payload = {
                "status": exc.result.health.status,
                "run_id": exc.result.run_id,
                "run_dir": str(exc.result.run_dir),
                "error": str(exc),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
    parser.error(f"unknown command: {args.command}")
    return 2


def _validate_config_path(path: Path, *, policy_path: Path | None = None) -> HealthReport:
    try:
        document = load_config_document(path)
    except ConfigLoadError as exc:
        return _config_load_error_report(exc, object_type="config", object_id=str(path))

    plugin_registry, plugin_findings = load_plugins_from_config(document.data, base_path=path.parent)
    if plugin_findings:
        return HealthReport(
            status="ERROR",
            errors=tuple(plugin_findings),
            effective_policy=default_effective_policy().to_dict(),
        )
    policy_result = resolve_effective_policy(document.data, config_path=path, explicit_policy_path=policy_path, plugin_registry=plugin_registry)
    effective_policy = policy_result.effective_policy.to_dict()
    schema_findings = _dedupe_findings((*collect_config_schema_findings(document.data), *policy_result.findings))
    if schema_findings:
        status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin"} for finding in schema_findings) else "FAIL"
        return HealthReport(
            status=status,
            errors=tuple(finding for finding in schema_findings if finding.severity == "error"),
            warnings=tuple(finding for finding in schema_findings if finding.severity == "warning"),
            effective_policy=effective_policy,
        )

    try:
        graph = parse_graph_config(document.data)
    except GraphConfigError as exc:
        return _graph_config_error_report(exc, path=path, effective_policy=effective_policy)
    try:
        compiled = GraphCompiler().compile(graph)
    except GraphCompileError as exc:
        return _fail_report(
            "GRAPH.COMPILE",
            str(exc),
            "pipeline",
            "pipeline",
            "topology",
            effective_policy=effective_policy,
        )
    return HealthReport(
        status="PASS",
        info={
            "nodes": len(graph.nodes),
            "nodesets": sorted(graph.nodesets),
            "explicit_edges": [edge.pair for edge in compiled.explicit_edges],
            "data_edges": [edge.pair for edge in compiled.data_edges],
            "effective_edges": [edge.pair for edge in compiled.effective_edges],
            "loops": [loop.name for loop in compiled.loops],
        },
        effective_policy=effective_policy,
    )


def _inspect_config_payload(path: Path, *, policy_path: Path | None = None) -> tuple[dict[str, object], int]:
    report = _validate_config_path(path, policy_path=policy_path)
    payload: dict[str, object] = {"health": report.to_dict()}
    if report.status not in {"PASS", "CONCERNS"}:
        return payload, 1
    document = load_config_document(path)
    graph = parse_graph_config(document.data)
    compiled = GraphCompiler().compile(graph)
    payload["config"] = {
        "inputs": list(graph.inputs),
        "nodes": [
            {
                "name": node.name,
                "type": node.node_type,
                "requires": list(node.requires),
                "provides": list(node.provides),
            }
            for node in graph.nodes
        ],
        "nodesets": [
            {
                "name": nodeset.name,
                "display_name": nodeset.display_name,
                "category": nodeset.category,
                "description": nodeset.description,
                "version": nodeset.version,
                "purity": nodeset.purity,
                "requires": list(nodeset.requires),
                "provides": list(nodeset.provides),
                "exports": list(nodeset.exports),
                "node_count": len(nodeset.graph.nodes),
            }
            for nodeset in graph.nodesets.values()
        ],
        "boundary": _boundary_payload(graph),
        "loops": [
            {
                "name": loop.name,
                "edges": [list(edge) for edge in loop.edges],
                "max_iterations": loop.max_iterations,
                "nodes": list(loop.nodes),
                "until": loop.until,
            }
            for loop in graph.loops
        ],
        "effective_edges": [list(edge.pair) for edge in compiled.effective_edges],
    }
    return payload, 0


def _inspect_node_payload(
    *,
    node_type: str,
    module_path: Path | None,
    class_name: str | None,
    policy_path: Path | None,
) -> tuple[dict[str, object], int]:
    if module_path is None:
        report = _fail_report(
            "NODE.INSPECT.MODULE_REQUIRED",
            "inspect-node currently requires --module because no project registry loader is configured",
            "node",
            node_type,
            "schema",
        )
        return {"health": report.to_dict()}, 1
    try:
        node_cls = _load_node_class(module_path, node_type=node_type, class_name=class_name)
    except (OSError, ImportError, AttributeError, TypeError, ValueError) as exc:
        report = _error_report("NODE.INSPECT.LOAD_ERROR", str(exc), "node", node_type, "schema")
        return {"health": report.to_dict()}, 1

    policy_result = resolve_effective_policy({}, config_path=module_path, explicit_policy_path=policy_path)
    effective_policy = policy_result.effective_policy.to_dict()
    if policy_result.findings:
        status = "ERROR" if any(finding.failure_layer in {"source", "syntax"} for finding in policy_result.findings) else "FAIL"
        report = HealthReport(status=status, errors=tuple(policy_result.findings), effective_policy=effective_policy)
        return {"health": report.to_dict()}, 1

    info = getattr(node_cls, "NODE_INFO", None)
    contract = getattr(node_cls, "CONTRACT", None)
    known_classes = _module_node_class_names(node_cls)
    violations = validate_node_class(
        node_cls,
        policy=policy_result.effective_policy.to_purity_policy(),
        expected_type=node_type,
        known_node_class_names=tuple(name for name in known_classes if name != node_cls.__name__),
        scan_module=True,
    )
    errors: list[HealthFinding] = []
    warnings: list[HealthFinding] = []
    for violation in violations:
        finding = HealthFinding(
            rule_id=violation.rule_id,
            severity=violation.severity,
            object_type="node",
            object_id=node_type,
            source_location=violation.source_location,
            failure_layer=violation.failure_layer,
            message=violation.message,
            suggested_fix_type=violation.suggested_fix_type,
            details={"legacy_code": violation.code, **dict(violation.details)},
        )
        if violation.severity == "warning":
            warnings.append(finding)
        else:
            errors.append(finding)
    base_report = scan_base_lib(module_path.parent, policy=policy_result.effective_policy.to_purity_policy())
    unhealthy_base_modules = {finding.object_id for finding in base_report.findings}
    for base_finding in base_report.findings:
        finding = _base_lib_finding_to_health(base_finding)
        if base_finding.severity == "warning":
            warnings.append(finding)
        else:
            errors.append(finding)
    for imported in node_base_lib_imports(node_cls):
        matched = _matching_unhealthy_base_module(imported, unhealthy_base_modules)
        if matched:
            errors.append(
                HealthFinding(
                    rule_id="NODE.BASE_LIB.INDIRECT_VIOLATION",
                    severity="error",
                    object_type="node",
                    object_id=node_type,
                    failure_layer="base_lib",
                    message=f"node imports unhealthy base_lib module: {imported} -> {matched}",
                    suggested_fix_type="fix_base_lib",
                    details={"imported_module": imported, "unhealthy_base_lib": matched},
                )
            )
    report = HealthReport(
        status="FAIL" if errors else "CONCERNS" if warnings else "PASS",
        errors=tuple(errors),
        warnings=tuple(warnings),
        effective_policy=effective_policy,
    )
    source = _class_source(node_cls)
    metrics = collect_node_metrics(node_cls)
    payload = {
        "health": report.to_dict(),
        "node": {
            "class_name": node_cls.__name__,
            "type_key": getattr(info, "type_key", ""),
            "metadata": _node_info_payload(info),
            "contract": _contract_payload(contract),
            "source": {
                "path": inspect.getsourcefile(node_cls) or "",
                "lines": len(source.splitlines()) if source else 0,
                "bytes": len(source.encode("utf-8")) if source else 0,
            },
            "metrics": metrics.to_dict(),
        },
        "base_lib": base_report.to_dict(),
    }
    return payload, 0 if report.status in {"PASS", "CONCERNS"} else 1


def _load_node_class(module_path: Path, *, node_type: str, class_name: str | None) -> type[PureNode]:
    if not module_path.exists():
        raise OSError(f"module file does not exist: {module_path}")
    module_name = f"_topology_kernel_inspect_{abs(hash(module_path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if class_name:
        node_cls = getattr(module, class_name)
        if not isinstance(node_cls, type):
            raise TypeError(f"{class_name} is not a class")
        return node_cls
    matches = []
    for value in module.__dict__.values():
        if not isinstance(value, type):
            continue
        info = getattr(value, "NODE_INFO", None)
        if isinstance(info, NodeInfo) and info.type_key == node_type:
            matches.append(value)
    if not matches:
        raise ValueError(f"no node class with NODE_INFO.type_key={node_type!r}")
    if len(matches) > 1:
        raise ValueError(f"multiple node classes with NODE_INFO.type_key={node_type!r}; pass --class")
    return matches[0]


def _node_info_payload(info: object) -> dict[str, object]:
    if not isinstance(info, NodeInfo):
        return {}
    return {
        "type_key": info.type_key,
        "display_name": info.display_name,
        "category": info.category,
        "description": info.description,
        "version": info.version,
        "purity": info.purity,
    }


def _contract_payload(contract: object) -> dict[str, object]:
    if not isinstance(contract, NodeContract):
        return {}
    return {
        "requires": list(contract.requires),
        "provides": list(contract.provides),
        "input_semantics": {key: list(value) for key, value in contract.input_semantics.items()},
        "output_semantics": {key: list(value) for key, value in contract.output_semantics.items()},
        "params_schema": dict(contract.params_schema),
        "output_schema": dict(contract.output_schema),
        "examples": [dict(example) for example in contract.examples],
    }


def _boundary_payload(graph) -> dict[str, object]:
    if graph.boundary is None:
        return {}
    return {
        "type": graph.boundary.boundary_type,
        "consumes": list(graph.boundary.consumes),
        "provides": list(graph.boundary.provides),
        "allowed_paths": list(graph.boundary.allowed_paths),
        "run_dir": graph.boundary.config.get("run_dir", ""),
    }


def _load_initial_input(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("--input JSON root must be an object")
    return {str(key): value for key, value in payload.items()}


def _module_node_class_names(node_cls: type[PureNode]) -> tuple[str, ...]:
    module = sys.modules.get(node_cls.__module__)
    if module is None:
        return ()
    names: list[str] = []
    for value in module.__dict__.values():
        if isinstance(value, type) and isinstance(getattr(value, "NODE_INFO", None), NodeInfo):
            names.append(value.__name__)
    return tuple(sorted(set(names)))


def _base_lib_finding_to_health(finding: BaseLibFinding) -> HealthFinding:
    return HealthFinding(
        rule_id=finding.rule_id,
        severity=finding.severity,
        object_type=finding.object_type,
        object_id=finding.object_id,
        source_location=finding.source_location,
        failure_layer=finding.failure_layer,
        message=finding.message,
        suggested_fix_type=finding.suggested_fix_type,
        details=finding.details,
    )


def _matching_unhealthy_base_module(imported: str, unhealthy: set[str]) -> str:
    for module in unhealthy:
        if imported == module or imported.startswith(f"{module}.") or module.startswith(f"{imported}."):
            return module
    return ""


def _class_source(node_cls: type[PureNode]) -> str:
    try:
        return inspect.getsource(node_cls)
    except (OSError, TypeError):
        return ""


def _error_report(
    rule_id: str,
    message: str,
    object_type: str,
    object_id: str,
    failure_layer: str,
    *,
    source_location: dict[str, object] | None = None,
    effective_policy: Mapping[str, object] | None = None,
) -> HealthReport:
    return HealthReport(
        status="ERROR",
        errors=(
            HealthFinding(
                rule_id=rule_id,
                severity="error",
                object_type=object_type,
                object_id=object_id,
                source_location=source_location or {},
                failure_layer=failure_layer,
                message=message,
                suggested_fix_type="fix_config",
            ),
        ),
        effective_policy=dict(effective_policy or {}),
    )


def _fail_report(
    rule_id: str,
    message: str,
    object_type: str,
    object_id: str,
    failure_layer: str,
    *,
    effective_policy: Mapping[str, object] | None = None,
) -> HealthReport:
    return HealthReport(
        status="FAIL",
        errors=(
            HealthFinding(
                rule_id=rule_id,
                severity="error",
                object_type=object_type,
                object_id=object_id,
                failure_layer=failure_layer,
                message=message,
                suggested_fix_type="fix_config",
            ),
        ),
        effective_policy=dict(effective_policy or {}),
    )


def _config_load_error_report(exc: ConfigLoadError, *, object_type: str, object_id: str) -> HealthReport:
    return _error_report(
        exc.rule_id,
        exc.message,
        object_type,
        object_id,
        exc.failure_layer,
        source_location=exc.source_location,
        effective_policy=default_effective_policy().to_dict(),
    )


def _graph_config_error_report(
    exc: GraphConfigError,
    *,
    path: Path,
    effective_policy: Mapping[str, object],
) -> HealthReport:
    detail = getattr(exc, "detail", str(exc))
    if "unknown node" in detail or "references unknown" in detail:
        return _fail_report(
            "CONFIG.TOPOLOGY",
            str(exc),
            "pipeline",
            "pipeline",
            "topology",
            effective_policy=effective_policy,
        )
    return _fail_report(
        "CONFIG.SCHEMA.PARSE",
        str(exc),
        "config",
        str(path),
        "schema",
        effective_policy=effective_policy,
    )


def _dedupe_findings(findings: tuple[HealthFinding, ...]) -> tuple[HealthFinding, ...]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[HealthFinding] = []
    for finding in findings:
        key = (finding.rule_id, finding.object_type, finding.object_id, finding.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return tuple(unique)
