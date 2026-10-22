"""Read-only identity shared by all Node contexts in one workflow invocation."""
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True)
class WorkflowIdentity:
    id: str = field(default_factory=lambda: uuid4().hex)

    def self(self):
        return {"id": self.id}
