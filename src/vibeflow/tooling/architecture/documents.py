from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Mapping

from vibeflow.core.findings import HealthFinding
from vibeflow.tooling.project.config_loader import ConfigLoadError, load_raw_config_document
from vibeflow.tooling.project.document_kinds import ARCHITECTURE_DOCUMENT_HEADER


_SOURCE_ERROR_RULES = frozenset(
    {
        "ARCHITECTURE.DOCUMENT.READ",
        "ARCHITECTURE.DOCUMENT.JSONC",
    }
)
_MAX_DIFFERENCE_PATHS = 50
_LOAD_STATES = frozenset({"loaded", "not_loaded", "unknown"})
_LOAD_STATE_OBSERVATION = object()


def check_architecture_document(
    document_path: Path,
    *,
    expected_payload: Mapping[str, object],
    expected_text: str,
    workflow_path: Path,
    project_config_path: Path | None = None,
    workspace_path: Path | None = None,
    registration_field: str = "",
) -> HealthFinding | None:
    document_path = document_path.resolve()
    workflow_path = workflow_path.resolve()
    command = architecture_regenerate_command(
        workflow_path,
        document_path,
        workspace_path=workspace_path,
    )
    details = _finding_details(
        document_path=document_path,
        workflow_path=workflow_path,
        project_config_path=project_config_path,
        registration_field=registration_field,
        command=command,
        expected_payload=expected_payload,
    )
    try:
        actual_text = document_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _finding(
            "ARCHITECTURE.DOCUMENT.MISSING",
            document_path,
            f"architecture document is missing: {document_path}; regenerate it with: {command}",
            details=_difference_details(details, "$"),
        )
    except OSError as exc:
        return _finding(
            "ARCHITECTURE.DOCUMENT.READ",
            document_path,
            f"cannot read architecture document {document_path}: {exc}; regenerate it with: {command}",
            details=_difference_details({**details, "read_error": str(exc)}, "$"),
        )

    if not actual_text.startswith(ARCHITECTURE_DOCUMENT_HEADER):
        return _finding(
            "ARCHITECTURE.DOCUMENT.HEADER",
            document_path,
            f"architecture document has a missing or modified generated-file header: {document_path}; regenerate it with: {command}",
            details=_difference_details(details, "$.__header__"),
        )

    try:
        actual_payload = load_raw_config_document(document_path).data
    except ConfigLoadError as exc:
        source_location = dict(exc.source_location)
        source_location.setdefault("path", str(document_path))
        return _finding(
            "ARCHITECTURE.DOCUMENT.JSONC",
            document_path,
            f"architecture document is not valid JSONC: {document_path}: {exc.message}; regenerate it with: {command}",
            details=_difference_details({**details, "parse_error": exc.message}, "$"),
            source_location=source_location,
        )

    expected_structure = _structural_payload(expected_payload)
    actual_structure = _structural_payload(actual_payload)
    if actual_structure != expected_structure:
        difference_paths, difference_count = _difference_paths(expected_structure, actual_structure)
        return _finding(
            "ARCHITECTURE.DOCUMENT.STALE",
            document_path,
            f"architecture document is out of date for workflow {workflow_path}: {document_path}; regenerate it with: {command}",
            details={
                **details,
                "difference_count": difference_count,
                "difference_paths": difference_paths,
                "differences_truncated": difference_count > len(difference_paths),
            },
        )

    if actual_text != render_architecture_payload(actual_payload):
        return _finding(
            "ARCHITECTURE.DOCUMENT.NON_CANONICAL",
            document_path,
            f"architecture document content is current but its generated formatting was modified: {document_path}; regenerate it with: {command}",
            details=_difference_details(details, "$.__canonical_text__"),
        )
    return None


def _structural_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    """Source load state describes this observation, not architecture freshness."""
    implementation = payload.get("implementation_graph")
    if not isinstance(implementation, Mapping):
        return payload
    graph = dict(implementation)
    files = graph.get("files")
    if isinstance(files, Mapping):
        graph["files"] = {key: _source_observation(value) for key, value in files.items()}
    resources = graph.get("resources")
    if isinstance(resources, Mapping):
        records = {}
        for key, value in resources.items():
            record = dict(value) if isinstance(value, Mapping) else value
            if isinstance(record, Mapping) and isinstance(record.get("sources"), (list, tuple)):
                record["sources"] = [_source_observation(item) for item in record["sources"]]
            records[key] = record
        graph["resources"] = records
    return {**payload, "implementation_graph": graph}


