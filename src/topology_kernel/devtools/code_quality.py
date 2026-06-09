from __future__ import annotations

import ast
import copy
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .code_quality_duplicates import duplicate_function_findings
from .code_quality_format import format_quality_summary
from .code_quality_types import (
    BRANCH_NODES,
    DEFAULT_EXCLUDED_DIRS,
    SIDE_EFFECT_ATTR_CALLS,
    SIDE_EFFECT_CALLS,
    SIDE_EFFECT_IMPORT_ROOTS,
    FileQuality,
    FunctionQuality,
    QualityFinding,
    QualityReport,
    QualityThresholds,
)


def scan_code_quality(
    root: Path | str,
    *,
    thresholds: QualityThresholds | None = None,
    excluded_dirs: Iterable[str] = DEFAULT_EXCLUDED_DIRS,
) -> QualityReport:
    resolved_root = Path(root).resolve()
    active_thresholds = thresholds or QualityThresholds()
    excluded = set(excluded_dirs)
    files = []
    findings: list[QualityFinding] = []

    for path in _iter_python_files(resolved_root, excluded):
        file_report, file_findings = _analyze_file(resolved_root, path, active_thresholds)
        files.append(file_report)
        findings.extend(file_findings)

    modules = {file.module for file in files}
    dependency_graph = _build_dependency_graph(files, modules)
    dependency_findings, longest_chain = _dependency_findings(dependency_graph, active_thresholds)
    findings.extend(dependency_findings)
    findings.extend(duplicate_function_findings(tuple(files)))

    has_error = any(finding.severity == "error" for finding in findings)
    status = "FAIL" if has_error else ("CONCERNS" if findings else "PASS")
    return QualityReport(
        status=status,
        root=str(resolved_root),
        thresholds=active_thresholds,
        files=tuple(sorted(files, key=lambda item: item.path)),
        dependency_graph=dependency_graph,
        longest_dependency_chain=tuple(longest_chain),
        findings=tuple(findings),
    )


def _iter_python_files(root: Path, excluded_dirs: set[str]) -> Iterable[Path]:
    if root.is_file() and root.suffix == ".py":
        yield root
        return
    for path in root.rglob("*.py"):
        if any(part in excluded_dirs for part in path.relative_to(root).parts):
            continue
        yield path


