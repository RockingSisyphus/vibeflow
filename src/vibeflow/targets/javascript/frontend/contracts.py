"""Native JavaScript target contracts beside the canonical workflow plan."""
from dataclasses import dataclass

COMPLETIONS = frozenset({"immediate", "suspend"})
SCHEDULES = frozenset({"inline", "deferred", "detached"})
EXECUTORS = frozenset({"current", "event_loop", "thread"})
TARGETS = frozenset({"browser", "node"})
PROFILES = frozenset({"esm-module", "single-esm", "web-app"})


@dataclass(frozen=True)
class CapabilityRequirement:
    id: str
    operations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "operations": list(self.operations)}
