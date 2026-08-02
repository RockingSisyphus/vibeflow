"""Python source and import analysis using only the standard library."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
from typing import Iterator

from .models import Finding, SourceLocation


LAYER_MODULES = {
    "core": "vibeflow.core",
    "block-compiler": "vibeflow.block_compiler",
    "python-target": "vibeflow.targets.python",
    "javascript-target": "vibeflow.targets.javascript",
    "tooling": "vibeflow.tooling",
}

LAYER_PATHS = {
    "core": Path("core"),
    "block-compiler": Path("block_compiler"),
    "python-target": Path("targets/python"),
    "javascript-target": Path("targets/javascript"),
    "tooling": Path("tooling"),
}

ALLOWED_LAYERS = {
    "core": frozenset({"core"}),
    "block-compiler": frozenset({"block-compiler", "core"}),
    "python-target": frozenset({"python-target", "block-compiler", "core"}),
    "javascript-target": frozenset(
        {"javascript-target", "block-compiler", "core"}
    ),
    "tooling": frozenset(LAYER_MODULES),
}

CORE_FORBIDDEN_MODULES = frozenset(
    {
        "asyncio.subprocess",
        "http",
        "os",
        "shutil",
        "socket",
        "subprocess",
        "tempfile",
        "urllib",
    }
)

CORE_FORBIDDEN_CALLS = frozenset(
    {
        "__import__",
        "compile",
        "eval",
        "exec",
        "open",
        "Path",
        "pathlib.Path",
        "importlib.import_module",
        "os.getenv",
        "os.system",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.run",
    }
)

CORE_FORBIDDEN_METHODS = frozenset(
    {
        "absolute",
        "exists",
        "glob",
        "is_dir",
        "is_file",
        "iterdir",
        "lstat",
        "mkdir",
        "open",
        "read_bytes",
        "read_text",
        "rename",
        "resolve",
        "rglob",
        "rmdir",
        "stat",
        "symlink_to",
        "touch",
        "unlink",
        "write_bytes",
        "write_text",
    }
)


def repository_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def iter_python_files(directory: Path) -> Iterator[Path]:
    if not directory.is_dir():
        return
    for path in sorted(directory.rglob("*.py")):
        if not any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
            yield path


def module_name(path: Path, source_root: Path) -> str:
    parts = list(path.relative_to(source_root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_module(node: ast.ImportFrom, source: str, path: Path) -> str:
    if node.level == 0:
        return node.module or ""
    package = source if path.name == "__init__.py" else source.rpartition(".")[0]
    try:
        return importlib.util.resolve_name(
            "." * node.level + (node.module or ""), package
        )
    except (ImportError, ValueError):
        return "<invalid-relative-import>"


def target_layer(module: str) -> str | None:
    for name, prefix in LAYER_MODULES.items():
        if module == prefix or module.startswith(prefix + "."):
            return name
    return None


def _root_module(module: str) -> str:
    return module.partition(".")[0]


def _stdlib(module: str) -> bool:
    root = _root_module(module)
    return root in sys.stdlib_module_names or root in sys.builtin_module_names


def parse_python(path: Path, root: Path) -> tuple[ast.Module | None, list[Finding]]:
    relative = repository_path(path, root)
    try:
        source = path.read_text(encoding="utf-8")
        return ast.parse(source, filename=relative), []
    except (OSError, UnicodeError, SyntaxError) as exc:
        line = getattr(exc, "lineno", 1) or 1
        column = getattr(exc, "offset", 0) or 0
        return None, [
            Finding(
                code="PY_SYNTAX",
                severity="error",
                subject_type="source_file",
                subject_id=relative,
                source_location=SourceLocation(relative, line, column),
                message=f"Python source cannot be parsed: {exc}",
                suggested_fix="Correct the source so Python's AST parser accepts it.",
            )
        ]


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    cursor: ast.AST = node.func
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        parts.append(cursor.id)
    return ".".join(reversed(parts))


def _import_findings(
    *,
    layer: str,
    module: str,
    path: Path,
    root: Path,
    tree: ast.Module,
) -> list[Finding]:
    findings: list[Finding] = []
    imports: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(
                (alias.name, node.lineno, node.col_offset) for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            imports.append(
                (imported_module(node, module, path), node.lineno, node.col_offset)
            )
    relative = repository_path(path, root)
    for target, line, column in imports:
        destination = target_layer(target)
        message: str | None = None
        if destination is not None and destination not in ALLOWED_LAYERS[layer]:
            message = f"{layer} may not depend on {destination}"
        elif target == "vibeflow" or target.startswith("vibeflow."):
            if destination is None:
                message = f"{layer} may not depend on a legacy or unowned VibeFlow module"
        elif layer in {"core", "block-compiler"} and not _stdlib(target):
            message = f"{layer} may use only the standard library and allowed lower layers"
        if message is not None:
            findings.append(
                Finding(
                    code="LAYER_DEPENDENCY",
                    severity="error",
                    subject_type="python_module",
                    subject_id=module,
                    source_location=SourceLocation(relative, line, column),
                    message=f"{message}: imported {target!r}.",
                    suggested_fix="Move the dependency to its owning layer or pass plain data across the boundary.",
                    details={"source_layer": layer, "target": target},
                )
            )
    return findings


def _core_side_effect_findings(
    *, module: str, path: Path, root: Path, tree: ast.Module
) -> list[Finding]:
    relative = repository_path(path, root)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                if any(
                    name == forbidden or name.startswith(forbidden + ".")
                    for forbidden in CORE_FORBIDDEN_MODULES
                ):
                    findings.append(
                        Finding(
                            code="CORE_IO_IMPORT",
                            severity="error",
                            subject_type="python_module",
                            subject_id=module,
                            source_location=SourceLocation(
                                relative, node.lineno, node.col_offset
                            ),
                            message=f"Core imports side-effect module {name!r}.",
                            suggested_fix="Move filesystem, environment, process, network, or host access into Tooling or a Target.",
                            details={"module": name},
                        )
                    )
            if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
                for alias in node.names:
                    if alias.name != "Path":
                        continue
                    findings.append(
                        Finding(
                            code="CORE_PATH_TYPE",
                            severity="error",
                            subject_type="python_module",
                            subject_id=module,
                            source_location=SourceLocation(
                                relative, node.lineno, node.col_offset
                            ),
                            message="Core imports the filesystem-bound pathlib.Path type.",
                            suggested_fix="Use PurePath for lexical path logic or pass a plain string from Tooling.",
                        )
                    )
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            method = name.rpartition(".")[2]
            if name in CORE_FORBIDDEN_CALLS or method in CORE_FORBIDDEN_METHODS:
                findings.append(
                    Finding(
                        code="CORE_IO_CALL",
                        severity="error",
                        subject_type="python_module",
                        subject_id=module,
                        source_location=SourceLocation(
                            relative, node.lineno, node.col_offset
                        ),
                        message=f"Core performs side-effecting or host-bound operation {name!r}.",
                        suggested_fix="Accept plain in-memory facts and perform this operation in Tooling or a Target.",
                        details={"call": name},
                    )
                )
        elif isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr == "environ"
            ):
                findings.append(
                    Finding(
                        code="CORE_ENV_ACCESS",
                        severity="error",
                        subject_type="python_module",
                        subject_id=module,
                        source_location=SourceLocation(
                            relative, node.lineno, node.col_offset
                        ),
                        message="Core reads or mutates the process environment.",
                        suggested_fix="Read the environment in Tooling and pass the resulting plain value to Core.",
                    )
                )
    return findings


def _subboundary_findings(
    *, layer: str, path: Path, root: Path, module: str, tree: ast.Module
) -> list[Finding]:
    relative_to_layer = path.relative_to(
        root / "src" / "vibeflow" / LAYER_PATHS[layer]
    ).as_posix()
    restricted = False
    code = ""
    message = ""
    if layer == "python-target" and relative_to_layer.startswith("quality/"):
        restricted = True
        code = "PYTHON_QUALITY_FILE_SCAN"
        message = "Python Target quality analysis may not traverse or read project files"
    elif layer == "javascript-target" and (
        relative_to_layer.startswith("quality/")
        or relative_to_layer.startswith("frontend/quality/")
    ):
        restricted = True
        code = "JAVASCRIPT_FRONTEND_PROCESS"
        message = "JavaScript frontend quality analysis may not launch processes"
    if not restricted:
        return []
    forbidden_calls = {
        "open",
        "Path",
        "pathlib.Path",
        "os.walk",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.run",
    }
    forbidden_methods = {"glob", "iterdir", "read_bytes", "read_text", "rglob"}
    relative = repository_path(path, root)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in forbidden_calls or name.rpartition(".")[2] in forbidden_methods:
            findings.append(
                Finding(
                    code=code,
                    severity="error",
                    subject_type="python_module",
                    subject_id=module,
                    source_location=SourceLocation(
                        relative, node.lineno, node.col_offset
                    ),
                    message=f"{message}: {name!r}.",
                    suggested_fix="Move this operation to the owning build/project adapter and pass plain facts inward.",
                )
            )
    return findings


def scan_layer(root: Path, layer: str) -> list[Finding]:
    source_root = root / "src"
    directory = source_root / "vibeflow" / LAYER_PATHS[layer]
    findings: list[Finding] = []
    for path in iter_python_files(directory):
        tree, parse_findings = parse_python(path, root)
        findings.extend(parse_findings)
        if tree is None:
            continue
        module = module_name(path, source_root)
        findings.extend(
            _import_findings(
                layer=layer,
                module=module,
                path=path,
                root=root,
                tree=tree,
            )
        )
        if layer == "core":
            findings.extend(
                _core_side_effect_findings(
                    module=module, path=path, root=root, tree=tree
                )
            )
        findings.extend(
            _subboundary_findings(
                layer=layer, path=path, root=root, module=module, tree=tree
            )
        )
    return findings


__all__ = [
    "LAYER_MODULES",
    "LAYER_PATHS",
    "iter_python_files",
    "parse_python",
    "repository_path",
    "scan_layer",
]
