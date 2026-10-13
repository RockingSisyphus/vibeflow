"""Python registry adapter for Core structural flow health rules."""

from __future__ import annotations

from vibeflow.targets.shared.quality_support.workflow_rules.flow import (
    append_flowchart_health as _append_core_flowchart_health,
)
from vibeflow.targets.shared.quality_support.workflow_rules.joins import append_join_policy_health
from vibeflow.targets.python.rules.graph.flow_data import (
    _append_nodeset_flow_health,
    append_data_contract_warnings,
)


def append_flowchart_health(
    graph,
    compiled,
    state,
    *,
    registry,
    owner: str = "pipeline",
    visited_nodesets: set[str] | None = None,
) -> None:
    if visited_nodesets is None:
        visited_nodesets = set()
    _append_core_flowchart_health(
        graph,
        compiled,
        state,
        owner=owner,
    )
    _append_nodeset_flow_health(
        graph,
        state,
        registry=registry,
        visited_nodesets=visited_nodesets,
    )

__all__ = [
    "append_data_contract_warnings",
    "append_flowchart_health",
    "append_join_policy_health",
]
