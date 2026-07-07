from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .code_quality_duplicates import duplicate_function_findings
from .code_quality_format import format_quality_summary
from .code_quality_imports import (
    _build_dependency_graph,
    _collect_import_sites,
    _import_sites_by_edge,
    _module_name,
    _resolve_internal_import,
    _resolve_relative_import,
)
from .code_quality_rules import side_effect_findings
from .code_quality_root_structure import analyze_root_structure
from .code_quality_structure import analyze_directory_structure
from .code_quality_types import (
    BRANCH_NODES,
    DirectoryQuality,
    DEFAULT_EXCLUDED_DIRS,
    FileQuality,
    FunctionQuality,
    ImportSite,
    PrefixClusterQuality,
    QualityFinding,
    QualityReport,
    QualityStructureLimits,
    QualityThresholds,
    SIDE_EFFECT_BOUNDARY_PATHS,
)
@dataclass(frozen=True)
class _FileShape:
    path: Path
    rel_path: str
    line_count: int
    byte_count: int
    function_count: int
    class_count: int
    public_api_count: int
    branch_count: int
def scan_code_quality(
    root: Path | str,
    *,
    thresholds: QualityThresholds | None = None,
    structure_limits: QualityStructureLimits | None = None,
    excluded_dirs: Iterable[str] = DEFAULT_EXCLUDED_DIRS,
    check_side_effects: bool = False,
) -> QualityReport:
    resolved_root = Path(root).resolve()
    active_thresholds = thresholds or QualityThresholds()
    excluded = set(excluded_dirs)
    files = []
    findings: list[QualityFinding] = []

    for path in _iter_python_files(resolved_root, excluded):
        file_report, file_findings = _analyze_file(
            resolved_root,
            path,
            active_thresholds,
            check_side_effects=check_side_effects,
        )
        files.append(file_report)
        findings.extend(file_findings)

    modules = {file.module for file in files}
    dependency_graph = _build_dependency_graph(files, modules)
    import_sites_by_edge = _import_sites_by_edge(files, modules)
    directory_graph, prefix_clusters, structure_summary, structure_findings = analyze_directory_structure(
        files,
        dependency_graph,
        import_sites_by_edge,
        active_thresholds,
    )
    findings.extend(structure_findings)
    root_structure_summary, root_structure_findings = analyze_root_structure(
        files,
        dependency_graph,
        import_sites_by_edge,
        structure_limits,
    )
    structure_summary.update(root_structure_summary)
    findings.extend(root_structure_findings)
    dependency_findings, longest_chain = _dependency_findings(dependency_graph, import_sites_by_edge, active_thresholds)
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
        directory_graph=directory_graph,
        prefix_clusters=prefix_clusters,
        structure_summary=structure_summary,
    )
def _iter_python_files(root: Path, excluded_dirs: set[str]) -> Iterable[Path]:
    if root.is_file() and root.suffix == ".py":
        if not _skip_file(root):
            yield root
        return
    for path in root.rglob("*.py"):
        if any(part in excluded_dirs for part in path.relative_to(root).parts):
            continue
        if _skip_file(path):
            continue
        yield path


def _skip_file(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".generated.py", "_pb2.py", "_pb2_grpc.py")) or name in {"build_distribution.py", "secrets.py", "credentials.py"}


def _analyze_file(root: Path, path: Path, thresholds: QualityThresholds, *, check_side_effects: bool) -> tuple[FileQuality, list[QualityFinding]]:
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
    import_sites = _collect_import_sites(module, rel_path, tree)
    imports = tuple(sorted(site.imported for site in import_sites))
    findings = [
        *_file_shape_findings(
            _FileShape(path, rel_path, line_count, byte_count, function_count, class_count, public_api_count, branches),
            thresholds,
        ),
        *_function_shape_findings(path, rel_path, functions, thresholds),
    ]
    if check_side_effects and rel_path not in SIDE_EFFECT_BOUNDARY_PATHS:
        findings.extend(side_effect_findings(module, rel_path, path, tree))
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
            import_sites=import_sites,
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
        import_sites=(),
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


