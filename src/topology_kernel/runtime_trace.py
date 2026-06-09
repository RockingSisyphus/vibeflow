from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuntimeTrace:
    exec_order: list[str] = field(default_factory=list)
    edge_executions: dict[str, int] = field(default_factory=dict)
    loop_iterations: dict[str, int] = field(default_factory=dict)
    loop_stop_reasons: dict[str, str] = field(default_factory=dict)
    loop_orders: dict[str, tuple[str, ...]] = field(default_factory=dict)
    boundary_events: list[dict[str, object]] = field(default_factory=list)
    events: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "exec_order": tuple(self.exec_order),
            "edge_executions": dict(self.edge_executions),
            "loop_iterations": dict(self.loop_iterations),
            "loop_stop_reasons": dict(self.loop_stop_reasons),
            "loop_orders": {name: list(order) for name, order in self.loop_orders.items()},
            "boundary_events": [dict(event) for event in self.boundary_events],
            "events": [dict(event) for event in self.events],
        }
