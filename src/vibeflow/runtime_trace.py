from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import TextIO


class RuntimeTraceSink:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._handle: TextIO | None = None
        self._lock = Lock()
        self._closed = False

    def open(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("w", encoding="utf-8", buffering=1)
            self._closed = False

    def write_event(self, event: dict[str, object]) -> None:
        with self._lock:
            if self._closed:
                return
            if self._handle is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._handle = self.path.open("w", encoding="utf-8", buffering=1)
            self._handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def write_summary(self, trace: "RuntimeTrace") -> None:
        summary = trace.to_dict()
        summary["kind"] = "runtime_summary"
        self.write_event(summary)

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None
            self._closed = True


@dataclass
class RuntimeTrace:
    exec_order: list[str] = field(default_factory=list)
    edge_executions: dict[str, int] = field(default_factory=dict)
    step_count: int = 0
    node_runs: dict[str, int] = field(default_factory=dict)
    qualified_exec_order: list[str] = field(default_factory=list)
    qualified_edge_executions: dict[str, int] = field(default_factory=dict)
    qualified_node_runs: dict[str, int] = field(default_factory=dict)
    nested_step_count: int = 0
    stop_reason: str = ""
    current_node: str = ""
    exception: str = ""
    event_count: int = 0
    trace_path: str = ""
    events_streamed: bool = True

    def record_node_run(self, node_name: str, run_count: int) -> None:
        qualified = qualified_name((node_name,))
        self.node_runs[node_name] = run_count
        self.exec_order.append(node_name)
        self.qualified_node_runs[qualified] = run_count
        self.qualified_exec_order.append(qualified)

    def record_edge(self, source: str, target: str) -> None:
        key = f"{source}->{target}"
        self.edge_executions[key] = self.edge_executions.get(key, 0) + 1
        qualified_key = f"{qualified_name((source,))}->{qualified_name((target,))}"
        self.qualified_edge_executions[qualified_key] = self.qualified_edge_executions.get(qualified_key, 0) + 1

    def add_event(self, event: dict[str, object], path: tuple[str, ...], sink: RuntimeTraceSink | None = None) -> None:
        enriched = dict(event)
        enriched["path"] = list(path)
        enriched["qualified_node"] = qualified_name(path)
        enriched["depth"] = max(len(path) - 1, 0)
        self.event_count += 1
        if sink is not None:
            sink.write_event(enriched)

    def merge_child(self, parent_path: tuple[str, ...], child: "RuntimeTrace") -> None:
        for name in child.qualified_exec_order:
            self.qualified_exec_order.append(_join_qualified(parent_path, name))
        for name, count in child.qualified_node_runs.items():
            key = _join_qualified(parent_path, name)
            self.qualified_node_runs[key] = self.qualified_node_runs.get(key, 0) + count
        for edge, count in child.qualified_edge_executions.items():
            source, sep, target = edge.partition("->")
            if not sep:
                continue
            key = f"{_join_qualified(parent_path, source)}->{_join_qualified(parent_path, target)}"
            self.qualified_edge_executions[key] = self.qualified_edge_executions.get(key, 0) + count
        self.event_count += child.event_count
        self.nested_step_count += child.step_count + child.nested_step_count

    def to_dict(self) -> dict[str, object]:
        return {
            "exec_order": tuple(self.exec_order),
            "edge_executions": dict(self.edge_executions),
            "step_count": self.step_count,
            "node_runs": dict(self.node_runs),
            "qualified_exec_order": tuple(self.qualified_exec_order),
            "qualified_edge_executions": dict(self.qualified_edge_executions),
            "qualified_node_runs": dict(self.qualified_node_runs),
            "total_step_count": self.step_count + self.nested_step_count,
            "stop_reason": self.stop_reason,
            "current_node": self.current_node,
            "exception": self.exception,
            "event_count": self.event_count,
            "trace_path": self.trace_path,
            "events_streamed": self.events_streamed,
        }


def qualified_name(path: tuple[str, ...]) -> str:
    return ".".join(path)


def _join_qualified(parent_path: tuple[str, ...], child_name: str) -> str:
    if not child_name:
        return qualified_name(parent_path)
    if not parent_path:
        return child_name
    return f"{qualified_name(parent_path)}.{child_name}"
