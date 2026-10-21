"""Resource ownership, independent of workflow selection and implementation IO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceOwner:
    kind: str
    id: str
    root_id: str = ""
    path: str = ""

    def __post_init__(self):
        if self.kind not in {"project", "root", "plugin"}:
            raise ValueError("resource owner kind must be project, root or plugin")
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("resource owner id must be a non-empty string")
        if not isinstance(self.root_id, str) or not isinstance(self.path, str):
            raise ValueError("resource owner root_id and path must be strings")

    @property
    def plugin_id(self):
        return self.id if self.kind == "plugin" else ""

    def to_dict(self):
        return {"kind": self.kind, "id": self.id, "root_id": self.root_id, "path": self.path}
