"""Repository profile implementations."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, Iterator
from urllib.parse import unquote

from .application_scan import (
    javascript_application_findings,
    neutral_tooling_findings,
    python_application_findings,
)
from .models import Finding, Report, SourceLocation, make_report
from .python_scan import (
    build_import_graph,
    iter_python_files,
    parse_python,
    repository_path,
    scan_layer,
)


PROFILE_NAMES = (
    "base",
    "core",
    "block-compiler",
    "python-target",
    "javascript-target",
    "all",
)

_LEGACY_PACKAGE_DIRS = frozenset(
    {
        "aot",
        "cli",
        "config",
        "descriptors",
        "devtools",
        "graph_config",
        "health",
        "portable",
        "plugins",
        "purity",
        "rendering",
        "resources",
        "runtime",
        "workspace",
    }
)

_GENERATED_ROOT_NAMES = frozenset(
    {
        ".pytest_cache",
        "build",
        "output",
        "reports",
        "review_artifacts",
        "runs",
        "tmp",
        "vibeflow_distribution",
    }
)

_DOCUMENTATION_ROOTS = (
    "README.md",
    "README.en.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    ".github",
    "docs",
    "distribution/kernel_development_pack",
    "quality/README.md",
    "sandbox",
)

_REMOVED_DOCUMENT_TOKENS = (
    "11_训练性能导向内核改进计划.md",
    "12_CompiledBlock完整代码生成计划.md",
    "13_CompiledBlock分阶段实施计划.md",
    "14_JS_TS节点与Web_AOT构建计划.md",
    "15_长期工作流与原生IO改造计划.md",
    "16_语言无关内核与多Target分层架构目标.md",
    "strict_flowchart_kernel_redesign.md",
)

_STALE_DOCUMENT_TOKENS = {
    "0.9.0": "Replace the obsolete public release version with 0.10.1.",
    "0.10.0": "Replace the obsolete public release version with 0.10.1.",
    "vibeflow.runtime": "Use the owning 0.10 layered API instead of the removed runtime facade.",
    "vibeflow.aot": "Use vibeflow.targets.javascript instead of the removed AOT facade.",
    "vibeflow.portable": "Use vibeflow.block_compiler instead of the removed portable facade.",
    "examples/": "Use the canonical sandbox/ path.",
    "vibeflow_distribution/": "Use dist/vibeflow-distribution/ for the current release directory.",
}

_MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")

_DOCUMENT_COMMAND_PATTERNS = (
    (
        "distribution launcher",
        re.compile(r"\bpython(?:3)?\s+run\.py\s+([a-z][a-z0-9-]*)"),
        frozenset(
            {
                "architecture",
                "ascii",
                "build",
                "delegate-cli",
                "export-architecture",
                "export-ascii",
                "export-mermaid",
                "export-svg",
                "inspect-config",
                "inspect-node",
                "mermaid",
                "quality",
                "quality-check",
                "review",
                "run",
                "svg",
                "validate",
                "verify-kernel",
            }
        ),
    ),
    (
        "module CLI",
        re.compile(r"\bpython(?:3)?\s+-m\s+vibeflow\s+([a-z][a-z0-9-]*)"),
        frozenset(
            {
                "build",
                "delegate-cli",
                "export-architecture",
                "export-ascii",
                "export-mermaid",
                "export-svg",
                "inspect-config",
                "inspect-node",
                "quality-check",
                "review",
                "run",
                "validate",
            }
        ),
    ),
    (
        "installed CLI",
        re.compile(r"(?<!-m )(?<![-\w.])vibeflow\s+([a-z][a-z0-9-]*)"),
        frozenset(
            {
                "build",
                "delegate-cli",
                "export-architecture",
                "export-ascii",
                "export-mermaid",
                "export-svg",
                "inspect-config",
                "inspect-node",
                "quality-check",
                "review",
                "run",
                "validate",
            }
        ),
    ),
)

_GENERATED_ANYWHERE_NAMES = frozenset(
    {
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
    }
)

_SANDBOX_GENERATED_NAMES = frozenset(
    {
        ".artifacts",
        "build",
        "dist",
        "output",
        "reports",
        "review_artifacts",
        "runs",
        "tmp",
    }
)

_SOURCE_TREES = ("src", "quality", "tools", "distribution", "sandbox", "tests")

_LEGACY_LAYER_DIRS = {
    "src/vibeflow/core": frozenset({"health"}),
    "src/vibeflow/targets/python": frozenset({"health", "purity"}),
    "src/vibeflow/tooling": frozenset(
        {"devtools", "javascript", "rendering", "workspace"}
    ),
}

_LAYER_ROOTS_WITH_INIT_ONLY = (
    "src/vibeflow/targets",
    "src/vibeflow/targets/python",
    "src/vibeflow/targets/javascript",
    "src/vibeflow/tooling",
)

_REQUIRED_DIRECTORIES = (
    "quality",
    "sandbox/python/minimal",
    "sandbox/python/integration",
    "sandbox/javascript/minimal",
    "sandbox/javascript/integration",
    "src/vibeflow/core/config",
    "src/vibeflow/core/descriptors",
    "src/vibeflow/core/quality",
    "src/vibeflow/core/inspection",
    "src/vibeflow/block_compiler",
    "src/vibeflow/targets/python/project",
    "src/vibeflow/targets/python/quality",
    "src/vibeflow/targets/python/runtime",
    "src/vibeflow/targets/javascript/frontend",
    "src/vibeflow/targets/javascript/quality",
    "src/vibeflow/targets/javascript/build",
    "src/vibeflow/targets/javascript/resources",
    "src/vibeflow/tooling/application",
    "src/vibeflow/tooling/application/cli",
    "src/vibeflow/tooling/application/javascript",
    "src/vibeflow/tooling/application/python",
    "src/vibeflow/tooling/application/python/project",
    "src/vibeflow/tooling/application/python/presentation",
    "src/vibeflow/tooling/project",
    "tests/core",
    "tests/block_compiler",
    "tests/targets",
    "tests/tooling",
    "tests/conformance",
    "tests/integration",
    "tests/fixtures",
    "distribution",
    "references",
    "tools",
)

_LEGACY_REPOSITORY_PATHS = (
    "examples",
    "src/vibeflow/tooling/application/cli/build_command.py",
    "src/vibeflow/tooling/application/cli/config.py",
    "src/vibeflow/tooling/application/cli/delegate_cli.py",
    "src/vibeflow/tooling/application/cli/export.py",
    "src/vibeflow/tooling/application/cli/node.py",
    "src/vibeflow/tooling/application/cli/quality.py",
    "src/vibeflow/tooling/application/cli/reports.py",
    "src/vibeflow/tooling/application/cli/review.py",
    "src/vibeflow/tooling/application/delegate_contract.py",
    "src/vibeflow/tooling/application/diagnostics.py",
    "src/vibeflow/tooling/application/javascript_build.py",
    "src/vibeflow/tooling/application/quality_output.py",
    "src/vibeflow/tooling/application/reports.py",
    "src/vibeflow/tooling/application/run_directory.py",
    "src/vibeflow/tooling/application/runner.py",
    "src/vibeflow/tooling/application/workspace_service.py",
    "src/vibeflow/tooling/presentation",
    "src/vibeflow/tooling/project/core.py",
    "src/vibeflow/tooling/project/effective_policy.py",
    "src/vibeflow/tooling/project/plugin_resources.py",
    "src/vibeflow/tooling/project/policy.py",
    "src/vibeflow/tooling/project/project_options.py",
    "src/vibeflow/tooling/project/python_quality.py",
    "src/vibeflow/tooling/project/quality.py",
    "src/vibeflow/tooling/project/quality_scan.py",
    "src/vibeflow/tooling/project/resource_registries.py",
    "src/vibeflow/tooling/project/resources.py",
    "src/vibeflow/tooling/project/types.py",
    "tests/unit",
    "tests/support",
    "build_distribution.py",
    "tools/check_layering.py",
    "tools/layering_allowlist.json",
    "tools/refactor_quality_profile.py",
    "tools/run_refactor_gate.py",
)


class RepositoryCheckError(RuntimeError):
    """The checker could not run because its environment is invalid."""


def _finding(
    code: str,
    root: Path,
    path: Path,
    message: str,
    fix: str,
    *,
    line: int = 1,
    details: dict[str, object] | None = None,
) -> Finding:
    relative = repository_path(path, root)
    return Finding(
        code=code,
        severity="error",
        subject_type="repository_path",
        subject_id=relative,
        source_location=SourceLocation(relative, line, 0),
        message=message,
        suggested_fix=fix,
        details=details or {},
    )


def _iter_source_python(root: Path) -> Iterator[Path]:
    for name in _SOURCE_TREES:
        directory = root / name
        if not directory.is_dir():
            continue
        yield from iter_python_files(directory)


def _generated_paths(root: Path) -> Iterator[Path]:
    ignored_roots = {".git", "archive", "dist", "references"}
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        relative_parts = current_path.relative_to(root).parts
        if relative_parts and relative_parts[0] in ignored_roots:
            directories[:] = []
            continue
        kept: list[str] = []
        for name in directories:
            candidate = current_path / name
            at_root = current_path == root
            in_sandbox = bool(relative_parts and relative_parts[0] == "sandbox")
            generated = (
                (at_root and name in _GENERATED_ROOT_NAMES)
                or name in _GENERATED_ANYWHERE_NAMES
                or (in_sandbox and name in _SANDBOX_GENERATED_NAMES)
                or name.endswith(".egg-info")
            )
            if generated:
                yield candidate
            else:
                kept.append(name)
        directories[:] = kept
        if current_path == root:
            for name in files:
                if name.lower().endswith(".zip"):
                    yield current_path / name
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                yield current_path / name


def _iter_documentation_files(root: Path) -> Iterator[Path]:
    """Yield maintained Markdown without traversing generated releases."""

    seen: set[Path] = set()
    for relative in _DOCUMENTATION_ROOTS:
        candidate = root / relative
        if candidate.is_file() and candidate.suffix.lower() == ".md":
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield candidate
            continue
        if not candidate.is_dir():
            continue
        for path in sorted(candidate.rglob("*.md")):
            if any(
                part in _GENERATED_ANYWHERE_NAMES
                or part in _SANDBOX_GENERATED_NAMES
                for part in path.relative_to(root).parts
            ):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def _markdown_link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    elif " " in target:
        # Markdown permits an optional quoted title after the destination.
        target = target.split(None, 1)[0]
    return unquote(target.split("#", 1)[0].split("?", 1)[0]).strip()


def _documentation_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_documentation_files(root):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        for line_number, line in enumerate(lines, start=1):
            for match in _MARKDOWN_LINK_RE.finditer(line):
                target = _markdown_link_target(match.group(1))
                if not target or target.startswith(
                    ("#", "http://", "https://", "mailto:", "data:")
                ):
                    continue
                destination = Path(target)
                if not destination.is_absolute():
                    destination = path.parent / destination
                if destination.exists():
                    continue
                findings.append(
                    _finding(
                        "DOCUMENT_LINK_MISSING",
                        root,
                        path,
                        f"Markdown link target does not exist: {target!r}.",
                        "Update the link to a maintained local document or remove it.",
                        line=line_number,
                        details={"target": target},
                    )
                )
        for token in _REMOVED_DOCUMENT_TOKENS:
            if token not in source:
                continue
            line_number = source[: source.index(token)].count("\n") + 1
            findings.append(
                _finding(
                    "REMOVED_DOCUMENT_REFERENCE",
                    root,
                    path,
                    f"Documentation still references removed historical plan {token!r}.",
                    "Link to the maintained topic guide instead of a completed plan.",
                    line=line_number,
                    details={"token": token},
                )
            )
        for token, fix in _STALE_DOCUMENT_TOKENS.items():
            if token not in source:
                continue
            line_number = source[: source.index(token)].count("\n") + 1
            findings.append(
                _finding(
                    "STALE_DOCUMENTATION",
                    root,
                    path,
                    f"Documentation contains obsolete token {token!r}.",
                    fix,
                    line=line_number,
                    details={"token": token},
                )
            )
        for command_kind, pattern, allowed_commands in _DOCUMENT_COMMAND_PATTERNS:
            for match in pattern.finditer(source):
                command = match.group(1)
                if command in allowed_commands:
                    continue
                line_number = source[: match.start(1)].count("\n") + 1
                findings.append(
                    _finding(
                        "STALE_DOCUMENT_COMMAND",
                        root,
                        path,
                        f"Documentation uses unknown {command_kind} command {command!r}.",
                        "Replace it with a command exposed by the current 0.10 CLI or remove the example.",
                        line=line_number,
                        details={"command": command, "kind": command_kind},
                    )
                )
    return findings


def check_base(root: Path, *, node_executable: str | None = None) -> list[Finding]:
    del node_executable
    findings: list[Finding] = []
    for path in _iter_source_python(root):
        _, parse_findings = parse_python(path, root)
        findings.extend(parse_findings)

    package_root = root / "src" / "vibeflow"
    for relative in _REQUIRED_DIRECTORIES:
        directory = root / relative
        if not directory.is_dir():
            findings.append(
                _finding(
                    "MISSING_CANONICAL_DIRECTORY",
                    root,
                    directory,
                    f"Required canonical directory {relative!r} is missing.",
                    "Create the directory in its documented layer and place the owned implementation or tests there.",
                )
            )
    for relative in _LEGACY_REPOSITORY_PATHS:
        path = root / relative
        if path.exists() or path.is_symlink():
            findings.append(
                _finding(
                    "LEGACY_REPOSITORY_PATH",
                    root,
                    path,
                    f"Legacy repository path {relative!r} remains.",
                    "Move any still-needed content to the canonical layer and remove this path.",
                )
            )
    for name in sorted(_LEGACY_PACKAGE_DIRS):
        directory = package_root / name
        if directory.exists():
            findings.append(
                _finding(
                    "LEGACY_PACKAGE",
                    root,
                    directory,
                    f"Legacy package directory {name!r} remains in the canonical source tree.",
                    "Move its implementation to Core, a Target, or Tooling and remove the compatibility package.",
                )
            )
    if package_root.is_dir():
        init_path = package_root / "__init__.py"
        init_tree, init_findings = parse_python(init_path, root)
        findings.extend(init_findings)
        if init_tree is not None:
            for node in init_tree.body:
                forbidden = isinstance(
                    node,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                )
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        imported = [alias.name for alias in node.names]
                    else:
                        imported = [node.module or ""]
                    forbidden = any(
                        name == "vibeflow" or name.startswith("vibeflow.")
                        for name in imported
                    )
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = (
                        node.targets if isinstance(node, ast.Assign) else [node.target]
                    )
                    public_names = {
                        target.id
                        for target in targets
                        if isinstance(target, ast.Name)
                        and not target.id.startswith("_")
                    }
                    forbidden = forbidden or bool(public_names)
                if forbidden:
                    findings.append(
                        _finding(
                            "ROOT_API_EXPORT",
                            root,
                            init_path,
                            "The vibeflow root package still defines or imports business API.",
                            "Keep the root package empty and import APIs from their owning layer.",
                            line=getattr(node, "lineno", 1),
                        )
                    )
        for path in sorted(package_root.glob("*.py")):
            if path.name not in {"__init__.py", "__main__.py"}:
                findings.append(
                    _finding(
                        "ROOT_BUSINESS_MODULE",
                        root,
                        path,
                        "Business code remains at the vibeflow package root.",
                        "Move the module to its owning layer and update imports.",
                    )
                )
    for relative_root, legacy_names in _LEGACY_LAYER_DIRS.items():
        layer_root = root / relative_root
        for name in sorted(legacy_names):
            directory = layer_root / name
            if not directory.exists():
                continue
            findings.append(
                _finding(
                    "LEGACY_LAYER_PACKAGE",
                    root,
                    directory,
                    f"Legacy layer package {relative_root}/{name} remains.",
                    "Move the implementation into the canonical owning subpackage.",
                )
            )
    for relative_root in _LAYER_ROOTS_WITH_INIT_ONLY:
        layer_root = root / relative_root
        if not layer_root.is_dir():
            continue
        for path in sorted(layer_root.glob("*.py")):
            if path.name != "__init__.py":
                findings.append(
                    _finding(
                        "LAYER_ROOT_BUSINESS_MODULE",
                        root,
                        path,
                        f"Business module remains at the root of {relative_root}.",
                        "Move it to the owning project, frontend, build, quality, runtime, or presentation subpackage.",
                    )
                )
    for path in sorted(set(_generated_paths(root))):
        findings.append(
            _finding(
                "GENERATED_ARTIFACT",
                root,
                path,
                "Generated or temporary content is present in the source repository.",
                "Remove it with the repository cleanup command; rebuild only in a temporary output directory.",
            )
        )
    # Target-specific application entry points are checked with their Target.
    # Every other Tooling/CLI module must remain target-neutral, including
    # dependencies reached through other neutral helpers.
    graph = build_import_graph(root)
    findings.extend(scan_layer(root, "tooling", graph=graph))
    findings.extend(neutral_tooling_findings(root, graph))
    findings.extend(_documentation_findings(root))
    return findings


def _node_command(node_executable: str | None) -> str:
    if node_executable:
        candidate = Path(node_executable)
        if candidate.is_file():
            return str(candidate)
        resolved = shutil.which(node_executable)
        if resolved:
            return resolved
        raise RepositoryCheckError(f"Node.js executable not found: {node_executable}")
    resolved = shutil.which("node")
    if not resolved:
        raise RepositoryCheckError("JavaScript profile requires Node.js 22 or newer")
    return resolved


def _node_version(command: str) -> int:
    try:
        result = subprocess.run(
            [command, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RepositoryCheckError(f"cannot execute Node.js: {exc}") from exc
    match = re.search(r"v?(\d+)", result.stdout.strip())
    if result.returncode != 0 or match is None:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RepositoryCheckError(f"cannot determine Node.js version: {detail}")
    major = int(match.group(1))
    if major < 22:
        raise RepositoryCheckError(
            f"JavaScript profile requires Node.js >=22; found {result.stdout.strip()}"
        )
    return major


def _check_mjs(root: Path, node_executable: str | None) -> list[Finding]:
    command = _node_command(node_executable)
    major = _node_version(command)
    resource_root = root / "src" / "vibeflow" / "targets" / "javascript"
    findings: list[Finding] = []
    for path in sorted(resource_root.rglob("*.mjs")) if resource_root.is_dir() else ():
        try:
            result = subprocess.run(
                [command, "--check", str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RepositoryCheckError(f"Node.js syntax check failed to run: {exc}") from exc
        if result.returncode == 0:
            continue
        output = (result.stderr or result.stdout).strip()
        line_match = re.search(rf"{re.escape(str(path))}:(\d+)", output)
        line = int(line_match.group(1)) if line_match else 1
        findings.append(
            _finding(
                "JS_SYNTAX",
                root,
                path,
                "Node.js rejected this JavaScript module.",
                "Correct the module so `node --check` succeeds on supported Node versions.",
                line=line,
                details={"node_major": major, "diagnostic": output},
            )
        )
    return findings


def check_core(root: Path, *, node_executable: str | None = None) -> list[Finding]:
    del node_executable
    graph = build_import_graph(root)
    return scan_layer(root, "core", graph=graph)


def check_block_compiler(
    root: Path, *, node_executable: str | None = None
) -> list[Finding]:
    del node_executable
    graph = build_import_graph(root)
    return scan_layer(root, "block-compiler", graph=graph)


def check_python_target(
    root: Path, *, node_executable: str | None = None
) -> list[Finding]:
    del node_executable
    graph = build_import_graph(root)
    return (
        scan_layer(root, "python-target", graph=graph)
        + python_application_findings(root, graph)
    )


def check_javascript_target(
    root: Path, *, node_executable: str | None = None
) -> list[Finding]:
    graph = build_import_graph(root)
    return (
        scan_layer(root, "javascript-target", graph=graph)
        + javascript_application_findings(root, graph)
        + _check_mjs(root, node_executable)
    )


_CHECKS: dict[str, Callable[..., list[Finding]]] = {
    "base": check_base,
    "core": check_core,
    "block-compiler": check_block_compiler,
    "python-target": check_python_target,
    "javascript-target": check_javascript_target,
}


def _validate_repository(root: Path) -> Path:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise RepositoryCheckError(f"repository root is not a directory: {root}")
    if not (resolved / "src" / "vibeflow").is_dir():
        raise RepositoryCheckError(
            f"repository root does not contain src/vibeflow: {resolved}"
        )
    return resolved


def run_profile(
    root: Path,
    profile: str,
    *,
    node_executable: str | None = None,
) -> Report:
    if profile not in PROFILE_NAMES:
        raise RepositoryCheckError(
            f"unknown profile {profile!r}; expected one of {', '.join(PROFILE_NAMES)}"
        )
    resolved = _validate_repository(root)
    names = tuple(_CHECKS) if profile == "all" else (profile,)
    findings: list[Finding] = []
    for name in names:
        findings.extend(
            _CHECKS[name](resolved, node_executable=node_executable)
        )
    return make_report(profile, findings)


__all__ = [
    "PROFILE_NAMES",
    "RepositoryCheckError",
    "check_base",
    "check_block_compiler",
    "check_core",
    "check_javascript_target",
    "check_python_target",
    "run_profile",
]