def _analyze_file(root: Path, path: Path, thresholds: QualityThresholds) -> tuple[FileQuality, list[QualityFinding]]:
    text = path.read_text(encoding="utf-8")
    byte_count = len(text.encode("utf-8"))
    line_count = len(text.splitlines())
    module = _module_name(root, path)
    rel_path = str(path.relative_to(root))
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return _syntax_error_file_result(path, rel_path, module, line_count, byte_count, exc)

    functions = tuple(_collect_functions(tree))
    function_count = sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree))
    class_count = sum(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
    public_api_count = sum(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
        for node in tree.body
    )
    branches, nesting = _branch_and_nesting(tree)
    imports = tuple(sorted(_collect_imports(module, tree)))
    findings = [
        *_file_shape_findings(path, rel_path, line_count, byte_count, function_count, class_count, public_api_count, thresholds),
        *_function_shape_findings(path, rel_path, functions, thresholds),
        *_side_effect_findings(module, rel_path, path, tree),
    ]
    return (
        FileQuality(
            path=rel_path,
            module=module,
            lines=line_count,
            bytes=byte_count,
            function_count=function_count,
            class_count=class_count,
            public_api_count=public_api_count,
            branch_count=branches,
            max_nesting_depth=nesting,
            imports=imports,
            functions=functions,
        ),
        findings,
    )


def _syntax_error_file_result(path: Path, rel_path: str, module: str, line_count: int, byte_count: int, exc: SyntaxError) -> tuple[FileQuality, list[QualityFinding]]:
    file_report = FileQuality(
        path=rel_path,
        module=module,
        lines=line_count,
        bytes=byte_count,
        function_count=0,
        class_count=0,
        public_api_count=0,
        branch_count=0,
        max_nesting_depth=0,
        imports=(),
        functions=(),
    )
    finding = QualityFinding(
        rule_id="QUALITY.SYNTAX.PYTHON",
        severity="error",
        object_type="file",
        object_id=rel_path,
        source_location={"path": str(path), "line": exc.lineno or 1, "column": exc.offset or 1},
        message=str(exc),
        suggested_fix_type="fix_syntax",
    )
    return file_report, [finding]


def _file_shape_findings(
    path: Path,
    rel_path: str,
    line_count: int,
    byte_count: int,
    function_count: int,
    class_count: int,
    public_api_count: int,
    thresholds: QualityThresholds,
) -> list[QualityFinding]:
    checks = [
        (line_count > thresholds.max_file_lines, "QUALITY.FILE.MAX_LINES", "error", f"file has {line_count} lines"),
        (line_count >= thresholds.warn_file_lines, "QUALITY.FILE.WARN_LINES", "warning", f"file has {line_count} lines"),
        (byte_count > thresholds.max_file_bytes, "QUALITY.FILE.MAX_BYTES", "error", f"file has {byte_count} bytes"),
        (function_count > thresholds.max_functions_per_file, "QUALITY.FILE.TOO_MANY_FUNCTIONS", "warning", f"file has {function_count} functions"),
        (class_count > thresholds.max_classes_per_file, "QUALITY.FILE.TOO_MANY_CLASSES", "warning", f"file has {class_count} classes"),
        (public_api_count > thresholds.max_public_api_per_file, "QUALITY.FILE.TOO_WIDE_PUBLIC_API", "warning", f"file exposes {public_api_count} public top-level objects"),
    ]
    findings = []
    for matched, rule_id, severity, message in checks:
        if matched and (rule_id != "QUALITY.FILE.WARN_LINES" or line_count <= thresholds.max_file_lines):
            findings.append(_finding(rule_id, severity, "file", rel_path, path, 1, message))
    return findings


def _function_shape_findings(path: Path, rel_path: str, functions: tuple[FunctionQuality, ...], thresholds: QualityThresholds) -> list[QualityFinding]:
    findings = []
    for function in functions:
        object_id = f"{rel_path}:{function.qualname}"
        if function.lines > thresholds.max_function_lines:
            findings.append(_finding("QUALITY.FUNCTION.MAX_LINES", "warning", "function", object_id, path, function.line_start, f"function has {function.lines} lines"))
        if function.branches > thresholds.max_function_branches:
            findings.append(_finding("QUALITY.FUNCTION.TOO_MANY_BRANCHES", "warning", "function", object_id, path, function.line_start, f"function has {function.branches} branches"))
        if function.max_nesting_depth > thresholds.max_function_nesting:
            findings.append(_finding("QUALITY.FUNCTION.TOO_DEEP_NESTING", "warning", "function", object_id, path, function.line_start, f"function nesting depth is {function.max_nesting_depth}"))
    return findings


def _collect_functions(tree: ast.AST) -> Iterable[FunctionQuality]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = getattr(node, "lineno", 1)
            end = getattr(node, "end_lineno", start)
            branches, nesting = _branch_and_nesting(node)
            yield FunctionQuality(
                qualname=node.name,
                line_start=start,
                line_end=end,
                lines=max(1, end - start + 1),
                branches=branches,
                max_nesting_depth=nesting,
                ast_fingerprint=_fingerprint_function(node),
            )


def _branch_and_nesting(tree: ast.AST) -> tuple[int, int]:
    visitor = _BranchVisitor()
    visitor.visit(tree)
    return visitor.branches, visitor.max_depth


class _BranchVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.branches = 0
        self.depth = 0
        self.max_depth = 0

    def generic_visit(self, node: ast.AST) -> Any:
        if isinstance(node, BRANCH_NODES):
            self.branches += 1
            self.depth += 1
            self.max_depth = max(self.max_depth, self.depth)
            super().generic_visit(node)
            self.depth -= 1
            return None
        return super().generic_visit(node)


def _collect_imports(module: str, tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in getattr(tree, "body", ()):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative_import(module, node.module, node.level) if node.level else node.module
            if base:
                imports.add(base)
                imports.update(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
    return imports


def _build_dependency_graph(files: Sequence[FileQuality], modules: set[str]) -> dict[str, tuple[str, ...]]:
    graph: dict[str, tuple[str, ...]] = {}
    for file in files:
        resolved = set()
        for imported in file.imports:
            candidate = _resolve_internal_import(imported, modules)
            if candidate and candidate != file.module:
                resolved.add(candidate)
        graph[file.module] = tuple(sorted(resolved))
    return graph


def _dependency_findings(graph: Mapping[str, Sequence[str]], thresholds: QualityThresholds) -> tuple[list[QualityFinding], list[str]]:
    findings: list[QualityFinding] = []
    longest = _longest_acyclic_chain(graph)
    if len(longest) > thresholds.max_dependency_chain:
        findings.append(QualityFinding("QUALITY.DEPENDENCY.CHAIN_TOO_DEEP", "error", "dependency_chain", " -> ".join(longest), f"dependency chain length is {len(longest)}", suggested_fix_type="split_module", details={"chain": longest}))
    elif len(longest) >= thresholds.warn_dependency_chain:
        findings.append(QualityFinding("QUALITY.DEPENDENCY.CHAIN_WARN", "warning", "dependency_chain", " -> ".join(longest), f"dependency chain length is {len(longest)}", suggested_fix_type="split_module", details={"chain": longest}))

    for cycle in _cycles(graph):
        findings.append(QualityFinding("QUALITY.DEPENDENCY.CYCLE", "error", "dependency_cycle", " -> ".join(cycle), "module import cycle detected", suggested_fix_type="break_dependency", details={"cycle": cycle}))
    for source, targets in graph.items():
        for target in targets:
            if source in graph.get(target, ()) and source < target:
                findings.append(QualityFinding("QUALITY.DEPENDENCY.BIDIRECTIONAL", "error", "dependency_pair", f"{source} <-> {target}", "bidirectional module dependency detected", suggested_fix_type="break_dependency"))
    return findings, longest


def _side_effect_findings(module: str, rel_path: str, path: Path, tree: ast.AST) -> list[QualityFinding]:
    findings = []
    aliases = _import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            findings.extend(_side_effect_import_findings(module, path, node))
            continue
        if isinstance(node, ast.Call):
            findings.extend(_side_effect_call_findings(rel_path, path, node, aliases))
    return findings

def _side_effect_import_findings(module: str, path: Path, node: ast.Import | ast.ImportFrom) -> list[QualityFinding]:
    findings = []
    for root in _side_effect_import_roots(node):
        if root in SIDE_EFFECT_IMPORT_ROOTS:
            findings.append(_finding("QUALITY.SIDE_EFFECT.IMPORT", "warning", "module", module, path, getattr(node, "lineno", 1), f"imports side-effect capable module {root}", "isolate_side_effect"))
    return findings


def _side_effect_call_findings(rel_path: str, path: Path, node: ast.Call, aliases: Mapping[str, str]) -> list[QualityFinding]:
    call_name = _call_name(node.func, aliases)
    if call_name in SIDE_EFFECT_CALLS or any(call_name == banned or call_name.startswith(f"{banned}.") for banned in SIDE_EFFECT_ATTR_CALLS):
        return [_finding("QUALITY.SIDE_EFFECT.CALL", "warning", "file", rel_path, path, getattr(node, "lineno", 1), f"calls side-effect capable API {call_name}", "isolate_side_effect")]
    return []


def _side_effect_import_roots(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    roots = [alias.name.split(".", 1)[0] for alias in getattr(node, "names", ())]
    if isinstance(node, ast.ImportFrom) and node.module:
        roots.append(node.module.split(".", 1)[0])
    return tuple(roots)

def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases = {"Path": "pathlib.Path"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases.update(_import_aliases_from_import(node))
        elif isinstance(node, ast.ImportFrom) and node.module:
            aliases.update(_import_aliases_from_import_from(node))
    return aliases


def _import_aliases_from_import(node: ast.Import) -> dict[str, str]:
    return {alias.asname or alias.name.split(".", 1)[0]: alias.name for alias in node.names}


def _import_aliases_from_import_from(node: ast.ImportFrom) -> dict[str, str]:
    if not node.module:
        return {}
    return {alias.asname or alias.name: f"{node.module}.{alias.name}" for alias in node.names}


def _call_name(func: ast.AST, aliases: Mapping[str, str]) -> str:
    if isinstance(func, ast.Name):
        return aliases.get(func.id, func.id)
    if isinstance(func, ast.Attribute):
        return f"{_call_name(func.value, aliases)}.{func.attr}"
    return "<dynamic>"


def _fingerprint_function(node: ast.AST) -> str:
    class Normalizer(ast.NodeTransformer):
        def visit_FunctionDef(self, function: ast.FunctionDef) -> ast.AST:
            function.name = "_function"
            self.generic_visit(function)
            return function

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Name(self, name: ast.Name) -> ast.AST:
            return ast.copy_location(ast.Name(id="_name", ctx=name.ctx), name)

        def visit_arg(self, arg: ast.arg) -> ast.AST:
            return ast.copy_location(ast.arg(arg="_arg", annotation=None, type_comment=None), arg)

        def visit_Constant(self, constant: ast.Constant) -> ast.AST:
            return ast.copy_location(ast.Constant(value="_constant"), constant)

    clone = Normalizer().visit(ast.fix_missing_locations(copy.deepcopy(node)))
    ast.fix_missing_locations(clone)
    return ast.dump(clone, include_attributes=False)


def _module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or path.stem


def _resolve_relative_import(module: str, imported: str | None, level: int) -> str | None:
    parts = module.split(".")
    base = parts[: max(0, len(parts) - level)]
    if imported:
        base.extend(imported.split("."))
    return ".".join(part for part in base if part)


def _resolve_internal_import(imported: str, modules: set[str]) -> str | None:
    if imported in modules:
        return imported
    parts = imported.split(".")
    while len(parts) > 1:
        parts.pop()
        candidate = ".".join(parts)
        if candidate in modules:
            return candidate
    return None


def _longest_acyclic_chain(graph: Mapping[str, Sequence[str]]) -> list[str]:
    best: list[str] = []

    def visit(node: str, path: list[str]) -> None:
        nonlocal best
        if node in path:
            return
        next_path = [*path, node]
        if len(next_path) > len(best):
            best = next_path
        for target in graph.get(node, ()):
            visit(target, next_path)

    for node in graph:
        visit(node, [])
    return best


def _cycles(graph: Mapping[str, Sequence[str]]) -> list[list[str]]:
    found: set[tuple[str, ...]] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in path:
            cycle = path[path.index(node) :] + [node]
            found.add(tuple(cycle))
            return
        for target in graph.get(node, ()):
            visit(target, [*path, node])

    for node in graph:
        visit(node, [])
    return [list(cycle) for cycle in sorted(found)]


def _finding(
    rule_id: str,
    severity: str,
    object_type: str,
    object_id: str,
    path: Path,
    line: int,
    message: str,
    suggested_fix_type: str = "refactor",
) -> QualityFinding:
    return QualityFinding(
        rule_id=rule_id,
        severity=severity,
        object_type=object_type,
        object_id=object_id,
        source_location={"path": str(path), "line": line},
        message=message,
        suggested_fix_type=suggested_fix_type,
    )
