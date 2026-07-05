from __future__ import annotations

from typing import Mapping

from .health_types import HealthFinding


def duplicate_logic_findings(
    fingerprints: dict[str, str],
    node_metrics: dict[str, dict[str, object]],
    *,
    node_types: Mapping[str, str] | None = None,
    node_similarities: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    types = dict(node_types or {})
    similarities = {name: dict(value) for name, value in (node_similarities or {}).items()}
    for fingerprint, group in _fingerprint_groups(fingerprints).items():
        if len(group) < 2:
            continue
        group = sorted(group)
        group_shapes = {name: str(node_metrics.get(name, {}).get("run_pure_shape", "")) for name in group}
        if set(group_shapes.values()) == {"wrapper"}:
            continue
        for index, first in enumerate(group):
            for second in group[index + 1:]:
                if _is_declared_similar(first, second, similarities):
                    continue
                first_shape = group_shapes.get(first, "")
                second_shape = group_shapes.get(second, "")
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
                        details={
                            "nodes": [first, second],
                            "node_types": {name: types.get(name, "") for name in (first, second)},
                            "run_pure_shapes": {first: first_shape, second: second_shape},
                            "fingerprint": fingerprint,
                            "duplicate_group": group,
                            "suppression_hint": "If this duplicate is intentional, declare similar_to with relationship variant or copy and a reason on the config node.",
                        },
                    )
                )
    return tuple(findings)


def _fingerprint_groups(fingerprints: Mapping[str, str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for node_name, fingerprint in fingerprints.items():
        grouped.setdefault(fingerprint, []).append(node_name)
    return grouped


def _is_declared_similar(first: str, second: str, similarities: Mapping[str, Mapping[str, str]]) -> bool:
    first_target = str(similarities.get(first, {}).get("node", "")).strip()
    second_target = str(similarities.get(second, {}).get("node", "")).strip()
    return first_target == second or second_target == first or (bool(first_target) and first_target == second_target)


def _duplicate_fingerprints(fingerprints: dict[str, str]) -> tuple[tuple[str, str], ...]:
    duplicates: list[tuple[str, str]] = []
    for names in _fingerprint_groups(fingerprints).values():
        if len(names) < 2:
            continue
        names = sorted(names)
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                duplicates.append((first, second))
    return tuple(duplicates)
