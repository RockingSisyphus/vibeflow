from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

from vibeflow.config.path_utils import is_relative_to
from vibeflow.workspace.architecture_types import ArchitectureDocumentSpec, WorkspaceConfigError


def project_architecture_documents(
    data: Mapping[str, Any],
    *,
    root_path: Path,
    path: Path,
) -> tuple[ArchitectureDocumentSpec, ...]:
    raw_documents = _architecture_document_items(data, path=path)
    if raw_documents is None:
        return ()
    specs: list[ArchitectureDocumentSpec] = []
    workflow_fields: dict[Path, str] = {}
    document_fields: dict[Path, str] = {}
    for index, raw_spec in enumerate(raw_documents):
        spec = _architecture_document_spec(raw_spec, index=index, root_path=root_path, path=path)
        _register_architecture_document(
            spec,
            workflow_fields=workflow_fields,
            document_fields=document_fields,
            path=path,
        )
        specs.append(spec)
    return tuple(specs)


def _architecture_document_items(data: Mapping[str, Any], *, path: Path) -> list[object] | None:
    if "architecture" not in data:
        return None
    raw_architecture = data["architecture"]
    if not isinstance(raw_architecture, Mapping):
        raise _architecture_config_error(
            path,
            "architecture",
            "must be an object containing a non-empty 'documents' list",
        )
    unknown = set(raw_architecture) - {"documents"}
    if unknown:
        raise _architecture_config_error(
            path,
            "architecture",
            f"contains unknown fields {sorted(unknown)}; only 'documents' is allowed",
        )
    raw_documents = raw_architecture.get("documents")
    if not isinstance(raw_documents, list) or not raw_documents:
        raise _architecture_config_error(
            path,
            "architecture.documents",
            "must be a non-empty list of {'workflow': '...', 'document': '...'} objects",
        )
    return raw_documents


def _architecture_document_spec(
    raw_spec: object,
    *,
    index: int,
    root_path: Path,
    path: Path,
) -> ArchitectureDocumentSpec:
    registration_field = f"architecture.documents[{index}]"
    if not isinstance(raw_spec, Mapping):
        raise _architecture_config_error(
            path,
            registration_field,
            "must be an object with exactly 'workflow' and 'document' fields",
        )
    unknown = set(raw_spec) - {"workflow", "document"}
    if unknown:
        raise _architecture_config_error(
            path,
            registration_field,
            f"contains unknown fields {sorted(unknown)}; only 'workflow' and 'document' are allowed",
        )
    missing = {"workflow", "document"} - set(raw_spec)
    if missing:
        raise _architecture_config_error(
            path,
            registration_field,
            f"is missing required fields {sorted(missing)}; add root-relative .jsonc paths",
        )
    workflow, workflow_path = _architecture_relative_jsonc_path(
        raw_spec["workflow"],
        field=f"{registration_field}.workflow",
        root_path=root_path,
        config_path=path,
    )
    document, document_path = _architecture_relative_jsonc_path(
        raw_spec["document"],
        field=f"{registration_field}.document",
        root_path=root_path,
        config_path=path,
    )
    if workflow_path == document_path:
        raise _architecture_config_error(
            path,
            registration_field,
            "must use different paths for 'workflow' and 'document'; choose a separate generated document path",
            workflow=workflow,
            document=document,
        )
    if not workflow_path.is_file():
        raise _architecture_config_error(
            path,
            f"{registration_field}.workflow",
            f"must reference an existing workflow file under the root; create or correct '{workflow}'",
            workflow=workflow,
            resolved_path=str(workflow_path),
        )
    if document_path.exists() and not document_path.is_file():
        raise _architecture_config_error(
            path,
            f"{registration_field}.document",
            f"must reference a file path, but '{document}' is an existing directory",
            document=document,
            resolved_path=str(document_path),
        )
    return ArchitectureDocumentSpec(workflow, document, workflow_path, document_path, registration_field)


def _register_architecture_document(
    spec: ArchitectureDocumentSpec,
    *,
    workflow_fields: dict[Path, str],
    document_fields: dict[Path, str],
    path: Path,
) -> None:
    field = spec.registration_field
    conflicts = (
        (
            spec.workflow_path,
            workflow_fields,
            f"{field}.workflow",
            "duplicates the workflow registered at {other}; keep only one mapping per workflow",
            "workflow",
            spec.workflow,
        ),
        (
            spec.workflow_path,
            document_fields,
            f"{field}.workflow",
            "is already used as the generated document at {other}; use separate source and output paths",
            "workflow",
            spec.workflow,
        ),
        (
            spec.document_path,
            document_fields,
            f"{field}.document",
            "duplicates the document registered at {other}; choose a unique document path",
            "document",
            spec.document,
        ),
        (
            spec.document_path,
            workflow_fields,
            f"{field}.document",
            "would overwrite the workflow registered at {other}; choose a separate generated document path",
            "document",
            spec.document,
        ),
    )
    for candidate, fields, error_field, message, detail_name, detail_value in conflicts:
        if candidate in fields:
            raise _architecture_config_error(
                path,
                error_field,
                message.format(other=fields[candidate]),
                **{detail_name: detail_value},
            )
    workflow_fields[spec.workflow_path] = f"{field}.workflow"
    document_fields[spec.document_path] = f"{field}.document"


def _architecture_relative_jsonc_path(
    value: object,
    *,
    field: str,
    root_path: Path,
    config_path: Path,
) -> tuple[str, Path]:
    if not isinstance(value, str) or not value.strip():
        raise _architecture_config_error(
            config_path,
            field,
            "must be a non-empty root-relative path ending in .jsonc",
        )
    relative = value.strip()
    candidate = Path(relative)
    if candidate.is_absolute() or PureWindowsPath(relative).is_absolute():
        raise _architecture_config_error(
            config_path,
            field,
            f"must be relative to root '{root_path}'; replace the absolute path '{relative}'",
            value=relative,
            root_path=str(root_path),
        )
    resolved = (root_path / candidate).resolve()
    if not is_relative_to(resolved, root_path):
        raise _architecture_config_error(
            config_path,
            field,
            f"must stay inside root '{root_path}'; remove '..' traversal from '{relative}'",
            value=relative,
            root_path=str(root_path),
            resolved_path=str(resolved),
        )
    if candidate.suffix != ".jsonc":
        raise _architecture_config_error(
            config_path,
            field,
            f"must end in .jsonc; change '{relative}' to a .jsonc path",
            value=relative,
        )
    normalized = resolved.relative_to(root_path).as_posix()
    return normalized, resolved


def _architecture_config_error(
    path: Path,
    field: str,
    problem: str,
    **details: object,
) -> WorkspaceConfigError:
    source_location: dict[str, object] = {
        "path": str(path),
        "project_config_path": str(path),
        "field": field,
    }
    source_location.update(details)
    return WorkspaceConfigError(
        "WORKSPACE.PROJECT_CONFIG.ARCHITECTURE",
        f"project config '{path}' field '{field}' {problem}",
        source_location,
    )
