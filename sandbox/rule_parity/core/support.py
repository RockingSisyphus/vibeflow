"""Observation formatting; never substitutes findings for a real API result."""

from __future__ import annotations


def plain(value):
    if hasattr(value, "items"):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [plain(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {key: plain(getattr(value, key)) for key in value.__dataclass_fields__}
    return value


def observe(operation):
    try:
        value = operation()
        if isinstance(value, dict):
            return value
        if hasattr(value, "errors") and hasattr(value, "warnings"):
            findings = (*value.errors, *value.warnings)
        elif hasattr(value, "findings"):
            findings = value.findings
        else:
            findings = tuple(value or ())
        diagnostics = tuple(item for item in findings if hasattr(item, "rule_id") or hasattr(item, "code"))
        codes = sorted({(str(getattr(item, "rule_id", getattr(item, "code", ""))),
            str(getattr(item, "severity", getattr(item, "details", {}).get("severity", "warning")))) for item in diagnostics})
        status = getattr(value, "status", None) or ("FAIL" if any(severity == "error" for _, severity in codes) else "CONCERNS" if codes else "PASS")
        metrics = {"finding_details": [{"code": getattr(item, "rule_id", getattr(item, "code", "")),
            "object_id": getattr(item, "object_id", ""), "details": plain(item.details)} for item in diagnostics],
            "finding_count": len(diagnostics)}
        if hasattr(value, "dependency_graph"):
            metrics.update(dependency_graph=plain(value.dependency_graph), longest_dependency_chain=plain(value.longest_dependency_chain),
                structure_summary=plain(value.structure_summary), prefix_clusters=plain(value.prefix_clusters))
        if hasattr(value, "compiled_graph"):
            compiled = value.compiled_graph
            metrics.update(order=list(compiled.order), schedule_edges=[list(edge.pair) for edge in compiled.resolved_schedule_edges],
                transfer_edges=[list(edge.pair) for edge in compiled.resolved_transfer_edges], flow_kinds=plain(compiled.flow_kinds))
        if hasattr(value, "info"):
            metrics["info"] = plain(value.info)
        return {"status": status, "codes": [{"code": code, "severity": severity} for code, severity in codes],
            "positions": [{"code": getattr(item, "rule_id", getattr(item, "code", "")), **plain(item.source_location)}
                for item in diagnostics if getattr(item, "source_location", {})],
            "metrics": metrics, "message": "; ".join(item.message for item in diagnostics)}
    except Exception as error:
        return {"status": "ERROR", "codes": [{"code": str(getattr(error, "rule_id", getattr(error, "code", type(error).__name__))), "severity": "error"}],
            "positions": [], "metrics": {"exception": type(error).__name__, "details": plain(getattr(error, "details", {}))}, "message": str(error)}


def expectation(*codes, **extra):
    return {"codes": [{"code": code, "severity": severity} for code, severity in codes], "exact_codes": True, **extra}


def append(rows, case_id, title, family, operation, expected, *, classification="preserved", notes="", evidence=""):
    rows.append({"id": "core.variant." + case_id, "title": title, "family": family,
        "expected": expected, "actual": observe(operation), "classification": classification, "notes": notes, "evidence": evidence})
