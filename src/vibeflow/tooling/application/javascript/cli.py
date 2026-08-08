from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Mapping, Sequence
from xml.etree import ElementTree


def build_parser() -> argparse.ArgumentParser:
    """Create the JavaScript application parser without loading Python."""

    parser = argparse.ArgumentParser(prog="vibeflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_build_parser(subparsers)
    add_audit_parsers(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
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
            command.add_argument("--collapse-nodesets", dest="expand_nodesets", action="store_false")
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
    review.add_argument("--output", required=True)

    quality = subparsers.add_parser(
        "quality-check",
        help="check JavaScript architecture and ownership boundaries",
    )
    quality.add_argument("--workspace")
    quality.add_argument("--config")
    quality.add_argument("--path")
    quality.add_argument(
        "--project-target",
        choices=("javascript",),
        help=argparse.SUPPRESS,
    )
    quality.add_argument("--json", action="store_true")
    quality.add_argument("--node-command", default="node", help=argparse.SUPPRESS)


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
            )
        )
    except Exception as exc:
        diagnostics = getattr(exc, "diagnostics", ())
        payload: dict[str, object] = {
            "status": "ERROR",
            "code": str(getattr(exc, "code", "VF_BUILD_FAILED")),
            "error": str(getattr(exc, "message", str(exc))),
        }
        if diagnostics:
            payload["diagnostics"] = [
                dict(item) if isinstance(item, Mapping) else str(item)
                for item in diagnostics
            ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
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
    }
    warnings = tuple(getattr(result.prepared, "warnings", ()) or ())
    if warnings:
        payload["warnings"] = [
            dict(item) for item in warnings
        ]
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
        print("PASS")
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
    from vibeflow.tooling.application.javascript.audit import render_architecture

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
    from vibeflow.tooling.application.javascript.audit import render_mermaid

    return _handle_text_export(
        args,
        render_mermaid,
        expand_nodesets=bool(args.expand_nodesets),
        show_contract=not bool(args.hide_contract),
        show_semantics=not bool(args.hide_semantics),
        mermaid_layout=str(args.mermaid_layout),
    )


def handle_export_ascii(args: argparse.Namespace) -> int:
    from vibeflow.tooling.application.javascript.audit import render_ascii

    return _handle_text_export(
        args,
        render_ascii,
        expand_nodesets=bool(args.expand_nodesets),
        show_contract=not bool(args.hide_contract),
        show_semantics=not bool(args.hide_semantics),
    )


