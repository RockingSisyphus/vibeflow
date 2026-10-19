"""Display-only project relationships. No scheduling or compilation effects."""
from pathlib import PurePosixPath
from posixpath import normpath
from typing import Mapping

from .architecture_types import WorkspaceConfigError


def validate_preview_options(value, *, path):
    def fail(message):
        raise WorkspaceConfigError("WORKSPACE.PREVIEW.INVALID", message, {"path": str(path), "field": "preview"})
    if not isinstance(value, Mapping) or set(value) - {"workflow_links"}:
        fail("preview must be an object containing only workflow_links")
    links = value.get("workflow_links", [])
    if not isinstance(links, list):
        fail("preview.workflow_links must be a list")
    required = {"from_workflow", "to_root", "to_workflow", "kind"}
    allowed = required | {"from_call_path", "label"}
    for index, link in enumerate(links):
        if not isinstance(link, Mapping) or not required <= set(link) or set(link) - allowed:
            fail(f"workflow_links[{index}] requires {sorted(required)}; allowed fields: {sorted(allowed)}")
        if any(not isinstance(v, str) or not v.strip() for v in link.values()):
            fail(f"workflow_links[{index}] fields must be non-empty strings")
        if link["kind"] not in {"call", "reference"}:
            fail(f"workflow_links[{index}].kind must be call or reference")
        for key in ("from_workflow", "to_workflow"):
            candidate = PurePosixPath(link[key])
            normalized = normpath(link[key])
            if candidate.is_absolute() or normalized == ".." or normalized.startswith("../") or "\\" in link[key]:
                fail(f"workflow_links[{index}].{key} must be a path relative to its root")