def _file_shape_findings(shape: _FileShape, thresholds: QualityThresholds) -> list[QualityFinding]:
    checks = [
        (shape.line_count > thresholds.max_file_lines, "QUALITY.FILE.MAX_LINES", "error", f"file has {shape.line_count} lines"),
        (shape.line_count >= thresholds.warn_file_lines, "QUALITY.FILE.WARN_LINES", "warning", f"file has {shape.line_count} lines"),
        (shape.byte_count > thresholds.max_file_bytes, "QUALITY.FILE.MAX_BYTES", "error", f"file has {shape.byte_count} bytes"),
        (shape.function_count > thresholds.max_functions_per_file, "QUALITY.FILE.TOO_MANY_FUNCTIONS", "warning", f"file has {shape.function_count} functions"),
        (shape.class_count > thresholds.max_classes_per_file, "QUALITY.FILE.TOO_MANY_CLASSES", "warning", f"file has {shape.class_count} classes"),
        (shape.public_api_count > thresholds.max_public_api_per_file, "QUALITY.FILE.TOO_WIDE_PUBLIC_API", "warning", f"file exposes {shape.public_api_count} public top-level objects"),
        (shape.branch_count > thresholds.max_file_branches, "QUALITY.FILE.TOO_MANY_BRANCHES", "warning", f"file has {shape.branch_count} branches"),
    ]
    findings = []
    for matched, rule_id, severity, message in checks:
        if matched and (rule_id != "QUALITY.FILE.WARN_LINES" or shape.line_count <= thresholds.max_file_lines):
            findings.append(_finding(rule_id, severity, ("file", shape.rel_path), shape.path, 1, message))
    return findings


def _function_shape_findings(path: Path, rel_path: str, functions: tuple[FunctionQuality, ...], thresholds: QualityThresholds) -> list[QualityFinding]:
    findings = []
    for function in functions:
        object_id = f"{rel_path}:{function.qualname}"
        if function.lines > thresholds.max_function_lines:
            findings.append(_finding("QUALITY.FUNCTION.MAX_LINES", "warning", ("function", object_id), path, function.line_start, f"function has {function.lines} lines"))
        if function.branches > thresholds.max_function_branches:
            findings.append(_finding("QUALITY.FUNCTION.TOO_MANY_BRANCHES", "warning", ("function", object_id), path, function.line_start, f"function has {function.branches} branches"))
        if function.max_nesting_depth > thresholds.max_function_nesting:
            findings.append(_finding("QUALITY.FUNCTION.TOO_DEEP_NESTING", "warning", ("function", object_id), path, function.line_start, f"function nesting depth is {function.max_nesting_depth}"))
        if function.param_count > thresholds.max_function_params:
            findings.append(_finding("QUALITY.FUNCTION.TOO_MANY_PARAMS", "warning", ("function", object_id), path, function.line_start, f"function has {function.param_count} parameters"))
    return findings


def _collect_functions(tree: ast.AST) -> Iterable[FunctionQuality]:
    collector = _FunctionCollector()
    collector.visit(tree)
    return tuple(collector.functions)


class _FunctionCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.functions: list[FunctionQuality] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        branches, nesting = _branch_and_nesting(node)
        self.functions.append(
            FunctionQuality(
                qualname=".".join((*self.stack, node.name)),
                line_start=start,
                line_end=end,
                lines=max(1, end - start + 1),
                branches=branches,
                max_nesting_depth=nesting,
                param_count=_param_count(node, is_method=bool(self.stack)),
                ast_fingerprint=_fingerprint_function(node),
            )
        )


def _param_count(node: ast.FunctionDef | ast.AsyncFunctionDef, *, is_method: bool) -> int:
    args = node.args
    positional = (*args.posonlyargs, *args.args)
    required_positional = len(positional) - len(args.defaults)
    required_kwonly = sum(default is None for default in args.kw_defaults)
    count = required_positional + required_kwonly + int(args.vararg is not None) + int(args.kwarg is not None)
    if is_method and positional and positional[0].arg in {"self", "cls"}:
        count -= 1
    return max(0, count)


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