def handle_export_svg(args: argparse.Namespace) -> int:
    from vibeflow.tooling.application.javascript.review import write_review_svg
    from vibeflow.tooling.presentation.review_types import REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH

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
    from vibeflow.tooling.application.javascript.audit import (
        render_architecture,
    )
    from vibeflow.tooling.application.javascript.review import (
        expected_review_coverage,
        write_review_svg,
    )

    config_path = Path(args.config).resolve()
    output = Path(args.output).resolve()
    payload: dict[str, object] = {
        "status": "ERROR",
        "failed_stage": None,
        "config": str(config_path),
        "architecture": None,
        "validation": None,
        "svg": str(output),
        "output": str(output),
        "project_target": "javascript",
        "published": False,
    }

    try:
        from vibeflow.tooling.project.workspace_loader import load_workspace_config

        workspace = load_workspace_config(Path(args.workspace).resolve())
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
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        write_review_svg(
            result,
            temporary,
            expand_nodesets=True,
            show_contract=True,
            show_semantics=True,
            theme="default",
            background="transparent",
            mermaid_layout="review-columns",
        )
    except Exception as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        return _finish_review_failure(
            payload,
            "svg",
            "REVIEW.SVG.RENDER",
            exc,
            status="FAIL",
        )
    try:
        assert temporary is not None
        _validate_review_svg_file(
            temporary,
            expected_coverage=expected_review_coverage(result),
        )
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        return _finish_review_failure(
            payload,
            "svg_check",
            str(getattr(exc, "code", "REVIEW.SVG.COVERAGE")),
            exc,
            status="FAIL",
        )
    try:
        os.replace(temporary, output)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        return _finish_review_failure(
            payload,
            "publish",
            "REVIEW.SVG.PUBLISH",
            exc,
        )

    payload.update(status="PASS", failed_stage=None, published=True)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def handle_quality_check(args: argparse.Namespace) -> int:
    from vibeflow.tooling.project.workspace_loader import (
        find_project_config,
        load_project_workspace,
        load_workspace_config,
    )

    try:
        workspace = None
        if args.workspace:
            workspace_path = Path(args.workspace).resolve()
        else:
            try:
                workspace_path = _find_workspace(
                    Path(args.path or args.config or ".")
                )
            except ValueError:
                project_config = find_project_config(
                    Path(args.path or args.config or ".")
                )
                if project_config is not None:
                    workspace = load_project_workspace(project_config)
                    workspace_path = workspace.path
                elif (
                    args.path
                    and not args.config
                    and args.project_target == "javascript"
                ):
                    return _handle_standalone_quality(
                        Path(args.path),
                        node_command=args.node_command,
                    )
                else:
                    raise
        if workspace is None:
            workspace = load_workspace_config(workspace_path)
        configs = _quality_configs(
            workspace,
            explicit_config=args.config,
            explicit_path=args.path,
        )
    except Exception as exc:
        _print_error(exc, as_json=True)
        return 1
    reports: list[dict[str, object]] = []
    failed = False
    for config in configs:
        namespace = argparse.Namespace(
            workspace=str(workspace_path),
            config=str(config),
            node_command=args.node_command,
            audit_registered_resources=True,
            workspace_config=workspace,
        )
        result, error = _audit(namespace)
        if error is not None:
            failed = True
            reports.append(_error_payload(error, config=config))
        else:
            assert result is not None
            reports.append(_audit_success_payload(result))
    payload = {
        "status": "FAIL" if failed else "PASS",
        "project_target": "javascript",
        "reports": reports,
        **({"skipped": "quality_enabled=false"} if not configs else {}),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failed else 0


def _handle_standalone_quality(
    source_path: Path,
    *,
    node_command: str,
) -> int:
    from vibeflow.targets.javascript.build.toolchain import (
        AotToolchainError,
        run_audit_driver,
    )

    selected = source_path.expanduser().resolve()
    try:
        files = _standalone_javascript_sources(selected)
        package_root = _standalone_package_root(selected)
        result = run_audit_driver(
            {
                "typecheckFiles": [str(item) for item in files],
                "importPolicy": {
                    "owners": [
                        {
                            "path": str(item),
                            "kind": "source",
                            "id": _relative_source_id(
                                package_root,
                                item,
                            ),
                        }
                        for item in files
                    ],
                    "allowedExternalPackages": [],
                },
            },
            package_root=package_root,
            node_command=node_command,
        )
    except (AotToolchainError, OSError, ValueError) as exc:
        payload = {
            "status": "FAIL",
            "project_target": "javascript",
            "path": str(selected),
            "reports": [_error_payload(exc)],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    payload = {
        "status": "PASS",
        "project_target": "javascript",
        "path": str(selected),
        "source_files": [str(item) for item in files],
        "toolchain": result.toolchain.to_dict(),
        "reports": [],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _standalone_package_root(source_path: Path) -> Path:
    start = source_path if source_path.is_dir() else source_path.parent
    for candidate in (start, *start.parents):
        if (candidate / "package.json").is_file():
            return candidate
    raise ValueError(
        "standalone JavaScript quality requires an ancestor package.json"
    )


def _standalone_javascript_sources(source_path: Path) -> tuple[Path, ...]:
    extensions = frozenset(
        {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
    )
    excluded = frozenset(
        {
            ".git",
            ".hg",
            ".pytest_cache",
            "build",
            "dist",
            "node_modules",
            "vendor",
        }
    )

    def accepted(path: Path) -> bool:
        name = path.name.lower()
        return (
            path.is_file()
            and path.suffix.lower() in extensions
            and not name.endswith((".d.ts", ".d.mts", ".d.cts"))
        )

    if source_path.is_file():
        if not accepted(source_path):
            raise ValueError(
                f"not a JavaScript/TypeScript source file: {source_path}"
            )
        return (source_path,)
    if not source_path.is_dir():
        raise ValueError(f"quality path does not exist: {source_path}")
    files = tuple(
        sorted(
            item.resolve()
            for item in source_path.rglob("*")
            if accepted(item)
            and not any(part in excluded for part in item.relative_to(source_path).parts)
        )
    )
    return files


def _relative_source_id(package_root: Path, source: Path) -> str:
    try:
        return source.relative_to(package_root).as_posix()
    except ValueError:
        return source.name


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
                    audit_registered_resources=bool(
                        getattr(args, "audit_registered_resources", False)
                    ),
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
    }
    if result.toolchain is not None:
        payload["toolchain"] = result.toolchain.to_dict()
    return payload


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


def _publish_review_pair(
    documents: tuple[tuple[Path, str], tuple[Path, str]],
) -> None:
    """Publish Architecture and SVG as one recoverable filesystem change."""

    staged: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    published: list[Path] = []
    committed = False
    try:
        for raw_path, text in documents:
            path = raw_path.resolve()
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
                handle.flush()
                os.fsync(handle.fileno())
                staged[path] = Path(handle.name)

        for path, _text in ((item[0].resolve(), item[1]) for item in documents):
            backup: Path | None = None
            if path.exists():
                with tempfile.NamedTemporaryFile(
                    prefix=f".{path.name}.",
                    suffix=".backup",
                    dir=path.parent,
                    delete=False,
                ) as handle:
                    backup = Path(handle.name)
                backup.unlink()
                os.replace(path, backup)
            backups[path] = backup
            try:
                os.replace(staged[path], path)
            except BaseException:
                if backup is not None:
                    os.replace(backup, path)
                    backups[path] = None
                raise
            published.append(path)
        committed = True
    except BaseException:
        restore_error: BaseException | None = None
        for path in reversed(published):
            try:
                path.unlink(missing_ok=True)
                backup = backups.get(path)
                if backup is not None and backup.exists():
                    os.replace(backup, path)
                    backups[path] = None
            except BaseException as exc:
                restore_error = restore_error or exc
        if restore_error is not None:
            raise OSError(
                "review publish failed and rollback could not restore all files"
            ) from restore_error
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        for backup in backups.values():
            if committed and backup is not None:
                backup.unlink(missing_ok=True)


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


def _validate_review_documents(architecture: str, svg: str) -> None:
    """Compatibility validation used by older programmatic callers."""

    _validate_architecture_document(architecture)
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError as exc:
        raise ValueError("generated review SVG is not valid XML") from exc
    if not root.tag.endswith("svg"):
        raise ValueError("generated review SVG has an invalid root element")
    if root.get("aria-roledescription") != "flowchart-review-columns":
        raise ValueError("generated review SVG has no review layout marker")


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
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1


def _quality_configs(
    workspace,
    *,
    explicit_config: str | None,
    explicit_path: str | None,
) -> tuple[Path, ...]:
    if explicit_config:
        candidate = Path(explicit_config).resolve()
        root = workspace.root_for_path(candidate)
        if (
            root is not None
            and root.project_target == "javascript"
            and not getattr(root, "quality_enabled", True)
        ):
            return ()
        return (candidate,)
    if explicit_path:
        candidate = Path(explicit_path).resolve()
        if candidate.is_file() and _is_workflow_config(candidate):
            root = workspace.root_for_path(candidate)
            if (
                root is not None
                and root.project_target == "javascript"
                and not getattr(root, "quality_enabled", True)
            ):
                return ()
            return (candidate,)
        roots = [
            root
            for root in workspace.roots
            if root.project_target == "javascript"
            and (
                candidate == root.path
                or root.path in candidate.parents
                or candidate in root.path.parents
            )
        ]
    else:
        roots = [
            root
            for root in workspace.roots
            if root.project_target == "javascript"
        ]
    matched_roots = tuple(roots)
    roots = [
        root
        for root in matched_roots
        if getattr(root, "quality_enabled", True)
    ]
    if matched_roots and not roots:
        return ()
    configs: set[Path] = set()
    for root in roots:
        configs.update(
            item.workflow_path.resolve()
            for item in root.architecture_documents
        )
        config_root = root.path / "configs"
        if config_root.is_dir():
            for item in config_root.rglob("*.jsonc"):
                if _is_workflow_config(item):
                    configs.add(item.resolve())
    if not configs:
        raise ValueError("no JavaScript workflow configs were found")
    return tuple(sorted(configs))


def _is_workflow_config(path: Path) -> bool:
    from vibeflow.tooling.project.config_loader import load_raw_config_document
    from vibeflow.tooling.project.document_kinds import (
        is_architecture_document_text,
    )

    if path.suffix.lower() not in {".json", ".jsonc"}:
        return False
    try:
        text = path.read_text(encoding="utf-8")
        if is_architecture_document_text(text):
            return False
        document = load_raw_config_document(path)
    except (OSError, ValueError):
        return False
    return (
        isinstance(document.data.get("pipeline"), Mapping)
        and "type_key" not in document.data
    )


def _find_workspace(value: Path) -> Path:
    candidate = value.expanduser().resolve()
    start = candidate if candidate.is_dir() else candidate.parent
    for directory in (start, *start.parents):
        workspace = directory / "vibeflow_config.jsonc"
        if workspace.is_file():
            return workspace
    raise ValueError(
        f"cannot find vibeflow_config.jsonc above {candidate}; pass --workspace"
    )


def _error_payload(error: Exception, *, config: Path | None = None) -> dict[str, object]:
    diagnostics = getattr(error, "diagnostics", ())
    payload: dict[str, object] = {
        "status": "ERROR",
        "code": str(
            getattr(error, "code", getattr(error, "rule_id", "VF_AUDIT_FAILED"))
        ),
        "error": str(getattr(error, "message", str(error))),
    }
    if config is not None:
        payload["config"] = str(config)
    if diagnostics:
        payload["diagnostics"] = [
            dict(item) if isinstance(item, Mapping) else str(item)
            for item in diagnostics
        ]
    return payload


def _print_error(error: Exception, *, as_json: bool, code: str = "") -> None:
    payload = _error_payload(error)
    if code:
        payload["code"] = code
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"ERROR {payload['code']}: {payload['error']}")


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
