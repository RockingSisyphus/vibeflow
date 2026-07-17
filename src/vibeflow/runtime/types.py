from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping

from vibeflow.data_contract import DataEnvelope, RunResult
from vibeflow.runtime.errors import PipelineRuntimeError
from vibeflow.runtime.trace import RuntimeTrace

@dataclass
class _RuntimeState:
    inboxes: dict[str, list[DataEnvelope]]
    result: RunResult = field(default_factory=RunResult)
    output_candidates: dict[str, list[DataEnvelope]] = field(default_factory=lambda: defaultdict(list))
    last_inputs: dict[str, dict[str, object]] = field(default_factory=dict)
    active_edges: set[tuple[str, str]] = field(default_factory=set)

@dataclass(frozen=True)
class _AsyncOutputs:
    outputs: Mapping[str, object]
    child_trace: RuntimeTrace | None = None

class _NestedRuntimeFailure(PipelineRuntimeError):
    def __init__(self, message: str, child_trace: RuntimeTrace) -> None:
        super().__init__(message)
        self.child_trace = child_trace
