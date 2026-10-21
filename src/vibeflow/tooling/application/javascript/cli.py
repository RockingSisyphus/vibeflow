from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Mapping, Sequence
from xml.etree import ElementTree

from vibeflow.tooling.application.result_scope import add_result_scope, format_result_scope
from vibeflow.targets.javascript.build.driver_session import check_scope



def build_parser() -> argparse.ArgumentParser:
    """Create the JavaScript application parser without loading Python."""

    parser = argparse.ArgumentParser(prog="vibeflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_build_parser(subparsers)
    add_audit_parsers(subparsers)
    return parser


@check_scope
def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    from vibeflow.tooling.application.project_quality import handle_quality_check
    handlers = {
        "build": handle_build,
        "validate": handle_validate,
        "inspect-config": handle_inspect_config,
        "export-architecture": handle_export_architecture,
        "export-mermaid": handle_export_mermaid,
        "export-ascii": handle_export_ascii,
        "export-svg": handle_export_svg,
        "review": handle_review,
        "quality-check": handle_quality_check,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.error(f"unknown JavaScript command: {args.command}")
        return 2
    return handler(args)


def add_audit_parsers(subparsers: argparse._SubParsersAction) -> None:
    validate = subparsers.add_parser(
        "validate",
        help="validate a JavaScript workflow without selecting a runtime platform",
    )
    _add_audit_input(validate)
    validate.add_argument("--json", action="store_true")

    inspect = subparsers.add_parser(
        "inspect-config",
        help="inspect a target-neutral JavaScript workflow",
    )
    _add_audit_input(inspect)

    for name, help_text in (
        ("export-architecture", "export target-neutral Architecture JSONC"),
        ("export-mermaid", "export target-neutral Mermaid"),
        ("export-ascii", "export target-neutral ASCII"),
        ("export-svg", "export a deterministic workflow SVG"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        _add_audit_input(command)
        command.add_argument("--output")
        if name == "export-architecture":
            command.add_argument("--check", action="store_true")
        if name in {"export-mermaid", "export-ascii", "export-svg"}:
            command.add_argument("--expand-nodesets", dest="expand_nodesets", action="store_true")
            command.add_argument("--collapse-nodeset_types", dest="expand_nodesets", action="store_false")
            command.add_argument("--hide-contract", action="store_true")
            command.add_argument("--hide-semantics", action="store_true")
            command.set_defaults(expand_nodesets=False)
        if name in {"export-mermaid", "export-svg"}:
            command.add_argument(
                "--mermaid-layout",
                choices=("default", "review-columns"),
                default="default",
            )
        if name == "export-svg":
            command.add_argument("--theme", default="default")
            command.add_argument("--background", default="transparent")
            command.add_argument("--mermaid-max-text-size", type=int, default=None)
            command.add_argument("--mermaid-max-edges", type=int, default=None)
            command.add_argument("--review-fragment-max-width", type=float, default=None)

    review = subparsers.add_parser(
        "review",
        help="refresh registered Architecture and atomically publish review SVG",
    )
    _add_audit_input(review)
    review.add_argument("--output")
    review.add_argument("--with-svg", action="store_true")
    review.add_argument("--preview-root", help="override offline preview directory")

    from vibeflow.tooling.application.project_quality import add_quality_parser
    add_quality_parser(subparsers)


def _add_audit_input(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--node-command", default="node", help=argparse.SUPPRESS)


def add_build_parser(subparsers: argparse._SubParsersAction) -> None:
    build = subparsers.add_parser(
        "build",
        help="compile a workflow into a standalone JavaScript/TypeScript AOT artifact",
    )
    build.add_argument(
        "--workspace",
        required=True,
        help="workspace vibeflow_config.jsonc path",
    )
    build.add_argument("--config", required=True, help="workflow JSONC path")
    build.add_argument("--target", required=True, choices=("browser", "node"))
    build.add_argument(
        "--profile",
        required=True,
        choices=("esm-module", "single-esm", "web-app"),
    )
    build.add_argument("--preview-root", help="override offline preview directory")
    build.add_argument("--out-dir", required=True, help="dedicated output directory")
    build.add_argument("--entry-name", default="", help="JavaScript entry file name")
    build.add_argument(
        "--sourcemap",
        choices=("none", "external", "inline"),
        default="external",
    )
    build.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing VibeFlow-owned AOT output",
    )
    build.add_argument("--html", dest="html_template", help="web-app HTML template")
    build.add_argument(
        "--app-entry",
        help="web-app JavaScript/TypeScript application entry",
    )
    build.add_argument(
        "--workflow-id",
        default="",
        help="stable public workflow identifier",
    )
    build.add_argument("--node-command", default="node", help=argparse.SUPPRESS)


def handle_build(args: argparse.Namespace) -> int:
    from vibeflow.tooling.application.javascript.build import (
        ProjectBuildRequest,
        build_project_aot,
    )

    try:
        result = build_project_aot(
            ProjectBuildRequest(
                workspace=Path(args.workspace),
                config=Path(args.config),
                out_dir=Path(args.out_dir),
                target=args.target,
                profile=args.profile,
                workflow_id=args.workflow_id,
                entry_name=args.entry_name,
                sourcemap=args.sourcemap,
                replace=args.replace,
                html_template=(
                    Path(args.html_template) if args.html_template else None
                ),
                app_entry=Path(args.app_entry) if args.app_entry else None,
                node_command=args.node_command,
                preview_root=getattr(args, "preview_root", None),
            )
        )
    except Exception as exc:
        payload = _error_payload(exc, default_code="VF_BUILD_FAILED")
        print(json.dumps(add_result_scope(payload, "vibeflow_build", checked_ids=()), ensure_ascii=False, indent=2))
        return 1

    payload = {
        "status": "PASS",
        "workflow_id": result.prepared.plan.workflow_id,
        "target": args.target,
        "profile": args.profile,
        "out_dir": str(result.out_dir),
        "entry": str(result.entry),
        "manifest": str(result.manifest),
        "files": list(result.files),
        "toolchain": result.build.toolchain.to_dict(),
        "rule_checks": result.prepared.rule_report.to_dict(),
    }
    warnings = tuple(getattr(result.prepared, "warnings", ()) or ())
    if warnings:
        payload["status"] = "CONCERNS"
        payload["warnings"] = [
            dict(item) for item in warnings
        ]
    payload = add_result_scope(payload, "vibeflow_build")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def handle_validate(args: argparse.Namespace) -> int:
    result, error = _audit(args)
    if error is not None:
        _print_error(error, as_json=bool(args.json))
        return 1
    assert result is not None
    payload = _audit_success_payload(result)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_result_scope(payload))
    return 0


def handle_inspect_config(args: argparse.Namespace) -> int:
    from vibeflow.tooling.application.javascript.audit import inspect_payload

    result, error = _audit(args)
    if error is not None:
        _print_error(error, as_json=True)
        return 1
    assert result is not None
    print(json.dumps(inspect_payload(result), ensure_ascii=False, indent=2))
    return 0


def handle_export_architecture(args: argparse.Namespace) -> int:
    from vibeflow.tooling.application.javascript.presentation.architecture import render_architecture

    result, error = _audit(args)
    if error is not None:
        _print_error(error, as_json=True)
        return 1
    assert result is not None
    text = render_architecture(result)
    output = Path(args.output).resolve() if args.output else None
    if bool(args.check):
        if output is None:
            _print_error(
                ValueError("export-architecture --check requires --output"),
                as_json=True,
                code="ARCHITECTURE.DOCUMENT.READ",
            )
            return 1
        try:
            actual = output.read_text(encoding="utf-8")
        except OSError as exc:
            _print_error(exc, as_json=True, code="ARCHITECTURE.DOCUMENT.READ")
            return 1
        if actual != text:
            _print_error(
                ValueError(f"architecture document is stale: {output}"),
                as_json=True,
                code="ARCHITECTURE.DOCUMENT.STALE",
            )
            return 1
        return 0
    _write_or_print(text, output)
    return 0


def handle_export_mermaid(args: argparse.Namespace) -> int:
    from vibeflow.tooling.application.javascript.presentation.diagrams import render_mermaid

    return _handle_text_export(
        args,
        render_mermaid,
        expand_nodesets=bool(args.expand_nodesets),
        show_contract=not bool(args.hide_contract),
        show_semantics=not bool(args.hide_semantics),
        mermaid_layout=str(args.mermaid_layout),
    )


def handle_export_ascii(args: argparse.Namespace) -> int:
    from vibeflow.tooling.application.javascript.presentation.diagrams import render_ascii

    return _handle_text_export(
        args,
        render_ascii,
        expand_nodesets=bool(args.expand_nodesets),
        show_contract=not bool(args.hide_contract),
        show_semantics=not bool(args.hide_semantics),
    )


def handle_export_svg(args: argparse.Namespace) -> int:
    from vibeflow.tooling.application.javascript.presentation.diagrams import write_review_svg
    from vibeflow.tooling.presentation.mermaid.types import REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH

    result, error = _audit(args)
    if error is not None:
        _print_error(error, as_json=True)
        return 1
    assert result is not None
    output = Path(args.output).resolve() if args.output else None
    try:
        if output is not None:
            write_review_svg(
                result,
                output,
                expand_nodesets=bool(args.expand_nodesets),
                show_contract=not bool(args.hide_contract),
                show_semantics=not bool(args.hide_semantics),
                theme=str(args.theme),
                background=str(args.background),
                max_text_size=args.mermaid_max_text_size,
                max_edges=args.mermaid_max_edges,
                review_fragment_max_width=(
                    args.review_fragment_max_width
                    if args.review_fragment_max_width is not None
                    else REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH
                ),
                mermaid_layout=str(args.mermaid_layout),
            )
        else:
            with tempfile.TemporaryDirectory(prefix="vibeflow-javascript-export-svg-") as raw:
                temporary = Path(raw) / "graph.svg"
                write_review_svg(
                    result,
                    temporary,
                    expand_nodesets=bool(args.expand_nodesets),
                    show_contract=not bool(args.hide_contract),
                    show_semantics=not bool(args.hide_semantics),
                    theme=str(args.theme),
                    background=str(args.background),
                    max_text_size=args.mermaid_max_text_size,
                    max_edges=args.mermaid_max_edges,
                    review_fragment_max_width=(
                        args.review_fragment_max_width
                        if args.review_fragment_max_width is not None
                        else REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH
                    ),
                    mermaid_layout=str(args.mermaid_layout),
                )
                print(temporary.read_text(encoding="utf-8"), end="")
    except Exception as exc:
        _print_error(exc, as_json=True, code="SVG.RENDER")
        return 1
    return 0


def handle_review(args: argparse.Namespace) -> int:
    from vibeflow.tooling.application.javascript.presentation.architecture import render_architecture
    config_path = Path(args.config).resolve()
    output = Path(args.output).resolve() if args.output else Path(getattr(args, "preview_root", None) or Path(args.workspace).resolve().parent) / "vibeflow-preview.html"
    payload: dict[str, object] = {
        "status": "ERROR",
        "failed_stage": None,
        "config": str(config_path),
        "architecture": None,
        "validation": None,
        "svg": str(output) if args.output else None,
        "output": str(output),
        "project_target": "javascript",
        "published": False,
    }

    try:
        from vibeflow.tooling.project.workspace_loader import load_workspace_config

        workspace = load_workspace_config(Path(args.workspace).resolve())
        from vibeflow.tooling.project.preparation import ProjectPreparation
        args.preparation = ProjectPreparation(workspace, node_command=args.node_command)
        args.governance = args.preparation.review(write_architecture=True)
        payload["project_architecture"] = str(args.governance.architecture_path)
        root = workspace.root_for_path(config_path)
        if root is None:
            return _finish_review_failure(
                payload,
                "workspace",
                "WORKSPACE.CONFIG.OUTSIDE_ROOT",
                ValueError(f"config is not under any workspace root: {config_path}"),
            )
        spec = next(
            (
                item
                for item in root.architecture_documents
                if item.workflow_path.resolve() == config_path
            ),
            None,
        )
        if spec is None:
            return _finish_review_failure(
                payload,
                "architecture",
                "REVIEW.ARCHITECTURE.UNREGISTERED",
                ValueError(
                    f"workflow is not registered in {root.config_path} architecture.documents: {config_path}"
                ),
                status="FAIL",
            )
        architecture_path = spec.document_path.resolve()
        payload["architecture"] = str(architecture_path)
        protected = {workspace.path.resolve(), config_path, architecture_path}
        if output in protected:
            return _finish_review_failure(
                payload,
                "output",
                "REVIEW.OUTPUT.CONFLICT",
                ValueError(
                    "review output cannot overwrite workspace, workflow, or Architecture source"
                ),
                status="FAIL",
            )
    except Exception as exc:
        return _finish_review_failure(
            payload,
            "workspace",
            str(getattr(exc, "rule_id", "WORKSPACE.LOAD")),
            exc,
        )

    result, error = _audit(args)
    if error is not None:
        return _finish_review_failure(
            payload,
            "preflight",
            str(getattr(error, "code", getattr(error, "rule_id", "REVIEW.PREFLIGHT"))),
            error,
            status="FAIL",
        )
    assert result is not None
    architecture = render_architecture(result)
    try:
        _atomic_write(architecture_path, architecture)
        if architecture_path.read_text(encoding="utf-8") != architecture:
            raise ValueError("generated Architecture document is not canonical after publication")
        _validate_architecture_document(architecture)
    except Exception as exc:
        return _finish_review_failure(
            payload,
            "architecture",
            "REVIEW.ARCHITECTURE.WRITE",
            exc,
        )

    validation = _audit_success_payload(result)
    payload["validation"] = validation
    return _publish_review_preview(result, args, payload)


def _publish_review_preview(result, args, payload):
    from vibeflow.tooling.application.javascript.presentation.preview import javascript_preview
    from vibeflow.tooling.presentation.preview.exporter import attach_svg
    record = None
    try:
        record = javascript_preview(result, preview_root=getattr(args,"preview_root",None),category="review",status="reviewing" if args.output or getattr(args,"with_svg",False) else "passed")
        payload.update(preview=str(record.root/"vibeflow-preview.html"),preview_id=record.metadata["id"])
    except Exception as exc:
        return _finish_review_failure(payload,"preview","REVIEW.PREVIEW.WRITE",exc,status="FAIL")
    if args.output or getattr(args,"with_svg",False):
        from vibeflow.tooling.application.javascript.presentation.diagrams import write_review_svg, expected_review_coverage
        output=Path(args.output).resolve() if args.output else record.directory/"requested-review.svg"
        temporary=None
        stage,code="svg","REVIEW.SVG.RENDER"
        try:
            output.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix="."+output.name+".",suffix=".tmp",dir=output.parent,delete=False) as handle:
                temporary=Path(handle.name)
            write_review_svg(result,temporary,expand_nodesets=True,show_contract=True,show_semantics=True,
                theme="default",background="transparent",mermaid_layout="review-columns")
            stage,code="svg_check","REVIEW.SVG.COVERAGE"
            _validate_review_svg_file(temporary,expected_coverage=expected_review_coverage(result))
            stage,code="publish","REVIEW.SVG.PUBLISH"
            os.replace(temporary,output)
            attach_svg(record,output)
            record.update("passed")
            payload["svg"]=str(output if args.output else record.directory/"review.svg")
        except Exception as exc:
            record.metadata["svg_error"]=str(exc)
            record.update("failed",error=str(exc))
            return _finish_review_failure(payload,stage,getattr(exc,"code",code),exc,status="FAIL")
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
            if not args.output:output.unlink(missing_ok=True)
    payload.update(status="CONCERNS" if result.warnings else "PASS",failed_stage=None,published=True,
        **({"warnings":list(result.warnings)} if result.warnings else {}))
    payload=add_result_scope(payload,"vibeflow_review_artifact")
    print(json.dumps(payload,ensure_ascii=False,indent=2))
    return 0




















def _diagnostic_text(finding: Mapping[str, object]) -> str:
    code = str(finding.get("code", finding.get("rule_id", "")))
    definition = str(finding.get("definition_id", ""))
    identity = f"{code} [{definition}]" if definition else code
    location = finding.get("source_location", {})
    position = ""
    if isinstance(location, Mapping):
        position = str(location.get("path", ""))
        for field in ("line", "column"):
            if location.get(field) is not None:
                position += f":{location[field]}"
    details = finding.get("details", {})
    owner = str(details.get("definition_id", "")) if isinstance(details, Mapping) else ""
    if not owner:
        owner = str(finding.get("object_id", ""))
    owner_text = f" (owner: {owner})" if owner else ""
    return f"  {identity}: {position}{owner_text} {finding.get('message', '')}"




def _audit(args: argparse.Namespace):
    from vibeflow.tooling.application.javascript.audit import (
        JavascriptAuditRequest,
        audit_javascript_project,
    )

    try:
        return (
            audit_javascript_project(
                JavascriptAuditRequest(
                    workspace=(
                        args.workspace_config
                        if getattr(args, "workspace_config", None) is not None
                        else Path(args.workspace)
                    ),
                    config=Path(args.config),
                    node_command=str(args.node_command),
                    quality_policy=getattr(args, "quality_policy", None),
                    catalogs=getattr(args, "catalogs", None),
                    preparation=getattr(args, "preparation", None), governance=getattr(args, "governance", None),
                )
            ),
            None,
        )
    except Exception as exc:
        return None, exc


def _audit_success_payload(result) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "PASS",
        "project_target": "javascript",
        "workflow_id": result.plan.workflow_id,
        "config": str(result.config_path),
        "source_files": list(result.source_files),
        "rule_checks": result.rule_report.to_dict() if result.rule_report else {},
    }
    if result.warnings:
        payload["status"] = "CONCERNS"
        payload["warnings"] = list(result.warnings)
    if result.toolchain is not None:
        payload["toolchain"] = result.toolchain.to_dict()
    return add_result_scope(payload, "vibeflow_structure")


def _handle_text_export(args: argparse.Namespace, renderer, **render_options) -> int:
    result, error = _audit(args)
    if error is not None:
        _print_error(error, as_json=True)
        return 1
    assert result is not None
    _write_or_print(
        renderer(result, **render_options),
        Path(args.output).resolve() if args.output else None,
    )
    return 0


def _write_or_print(text: str, output: Path | None) -> None:
    if output is None:
        print(text, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _atomic_write(path: Path, text: str) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class _ReviewSvgValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _validate_architecture_document(architecture: str) -> None:
    from vibeflow.tooling.project.document_kinds import (
        ARCHITECTURE_DOCUMENT_HEADER,
    )

    if not architecture.startswith(ARCHITECTURE_DOCUMENT_HEADER):
        raise ValueError(
            "generated Architecture document has no VibeFlow header"
        )
    try:
        payload = json.loads(architecture[len(ARCHITECTURE_DOCUMENT_HEADER) :])
    except json.JSONDecodeError as exc:
        raise ValueError(
            "generated Architecture document is not valid JSONC"
        ) from exc
    if (
        not isinstance(payload, Mapping)
        or payload.get("project_target") != "javascript"
    ):
        raise ValueError("generated Architecture document has an invalid target")


def _validate_review_svg_file(
    path: Path,
    *,
    expected_coverage: frozenset[tuple[str, str, str]],
) -> None:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise _ReviewSvgValidationError(
            "REVIEW.SVG.XML",
            "generated review SVG is not valid XML",
        ) from exc
    if not root.tag.endswith("svg"):
        raise _ReviewSvgValidationError(
            "REVIEW.SVG.ROOT",
            "generated review SVG has an invalid root element",
        )
    if root.get("aria-roledescription") != "flowchart-review-columns":
        raise _ReviewSvgValidationError(
            "REVIEW.SVG.LAYOUT",
            "generated review SVG has no review layout marker",
        )
    fragments = [
        element
        for element in root.iter()
        if element.tag.endswith("g")
        and "review-inline-fragment" in element.get("class", "").split()
    ]
    if not any(len(list(fragment)) > 0 for fragment in fragments):
        raise _ReviewSvgValidationError(
            "REVIEW.SVG.FRAGMENT",
            "generated review SVG has no non-empty review fragment",
        )
    actual_items = [
        (
            fragment.get("data-review-kind", ""),
            fragment.get("data-review-owner", ""),
            fragment.get("data-review-target", ""),
        )
        for fragment in fragments
        if fragment.get("data-review-kind", "") in {
            "workflow",
            "resource",
            "nodeset",
            "loop_body",
        }
    ]
    actual = frozenset(actual_items)
    duplicates = sorted(
        item for item in actual if actual_items.count(item) > 1
    )
    missing = sorted(expected_coverage - actual)
    unexpected = sorted(actual - expected_coverage)
    if missing or unexpected or duplicates:
        raise _ReviewSvgValidationError(
            "REVIEW.SVG.COVERAGE",
            "generated review SVG coverage mismatch: "
            f"missing={missing}, unexpected={unexpected}, duplicates={duplicates}",
        )


def _finish_review_failure(
    payload: dict[str, object],
    stage: str,
    code: str,
    error: BaseException,
    *,
    status: str = "ERROR",
) -> int:
    message = str(getattr(error, "message", str(error)))
    payload.update(
        status=status,
        failed_stage=stage,
        published=False,
        code=code,
        error={
            "rule_id": code,
            "severity": "error",
            "object_type": "review",
            "object_id": str(payload.get("config") or ""),
            "failure_layer": stage,
            "message": message,
            "details": {},
            "suggested_fix_type": "fix_config",
        },
    )
    diagnostics = _error_payload(error)
    for field in ("diagnostics", "warnings", "source_location", "field"):
        if field in diagnostics:
            payload[field] = diagnostics[field]
    print(json.dumps(add_result_scope(payload, "vibeflow_review_artifact", checked_ids=()), ensure_ascii=False, indent=2))
    return 1






def _error_payload(error: Exception, *, config: Path | None = None,
                   default_code: str = "VF_AUDIT_FAILED") -> dict[str, object]:
    diagnostics = getattr(error, "diagnostics", ())
    payload: dict[str, object] = {
        "status": "ERROR",
        "code": str(
            getattr(error, "code", getattr(error, "rule_id", default_code))
        ),
        "error": str(getattr(error, "message", str(error))),
    }
    if config is not None:
        payload["config"] = str(config)
    if getattr(error, "path", ""):
        payload["source_location"] = {"path": str(error.path)}
    if getattr(error, "field", ""):
        payload["field"] = str(error.field)
    if getattr(error, "details", None):
        payload["details"] = dict(error.details)
    if diagnostics:
        payload["diagnostics"] = [
            dict(item) if isinstance(item, Mapping) else str(item)
            for item in diagnostics
        ]
        warnings = [item for item in diagnostics if isinstance(item, Mapping) and item.get("severity") == "warning"]
        if warnings:
            payload["warnings"] = warnings
    return payload


def _print_error(
    error: Exception,
    *,
    as_json: bool,
    code: str = "",
    validation_scope: str = "vibeflow_structure",
) -> None:
    payload = add_result_scope(
        _error_payload(error), validation_scope, checked_ids=()
    )
    if code:
        payload["code"] = code
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_result_scope(payload))
        print(f"ERROR {payload['code']}: {payload['error']}")
        for finding in payload.get("diagnostics", ()):
            if isinstance(finding, Mapping):
                print(_diagnostic_text(finding))


__all__ = [
    "add_audit_parsers",
    "add_build_parser",
    "build_parser",
    "handle_build",
    "handle_export_architecture",
    "handle_inspect_config",
    "handle_quality_check",
    "handle_review",
    "handle_validate",
    "main",
]