def _dependency_findings(
    graph: Mapping[str, Sequence[str]],
    import_sites_by_edge: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
    thresholds: QualityThresholds,
) -> tuple[list[QualityFinding], list[str]]:
    findings: list[QualityFinding] = []
    longest = _longest_acyclic_chain(graph)
    if len(longest) > thresholds.max_dependency_chain:
        edge_import_sites = _path_edge_import_sites(longest, import_sites_by_edge)
        findings.append(
            QualityFinding(
                "QUALITY.DEPENDENCY.CHAIN_TOO_DEEP",
                "error",
                "dependency_chain",
                " -> ".join(longest),
                f"dependency chain length is {len(longest)}",
                source_location=_first_import_site_location(edge_import_sites),
                suggested_fix_type="split_module",
                details={"chain": longest, "edge_import_sites": edge_import_sites},
            )
        )
    elif len(longest) >= thresholds.warn_dependency_chain:
        edge_import_sites = _path_edge_import_sites(longest, import_sites_by_edge)
        findings.append(
            QualityFinding(
                "QUALITY.DEPENDENCY.CHAIN_WARN",
                "warning",
                "dependency_chain",
                " -> ".join(longest),
                f"dependency chain length is {len(longest)}",
                source_location=_first_import_site_location(edge_import_sites),
                suggested_fix_type="split_module",
                details={"chain": longest, "edge_import_sites": edge_import_sites},
            )
        )

    for cycle in _cycles(graph):
        edge_import_sites = _path_edge_import_sites(cycle, import_sites_by_edge)
        findings.append(
            QualityFinding(
                "QUALITY.DEPENDENCY.CYCLE",
                "error",
                "dependency_cycle",
                " -> ".join(cycle),
                "module import cycle detected",
                source_location=_first_import_site_location(edge_import_sites),
                suggested_fix_type="break_dependency",
                details={"cycle": cycle, "edge_import_sites": edge_import_sites},
            )
        )
    for source, targets in graph.items():
        for target in targets:
            if source in graph.get(target, ()) and source < target:
                findings.append(
                    QualityFinding(
                        "QUALITY.DEPENDENCY.BIDIRECTIONAL",
                        "error",
                        "dependency_pair",
                        f"{source} <-> {target}",
                        "bidirectional module dependency detected",
                        source_location=_first_import_site_location(
                            [
                                {
                                    "source": source,
                                    "target": target,
                                    "import_sites": list(import_sites_by_edge.get((source, target), ())),
                                }
                            ]
                        ),
                        suggested_fix_type="break_dependency",
                        details={
                            "source": source,
                            "target": target,
                            "forward_import_sites": list(import_sites_by_edge.get((source, target), ())),
                            "reverse_import_sites": list(import_sites_by_edge.get((target, source), ())),
                        },
                    )
                )
    return findings, longest


def _path_edge_import_sites(
    path: Sequence[str],
    import_sites_by_edge: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
) -> list[dict[str, object]]:
    return [
        {
            "source": source,
            "target": target,
            "import_sites": list(import_sites_by_edge.get((source, target), ())),
        }
        for source, target in zip(path, path[1:])
    ]


def _first_import_site_location(edge_import_sites: Sequence[Mapping[str, object]]) -> dict[str, object]:
    for edge in edge_import_sites:
        sites = edge.get("import_sites")
        if not isinstance(sites, Sequence):
            continue
        for site in sites:
            if not isinstance(site, Mapping):
                continue
            path = str(site.get("path", "")).strip()
            if not path:
                continue
            location: dict[str, object] = {"path": path}
            if site.get("line"):
                location["line"] = site["line"]
            if site.get("column"):
                location["column"] = site["column"]
            return location
    return {}


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
    target: tuple[str, str],
    path: Path,
    line: int,
    message: str,
    suggested_fix_type: str = "refactor",
) -> QualityFinding:
    object_type, object_id = target
    return QualityFinding(
        rule_id=rule_id,
        severity=severity,
        object_type=object_type,
        object_id=object_id,
        source_location={"path": str(path), "line": line},
        message=message,
        suggested_fix_type=suggested_fix_type,
    )
