from __future__ import annotations

import argparse
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Mapping


_REVIEW_LAYOUT = "flowchart-review-columns"
_REVIEW_FRAGMENT_CLASS = "review-inline-fragment"


def add_review_parser(subparsers: argparse._SubParsersAction) -> None:
    review = subparsers.add_parser(
        "review",
        help="refresh registered architecture, validate it, and publish a canonical expanded review SVG",
    )
    review.add_argument("--workspace", required=True, help="workspace vibeflow_config.jsonc path")
    review.add_argument("--config", required=True, help="registered executable workflow config path")
    review.add_argument("--output", required=True, help="canonical expanded review SVG output path")


def handle_review(args: argparse.Namespace) -> int:
    runner = _ReviewRunner(
        workspace_path=Path(args.workspace).resolve(),
        config_path=Path(args.config).resolve(),
        output_path=Path(args.output).resolve(),
    )
    return_code = runner.run()
    _print_result(runner.result)
    return return_code


class _ReviewRunner:
    def __init__(self, *, workspace_path: Path, config_path: Path, output_path: Path) -> None:
        self.workspace_path = workspace_path
        self.config_path = config_path
        self.output_path = output_path
        self.result = _review_result(config_path=config_path, output_path=output_path)
        self.workspace = None
        self.root = None
        self.spec = None
        self.graph = None
        self.compiled = None
        self.registry = None
        self.resources = None
        self.validation_status = "ERROR"
        self.temporary_path: Path | None = None

    def run(self) -> int:
        stages = (
            self._load_workspace,
            self._locate_architecture,
            self._check_output_conflict,
            self._preflight,
            self._regenerate_architecture,
            self._validate,
            self._render_and_publish,
        )
        for stage in stages:
            if not stage():
                return 1
        self.result.update(status=self.validation_status, failed_stage=None, published=True)
        return 0

    def _load_workspace(self) -> bool:
        from vibeflow.health.types import HealthFinding
        from vibeflow.workspace import WorkspaceConfigError, load_workspace_config

        try:
            self.workspace = load_workspace_config(self.workspace_path)
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

    def _check_output_conflict(self) -> bool:
        protected_paths = {
            self.workspace_path,
            self.config_path,
            self.spec.document_path.resolve(),
        }
        if self.output_path not in protected_paths:
            return True
        finding = _review_finding(
            "REVIEW.OUTPUT.CONFLICT",
            f"review SVG output must not overwrite workspace, workflow, or architecture source: {self.output_path}",
            object_type="svg",
            object_id=str(self.output_path),
            failure_layer="source",
            details={"protected_paths": [str(path) for path in sorted(protected_paths)]},
        )
        self._fail_finding("output", "FAIL", finding)
        return False

    def _preflight(self) -> bool:
        from vibeflow.workspace import load_workspace_graph_for_export

        try:
            loaded = load_workspace_graph_for_export(
                self.config_path,
                workspace=self.workspace,
                validate_health=True,
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
        self.graph, self.compiled, self.registry, self.resources, report = loaded
        if report is not None:
            self._fail_report("preflight", report)
            return False
        return True

    def _regenerate_architecture(self) -> bool:
        from vibeflow.architecture_validation import architecture_finding_status, check_architecture_document
        from vibeflow.rendering.architecture_document import build_architecture_document, render_architecture_payload

        try:
            payload = build_architecture_document(
                self.graph,
                compiled=self.compiled,
                registry=self.registry,
                resources=self.resources,
            )
            text = render_architecture_payload(payload)
            self.spec.document_path.parent.mkdir(parents=True, exist_ok=True)
            self.spec.document_path.write_text(text, encoding="utf-8")
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
        from vibeflow.workspace import validate_workspace_config_path

        try:
            validation = validate_workspace_config_path(
                self.config_path,
                workspace=self.workspace,
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

    def _render_and_publish(self) -> bool:
        if not self._create_temporary_output():
            return False
        try:
            stages = (self._render_temporary_output, self._check_temporary_output, self._publish_output)
            for stage in stages:
                if not stage():
                    return False
            return True
        finally:
            self._cleanup_temporary_output()

    def _create_temporary_output(self) -> bool:
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                prefix=f".{self.output_path.name}.",
                suffix=".tmp",
                dir=self.output_path.parent,
                delete=False,
            ) as handle:
                self.temporary_path = Path(handle.name)
        except OSError as exc:
            finding = _review_finding(
                "REVIEW.SVG.TEMPORARY_OUTPUT",
                f"could not create temporary SVG output beside {self.output_path}: {exc}",
                object_type="svg",
                object_id=str(self.output_path),
                failure_layer="source",
            )
            self._fail_finding("svg", "ERROR", finding)
            return False
        return True

    def _render_temporary_output(self) -> bool:
        try:
            _render_canonical_review_svg(
                self.graph,
                self.compiled,
                self.temporary_path,
                registry=self.registry,
                resources=self.resources,
            )
        except Exception as exc:
            finding = _review_finding(
                "REVIEW.SVG.RENDER",
                f"could not render canonical expanded review SVG: {exc}",
                object_type="svg",
                object_id=str(self.output_path),
                failure_layer="render",
            )
            self._fail_finding("svg", "FAIL", finding)
            return False
        return True

    def _check_temporary_output(self) -> bool:
        finding = _check_canonical_review_svg(self.temporary_path, output_path=self.output_path)
        if finding is None:
            return True
        self._fail_finding("svg_check", "FAIL", finding)
        return False

    def _publish_output(self) -> bool:
        try:
            os.replace(self.temporary_path, self.output_path)
            self.temporary_path = None
        except OSError as exc:
            finding = _review_finding(
                "REVIEW.SVG.PUBLISH",
                f"could not publish canonical expanded review SVG to {self.output_path}: {exc}",
                object_type="svg",
                object_id=str(self.output_path),
                failure_layer="source",
            )
            self._fail_finding("publish", "ERROR", finding)
            return False
        return True

    def _cleanup_temporary_output(self) -> None:
        if self.temporary_path is None:
            return
        try:
            self.temporary_path.unlink(missing_ok=True)
        except OSError:
            pass

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


def _render_canonical_review_svg(
    graph: object, compiled: object, output_path: Path,
    *,
    registry: object, resources: object,
) -> None:
    from vibeflow.rendering.mermaid.render import (
        EXPANDED_MERMAID_MAX_EDGES,
        EXPANDED_MERMAID_MAX_TEXT_SIZE,
    )
    from vibeflow.rendering.mermaid.review_svg import render_review_columns_svg

    render_review_columns_svg(
        graph,
        compiled,
        output_path,
        registry=registry,
        resources=resources,
        expand_nodesets=True,
        show_contract=True,
        show_semantics=True,
        theme="default",
        background="transparent",
        max_text_size=EXPANDED_MERMAID_MAX_TEXT_SIZE,
        max_edges=EXPANDED_MERMAID_MAX_EDGES,
    )


def _check_canonical_review_svg(path: Path, *, output_path: Path):
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        return _review_finding(
            "REVIEW.SVG.XML",
            f"rendered review output is not readable SVG XML: {exc}",
            object_type="svg",
            object_id=str(output_path),
            failure_layer="render",
        )
    if _xml_local_name(root.tag) != "svg":
        return _review_finding(
            "REVIEW.SVG.ROOT",
            "rendered review output root element is not <svg>",
            object_type="svg",
            object_id=str(output_path),
            failure_layer="render",
        )
    if root.attrib.get("aria-roledescription") != _REVIEW_LAYOUT:
        return _review_finding(
            "REVIEW.SVG.LAYOUT",
            f"rendered review output is missing aria-roledescription={_REVIEW_LAYOUT!r}",
            object_type="svg",
            object_id=str(output_path),
            failure_layer="render",
        )
    fragments = [
        element
        for element in root.iter()
        if _xml_local_name(element.tag) == "g"
        and _REVIEW_FRAGMENT_CLASS in element.attrib.get("class", "").split()
    ]
    if not any(len(list(fragment)) > 0 for fragment in fragments):
        return _review_finding(
            "REVIEW.SVG.FRAGMENT",
            f"rendered review output has no non-empty {_REVIEW_FRAGMENT_CLASS} group",
            object_type="svg",
            object_id=str(output_path),
            failure_layer="render",
        )
    return None


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _review_result(*, config_path: Path, output_path: Path) -> dict[str, object]:
    return {
        "status": "ERROR", "failed_stage": None,
        "config": str(config_path),
        "architecture": None, "validation": None,
        "svg": str(output_path), "published": False,
    }


def _review_finding(
    rule_id: str, message: str,
    *,
    object_type: str, object_id: str, failure_layer: str,
    details: Mapping[str, object] | None = None,
):
    from vibeflow.health.types import HealthFinding

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
    print(json.dumps(dict(result), ensure_ascii=False, indent=2))
