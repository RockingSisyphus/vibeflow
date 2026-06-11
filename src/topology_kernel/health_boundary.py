from __future__ import annotations

import ast
import inspect

from .ast_rules import call_name
from .boundary import BoundaryRegistry, BoundaryRegistryError
from .graph_config import GraphConfig
from .health_types import HealthFinding


DECISION_LOGIC_TERMS = ("rank", "score", "audit", "plan", "strategy")


def validate_boundary_health(
    graph: GraphConfig,
    *,
    boundary_registry: BoundaryRegistry | None,
) -> tuple[HealthFinding, ...]:
    spec = graph.boundary
    if spec is None:
        return ()
    findings: list[HealthFinding] = []
    if boundary_registry is None:
        findings.append(_boundary_finding("BOUNDARY.TYPE.UNRESOLVED", "graph declares boundary but no boundary registry was provided", spec.boundary_type))
    else:
        try:
            boundary_cls = boundary_registry.get(spec.boundary_type)
        except BoundaryRegistryError as exc:
            findings.append(_boundary_finding("BOUNDARY.TYPE.UNKNOWN", str(exc), spec.boundary_type))
        else:
            findings.extend(_boundary_decision_logic_findings(spec.boundary_type, boundary_cls))
    findings.extend(_boundary_key_findings(tuple(spec.consumes), prefix=("effects.", "outbox."), rule_id="BOUNDARY.CONTRACT.CONSUMES_KEY"))
    findings.extend(_boundary_key_findings(tuple(spec.provides), prefix=("io.",), rule_id="BOUNDARY.CONTRACT.PROVIDES_KEY"))
    findings.extend(_boundary_config_findings(spec.boundary_type, spec.config))
    return tuple(findings)


def boundary_info(graph: GraphConfig) -> dict[str, object]:
    spec = graph.boundary
    if spec is None:
        return {}
    return {
        "type": spec.boundary_type,
        "consumes": list(spec.consumes),
        "provides": list(spec.provides),
        "allowed_paths": list(spec.allowed_paths),
        "run_dir": spec.config.get("run_dir", ""),
    }


def _boundary_key_findings(keys: tuple[str, ...], *, prefix: tuple[str, ...], rule_id: str) -> list[HealthFinding]:
    findings = []
    for key in keys:
        if not key.startswith(prefix):
            allowed = " or ".join(prefix)
            findings.append(_boundary_finding(rule_id, f"boundary key must start with {allowed}: {key}", key))
    return findings


def _boundary_config_findings(boundary_type: str, config: dict[str, object]) -> list[HealthFinding]:
    findings = []
    run_dir = config.get("run_dir")
    allowed_paths = config.get("allowed_paths")
    if run_dir is not None and not (isinstance(run_dir, str) and run_dir.strip()):
        findings.append(_boundary_finding("BOUNDARY.CONFIG.RUN_DIR", "boundary.config.run_dir must be a non-empty string", boundary_type))
    if allowed_paths is not None and not _is_string_list(allowed_paths):
        findings.append(_boundary_finding("BOUNDARY.CONFIG.ALLOWED_PATHS", "boundary.config.allowed_paths must be a list of non-empty strings", boundary_type))
    return findings


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(path, str) and path.strip() for path in value)


def _boundary_decision_logic_findings(boundary_type: str, boundary_cls: type) -> list[HealthFinding]:
    try:
        source = inspect.getsource(boundary_cls)
        path = inspect.getsourcefile(boundary_cls) or ""
        start_line = inspect.getsourcelines(boundary_cls)[1]
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return []
    findings = []
    for node in ast.walk(tree):
        name = _decision_name(node)
        if not name or not _looks_like_decision_logic(name):
            continue
        findings.append(
            _boundary_finding(
                "BOUNDARY.SMELL.DECISION_LOGIC",
                f"boundary contains decision-like logic '{name}'; consider moving strategy into node/base_lib and passing an explicit request",
                boundary_type,
                severity="warning",
                source_location={"path": path, "line": start_line + getattr(node, "lineno", 1) - 1, "column": getattr(node, "col_offset", 0) + 1},
                details={"name": name},
            )
        )
    return findings


def _decision_name(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, ast.Call):
        return call_name(node.func)
    return ""


def _looks_like_decision_logic(name: str) -> bool:
    normalized = name.casefold()
    if "select_" in normalized and "provider" in normalized:
        return True
    return any(term in normalized.split(".")[-1] for term in DECISION_LOGIC_TERMS)


def _boundary_finding(
    rule_id: str,
    message: str,
    object_id: str,
    *,
    severity: str = "error",
    source_location: dict[str, object] | None = None,
    details: dict[str, object] | None = None,
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity=severity,
        object_type="boundary",
        object_id=object_id,
        source_location=source_location or {},
        failure_layer="boundary",
        message=message,
        suggested_fix_type="fix_boundary",
        details=details or {},
    )