def _source_observation(value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    record = dict(value)
    state = record.get("load_state")
    if isinstance(state, str) and state in _LOAD_STATES:
        record["load_state"] = _LOAD_STATE_OBSERVATION
    return record



def architecture_regenerate_command(
    workflow_path: Path,
    document_path: Path,
    *,
    workspace_path: Path | None = None,
) -> str:
    workflow_path = workflow_path.resolve()
    document_path = document_path.resolve()
    workspace = workspace_path.resolve() if workspace_path is not None else None
    base = workspace.parent if workspace is not None else Path.cwd().resolve()
    workflow_arg = _portable_cli_path(workflow_path, base=base)
    document_arg = _portable_cli_path(document_path, base=base)
    run_wrapper = base / "run.py"
    if workspace is not None and run_wrapper.is_file():
        args = ("python", "run.py", "architecture", "--config", workflow_arg, "--output", document_arg)
    else:
        args = ["python", "-m", "vibeflow", "export-architecture"]
        if workspace is not None:
            args.extend(("--workspace", _portable_cli_path(workspace, base=base)))
        args.extend(("--config", workflow_arg, "--output", document_arg))
    return " ".join(shlex.quote(str(value)) for value in args)


def architecture_finding_status(finding: HealthFinding) -> str:
    return "ERROR" if finding.rule_id in _SOURCE_ERROR_RULES else "FAIL"


def _finding(
    rule_id: str,
    document_path: Path,
    message: str,
    *,
    details: Mapping[str, object],
    source_location: Mapping[str, object] | None = None,
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type="architecture_document",
        object_id=str(document_path),
        source_location=dict(source_location or {"path": str(document_path)}),
        failure_layer="syntax" if rule_id == "ARCHITECTURE.DOCUMENT.JSONC" else "source" if rule_id == "ARCHITECTURE.DOCUMENT.READ" else "topology",
        message=message,
        suggested_fix_type="regenerate_architecture",
        details=dict(details),
    )


def _finding_details(
    *,
    document_path: Path,
    workflow_path: Path,
    project_config_path: Path | None,
    registration_field: str,
    command: str,
    expected_payload: Mapping[str, object],
) -> dict[str, object]:
    details: dict[str, object] = {
        "document_path": str(document_path),
        "workflow_path": str(workflow_path),
        "regenerate_command": command,
        "source_paths": _source_paths(expected_payload),
    }
    if project_config_path is not None:
        details["project_config_path"] = str(project_config_path.resolve())
    if registration_field:
        details["registration_field"] = registration_field
    return details


def _source_paths(payload: object) -> list[str]:
    found: set[str] = set()
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for key, value in current.items():
                if key in {"source", "source_path", "path"} and isinstance(value, str) and value:
                    found.add(value)
                elif isinstance(value, (Mapping, list, tuple)):
                    stack.append(value)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
    return sorted(found)


def _difference_details(details: Mapping[str, object], *paths: str) -> dict[str, object]:
    return {
        **details,
        "difference_count": len(paths),
        "difference_paths": list(paths),
        "differences_truncated": False,
    }


def _difference_paths(expected: object, actual: object) -> tuple[list[str], int]:
    paths: list[str] = []
    count = 0
    stack: list[tuple[str, object, object]] = [("$", expected, actual)]
    while stack:
        path, left, right = stack.pop()
        if type(left) is not type(right):
            count += 1
            if len(paths) < _MAX_DIFFERENCE_PATHS:
                paths.append(path)
            continue
        if isinstance(left, Mapping):
            left_keys = set(left)
            right_keys = set(right)
            for key in sorted(left_keys | right_keys, reverse=True):
                child = f"{path}.{key}"
                if key not in left_keys or key not in right_keys:
                    count += 1
                    if len(paths) < _MAX_DIFFERENCE_PATHS:
                        paths.append(child)
                else:
                    stack.append((child, left[key], right[key]))
            continue
        if isinstance(left, (list, tuple)):
            common = min(len(left), len(right))
            if len(left) != len(right):
                count += abs(len(left) - len(right))
                for index in range(common, max(len(left), len(right))):
                    if len(paths) < _MAX_DIFFERENCE_PATHS:
                        paths.append(f"{path}[{index}]")
            for index in range(common - 1, -1, -1):
                stack.append((f"{path}[{index}]", left[index], right[index]))
            continue
        if left != right:
            count += 1
            if len(paths) < _MAX_DIFFERENCE_PATHS:
                paths.append(path)
    return paths, count


def _portable_cli_path(path: Path, *, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)


def render_architecture_payload(payload):
    return ARCHITECTURE_DOCUMENT_HEADER + json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def parse_architecture_text(text, *, project_target=None):
    if not text.startswith(ARCHITECTURE_DOCUMENT_HEADER):
        raise ValueError("generated Architecture document has no VibeFlow header")
    payload=json.loads(text[len(ARCHITECTURE_DOCUMENT_HEADER):])
    if not isinstance(payload, Mapping) or project_target is not None and payload.get("project_target") != project_target:
        raise ValueError("generated Architecture document has an invalid target")
    return payload



