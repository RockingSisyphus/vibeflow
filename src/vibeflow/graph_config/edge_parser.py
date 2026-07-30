from __future__ import annotations

from typing import Any, Mapping

from vibeflow.graph_config.types import EdgeSpec, GraphConfigError


def parse_edge(item: Any, *, index: int) -> EdgeSpec:
    if isinstance(item, (list, tuple)) and len(item) == 2:
        return EdgeSpec(
            source=str(item[0]).strip(),
            target=str(item[1]).strip(),
        )
    if not isinstance(item, Mapping):
        raise GraphConfigError(
            f"pipeline.edges[{index}] must be [from, to] or object"
        )
    source = str(item.get("from", item.get("source", ""))).strip()
    target = str(item.get("to", item.get("target", ""))).strip()
    if not source or not target:
        raise GraphConfigError(f"pipeline.edges[{index}] requires from/to")
    for field in ("max_executions", "max", "loop"):
        if field in item:
            raise GraphConfigError(
                f"pipeline.edges[{index}].{field} is removed; "
                "use when/max_steps"
            )
    when = str(item.get("when", "")).strip()
    if when:
        _validate_when_expression(
            when,
            field=f"pipeline.edges[{index}].when",
        )
    schedule = _edge_role(item, "schedule", index=index)
    transfer = _edge_role(item, "transfer", index=index)
    if schedule is False and transfer is False:
        raise GraphConfigError(
            f"pipeline.edges[{index}] must schedule, transfer, or both"
        )
    return EdgeSpec(
        source=source,
        target=target,
        when=when,
        schedule=schedule,
        transfer=transfer,
    )


def _edge_role(
    item: Mapping[str, Any],
    role: str,
    *,
    index: int,
) -> bool | None:
    value = item.get(role)
    if role in item and not isinstance(value, bool):
        raise GraphConfigError(
            f"pipeline.edges[{index}].{role} must be a boolean"
        )
    return value if isinstance(value, bool) else None


def _validate_when_expression(value: str, *, field: str) -> None:
    operators = [operator for operator in ("==", "!=") if operator in value]
    if len(operators) != 1:
        raise GraphConfigError(f"{field} must use == or !=")
    left, right = (
        part.strip() for part in value.split(operators[0], 1)
    )
    if not left or not right:
        raise GraphConfigError(f"{field} must compare a key to a literal")
    if right in {"true", "false"}:
        return
    if (
        len(right) >= 2
        and right[0] == right[-1]
        and right[0] in {"'", '"'}
    ):
        return
    raise GraphConfigError(
        f"{field} literal must be true, false, or quoted string"
    )


__all__ = ["parse_edge"]
