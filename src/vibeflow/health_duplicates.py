from __future__ import annotations

from .health_types import HealthFinding


def duplicate_logic_findings(fingerprints: dict[str, str], node_metrics: dict[str, dict[str, object]]) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    for first, second in _duplicate_fingerprints(fingerprints):
        first_shape = str(node_metrics.get(first, {}).get("run_pure_shape", ""))
        second_shape = str(node_metrics.get(second, {}).get("run_pure_shape", ""))
        if first_shape == second_shape == "wrapper":
            continue
        findings.append(
            HealthFinding(
                rule_id="GRAPH.SMELL.DUPLICATE_LOGIC",
                severity="warning",
                object_type="node",
                object_id=f"{first},{second}",
                failure_layer="implementation",
                message=f"nodes appear to have duplicate run_pure logic: {first}, {second}",
                suggested_fix_type="split_node",
                details={"run_pure_shapes": {first: first_shape, second: second_shape}},
            )
        )
    return tuple(findings)


def _duplicate_fingerprints(fingerprints: dict[str, str]) -> tuple[tuple[str, str], ...]:
    grouped: dict[str, list[str]] = {}
    for node_name, fingerprint in fingerprints.items():
        grouped.setdefault(fingerprint, []).append(node_name)
    duplicates: list[tuple[str, str]] = []
    for names in grouped.values():
        if len(names) < 2:
            continue
        names = sorted(names)
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                duplicates.append((first, second))
    return tuple(duplicates)
