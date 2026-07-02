from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuntimeTrace:
    exec_order: list[str] = field(default_factory=list)
    edge_executions: dict[str, int] = field(default_factory=dict)
    step_count: int = 0
    node_runs: dict[str, int] = field(default_factory=dict)
    stop_reason: str = ""
    current_node: str = ""
    exception: str = ""
    events: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "exec_order": tuple(self.exec_order),
            "edge_executions": dict(self.edge_executions),
            "step_count": self.step_count,
            "node_runs": dict(self.node_runs),
            "stop_reason": self.stop_reason,
            "current_node": self.current_node,
            "exception": self.exception,
            "events": [dict(event) for event in self.events],
        }
