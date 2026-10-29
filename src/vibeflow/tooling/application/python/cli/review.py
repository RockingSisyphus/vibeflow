from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping


def add_review_parser(subparsers: argparse._SubParsersAction) -> None:
    review = subparsers.add_parser(
        "review",
        help="refresh registered architecture, validate it, and publish offline preview data",
    )
    review.add_argument("--workspace", required=True, help="workspace vibeflow_config.jsonc path")
    review.add_argument("--config", required=True, help="registered executable workflow config path")
    review.add_argument("--preview-root", help="override offline preview directory")


def handle_review(args: argparse.Namespace) -> int:
    runner = _ReviewRunner(
        workspace_path=Path(args.workspace).resolve(),
        config_path=Path(args.config).resolve(),
        preview_root=getattr(args, "preview_root", None),
    )
    return_code = runner.run()
    _print_result(runner.result)
    return return_code


class _ReviewRunner:
    def __init__(self, *, workspace_path: Path, config_path: Path, preview_root=None) -> None:
        self.workspace_path = workspace_path
        self.config_path = config_path
        self.preview_root = preview_root
        self.result = _review_result(config_path=config_path)
        self.preparation = None
        self.governance = None
        self.workspace = None
        self.root = None
        self.spec = None
        self.graph = None
        self.compiled = None
        self.registry = None
        self.resources = None
        self.health = None
        self.presentation = None
        self.validation_status = "ERROR"

    def run(self) -> int:
        stages = (
            self._load_workspace,
            self._locate_architecture,
            self._preflight,
            self._regenerate_architecture,
            self._validate,
            self._publish_preview,
        )
        for stage in stages:
            if not stage():
                return 1
        self.result.update(status=self.validation_status, failed_stage=None, published=True)
        return 0

    def _load_workspace(self) -> bool:
        from vibeflow.core.findings import HealthFinding
        from vibeflow.tooling.application.python.workspace_service import WorkspaceConfigError, load_workspace_config

        try:
            self.workspace = load_workspace_config(self.workspace_path)
            selected_root = self.workspace.root_for_path(self.config_path)
            if selected_root is not None and selected_root.project_target != "python":
                raise WorkspaceConfigError("CLI.PROJECT_TARGET.MISMATCH",
                    f"Python review requires project_target='python'; root '{selected_root.id}' declares '{selected_root.project_target}'",
                    {"path": str(self.config_path)})
            from vibeflow.tooling.project.preparation import ProjectPreparation
            self.preparation = ProjectPreparation(self.workspace)
            self.governance = self.preparation.review(write_architecture=True)
            self.result["project_architecture"] = str(self.governance.architecture_path)
        except WorkspaceConfigError as exc:
            finding = HealthFinding(
                rule_id=exc.rule_id,
                severity="error",
                object_type="workspace",
                object_id=str(self.workspace_path),
                source_location=dict(exc.source_location),
                failure_layer=exc.failure_layer,
                message=exc.message,
                suggested_fix_type="fix_config",
            )
            self._fail_finding("workspace", "ERROR", finding)
            return False
        except Exception as exc:
            finding = _review_finding(
                "WORKSPACE.LOAD",
                f"could not load workspace {self.workspace_path}: {exc}",
                object_type="workspace",
                object_id=str(self.workspace_path),
                failure_layer="workspace",
            )
            self._fail_finding("workspace", "ERROR", finding)
            return False
        return True

    def _locate_architecture(self) -> bool:
        self.root = self.workspace.root_for_path(self.config_path)
        if self.root is None:
            finding = _review_finding(
                "WORKSPACE.CONFIG.OUTSIDE_ROOT",
                f"config is not under any workspace root: {self.config_path}",
                object_type="config",
                object_id=str(self.config_path),
                failure_layer="workspace",
            )
            self._fail_finding("workspace", "ERROR", finding)
            return False
        self.spec = next(
            (
                item
                for item in self.root.architecture_documents
                if item.workflow_path.resolve() == self.config_path
            ),
            None,
        )
        if self.spec is None:
            finding = _review_finding(
                "REVIEW.ARCHITECTURE.UNREGISTERED",
                f"workflow is not registered in {self.root.config_path} architecture.documents: {self.config_path}",
                object_type="workflow",
                object_id=str(self.config_path),
                failure_layer="topology",
                details={"project_config_path": str(self.root.config_path.resolve())},
            )
            self._fail_finding("architecture", "FAIL", finding)
            return False
        self.result["architecture"] = str(self.spec.document_path.resolve())
        return True


    def _preflight(self) -> bool:
        from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export

        try:
            loaded = load_workspace_graph_for_export(
                self.config_path,
                workspace=self.workspace,
                validate_health=True,
                _include_presentation=True,
                preparation=self.preparation, governance=self.governance,
            )
        except Exception as exc:
            finding = _review_finding(
                "REVIEW.PREFLIGHT",
                f"could not complete workflow graph/schema/health preflight: {exc}",
                object_type="workflow",
                object_id=str(self.config_path),
                failure_layer="topology",
            )
            self._fail_finding("preflight", "ERROR", finding)
            return False
        self.graph, self.compiled, self.registry, self.resources, report, self.health, self.presentation = loaded
        if report is not None:
            self._fail_report("preflight", report)
            return False
        return True

    def _regenerate_architecture(self) -> bool:
        from vibeflow.tooling.architecture.documents import architecture_finding_status, check_architecture_document
        from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_document, render_architecture_payload

        try:
            payload = build_architecture_document(
                self.graph,
                compiled=self.compiled,
                registry=self.registry,
                resources=self.resources,
                prepared=self.presentation,
            )
            text = render_architecture_payload(payload)
            self.spec.document_path.parent.mkdir(parents=True, exist_ok=True)
            from vibeflow.tooling.file_io import atomic_write
            atomic_write(self.spec.document_path, text)
            self.preparation.publish_architecture()
            finding = check_architecture_document(
                self.spec.document_path,
                expected_payload=payload,
                expected_text=text,
                workflow_path=self.spec.workflow_path,
                project_config_path=self.root.config_path,
                workspace_path=self.workspace.path,
                registration_field=self.spec.registration_field,
            )
        except Exception as exc:
            finding = _review_finding(
                "REVIEW.ARCHITECTURE.WRITE",
                f"could not regenerate registered architecture document {self.spec.document_path}: {exc}",
                object_type="architecture_document",
                object_id=str(self.spec.document_path),
                failure_layer="source",
            )
            self._fail_finding("architecture", "ERROR", finding)
            return False
        if finding is not None:
            self._fail_finding("architecture", architecture_finding_status(finding), finding)
            return False
        return True

    def _validate(self) -> bool:
        from vibeflow.tooling.application.python.presentation.architecture_validation import _validate_registered_architecture_document

        try:
            validation = _validate_registered_architecture_document(
                self.health,
                document_path=self.config_path,
                graph=self.graph,
                compiled=self.compiled,
                registry=self.registry,
                resources=self.resources,
                workspace=self.workspace,
                prepared=self.presentation,
            )
        except Exception as exc:
            finding = _review_finding(
                "REVIEW.VALIDATION",
                f"could not complete formal workspace validation: {exc}",
                object_type="workflow",
                object_id=str(self.config_path),
                failure_layer="topology",
            )
            self._fail_finding("validation", "ERROR", finding)
            return False
        self.result["validation"] = validation.to_dict()
        self.validation_status = validation.status
        if validation.status in {"FAIL", "ERROR"}:
            self._fail_report("validation", validation)
            return False
        return True


    def _publish_preview(self) -> bool:
        from vibeflow.tooling.application.python.presentation.preview import python_preview
        try:
            record = python_preview(self.presentation, config=self.config_path, workspace=self.workspace,
                                    preview_root=self.preview_root, category="review", status="passed", check_status=self.validation_status)
            self.result["preview"] = str(record.root / "vibeflow-preview.html")
            self.result["output"] = self.result["preview"]
            self.result["preview_id"] = record.metadata["id"]
            return True
        except Exception as exc:
            self._fail_finding("preview", "FAIL", _review_finding("REVIEW.PREVIEW.WRITE", str(exc),
                object_type="preview", object_id=str(self.preview_root or self.workspace.root), failure_layer="render"))
            return False


    def _fail_report(self, stage: str, report: object) -> None:
        self.result["validation"] = report.to_dict()
        self.result.update(status=report.status, failed_stage=stage, published=False)
        if report.errors:
            self.result["error"] = report.errors[0].to_dict()

    def _fail_finding(self, stage: str, status: str, finding: object) -> None:
        self.result.update(
            status=status,
            failed_stage=stage,
            published=False,
            error=finding.to_dict(),
        )


def _review_result(*, config_path: Path) -> dict[str, object]:
    return {
        "status": "ERROR", "failed_stage": None,
        "config": str(config_path),
        "architecture": None, "validation": None,
        "published": False,
    }


def _review_finding(
    rule_id: str, message: str,
    *,
    object_type: str, object_id: str, failure_layer: str,
    details: Mapping[str, object] | None = None,
):
    from vibeflow.core.findings import HealthFinding

    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type=object_type,
        object_id=object_id,
        source_location={"path": object_id},
        failure_layer=failure_layer,
        message=message,
        suggested_fix_type="fix_config",
        details=dict(details or {}),
    )


def _print_result(result: Mapping[str, object]) -> None:
    from vibeflow.tooling.application.result_scope import add_result_scope

    status = str(result.get("status", "ERROR"))
    payload = add_result_scope(
        result,
        "vibeflow_review_artifact",
        checked_ids=None
        if status in {"PASS", "CONCERNS"} and bool(result.get("published"))
        else (),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
