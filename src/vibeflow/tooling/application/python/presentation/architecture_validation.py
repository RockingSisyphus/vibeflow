"""Python registration adapter for the shared architecture document checker."""
from dataclasses import replace
from pathlib import Path
from vibeflow.core.findings import HealthReport
from vibeflow.tooling.architecture.documents import check_architecture_document, architecture_finding_status


def _validate_registered_architecture_document(
    report: HealthReport,
    *,
    document_path: Path,
    graph: object,
    compiled: object,
    registry: object,
    resources: object,
    workspace: object,
    prepared=None,
) -> HealthReport:
    """Validate the generated document registered for one workflow, if any."""

    from vibeflow.tooling.application.python.presentation.architecture_document import (
        build_architecture_document,
        render_architecture_payload,
    )

    root = workspace.root_for_path(document_path)
    if root is None:
        return report
    resolved_document_path = document_path.resolve()
    spec = next(
        (
            item
            for item in root.architecture_documents
            if item.workflow_path.resolve() == resolved_document_path
        ),
        None,
    )
    if spec is None:
        return report
    expected_payload = build_architecture_document(
        graph,
        compiled=compiled,
        registry=registry,
        resources=resources,
        prepared=prepared,
    )
    expected_text = render_architecture_payload(expected_payload)
    finding = check_architecture_document(
        spec.document_path,
        expected_payload=expected_payload,
        expected_text=expected_text,
        workflow_path=spec.workflow_path,
        project_config_path=root.config_path,
        workspace_path=workspace.path,
        registration_field=spec.registration_field,
    )
    if finding is None:
        return report
    return replace(
        report,
        status=architecture_finding_status(finding),
        errors=(*report.errors, finding),
    )
