from __future__ import annotations

from .health_types import HealthFinding


def registry_namespace_findings(registry) -> tuple[HealthFinding, ...]:
    method = getattr(registry, "registration_info", None)
    if not callable(method):
        return ()
    findings: list[HealthFinding] = []
    for info in method():
        expected = _registered_namespace(info.function)
        if not expected or str(info.key).startswith(f"{expected}."):
            continue
        findings.append(
            HealthFinding(
                rule_id="REGISTRY.SMELL.NAMESPACE_MISMATCH",
                severity="warning",
                object_type="registry",
                object_id=str(info.key),
                source_location={"path": info.path, "line": info.line} if info.path else {},
                failure_layer="topology",
                message=f"node key '{info.key}' was registered from {info.function}, expected prefix '{expected}.'",
                suggested_fix_type="fix_registry",
                details={"registered_key": info.key, "expected_namespace": expected, "source_function": info.function},
            )
        )
    return tuple(findings)


def _registered_namespace(function_name: str) -> str:
    prefix = "_register_"
    suffix = "_nodes"
    if not function_name.startswith(prefix) or not function_name.endswith(suffix):
        return ""
    value = function_name[len(prefix) : -len(suffix)]
    return value if value and "." not in value else ""
