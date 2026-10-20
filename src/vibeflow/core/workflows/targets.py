"""Pure target declarations shared by configuration, startup and preview."""
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkflowTarget:
    workflow: str
    command: tuple[str, ...]
    root: str = ""
    entry: str = ""
    cwd: str = "."
    env: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self):
        return {"workflow": self.workflow, "command": list(self.command), "root": self.root,
                "entry": self.entry, "cwd": self.cwd, "env": dict(self.env)}


def parse_targets(value):
    if not isinstance(value, Mapping):
        raise ValueError("workflow_targets must be an object keyed by target alias")
    result = {}
    fields = {"workflow", "command", "root", "entry", "cwd", "env"}
    for alias, raw in value.items():
        location = f"workflow_targets.{alias}"
        if not isinstance(alias, str) or not alias.strip() or not isinstance(raw, Mapping) or set(raw) - fields:
            raise ValueError(f"{location} must be a target declaration with {sorted(fields)}")
        if not isinstance(raw.get("workflow"), str) or not raw["workflow"].strip():
            raise ValueError(f"{location}.workflow must name a workflow config")
        command = raw.get("command")
        if not isinstance(command, (tuple, list)) or not command or any(not isinstance(v, str) for v in command) or not command[0]:
            raise ValueError(f"{location}.command must be a non-empty argument array")
        for key in ("root", "entry", "cwd"):
            if key in raw and not isinstance(raw[key], str):
                raise ValueError(f"{location}.{key} must be a string")
        environment = raw.get("env", {})
        if not isinstance(environment, Mapping) or any(not isinstance(k, str) or not k or not isinstance(v, str) for k, v in environment.items()):
            raise ValueError(f"{location}.env must contain string names and values")
        result[alias] = WorkflowTarget(raw["workflow"], tuple(command), raw.get("root", ""),
            raw.get("entry", ""), raw.get("cwd", "."), dict(environment))
    return result
