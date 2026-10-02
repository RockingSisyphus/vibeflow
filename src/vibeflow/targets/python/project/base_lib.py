"""Python ``base_lib`` source, dependency, and project-file analysis."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Mapping

from vibeflow.core.quality.implementation import (
    ImplementationLimits,
    ImplementationMetrics,
    evaluate_base_lib_implementation,
)
from vibeflow.targets.python.project.base_lib_types import (
    BaseLibDependencySummary,
    BaseLibFinding,
    BaseLibModuleReport,
    BaseLibScanReport,
)
from vibeflow.targets.python.project.node import EFFECT_SCOPE_NONE
from vibeflow.targets.python.quality.source_analysis.ast_rules import (
    boolop_branch_count,
    import_aliases_from_node,
    imported_module_roots,
    import_modules,
    module_assignment_is_allowed,
    module_matches,
    module_statement_kind,
    record_assignment_aliases,
)
from vibeflow.targets.python.quality.source_analysis.effects import (
    call_violation,
    dynamic_namespace_reference,
    import_violation_code,
    process_argv_import_is_forbidden,
    process_argv_reference,
    system_exit_is_forbidden,
    system_exit_reference,
)
from vibeflow.targets.python.quality.source_analysis.types import PurityPolicy


FORBIDDEN_PROJECT_IMPORT_PARTS = {
    "boundary", "boundaries", "nodes", "plugin", "plugins", "runtime",
}


def analyze_base_lib_source(
    source_text: str,
    *,
    module: str,
    path: str,
    policy: PurityPolicy | None = None,
) -> BaseLibModuleReport:
    """Analyze one already-loaded base_lib module."""

    policy = policy or PurityPolicy()
    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        return BaseLibModuleReport(
            module=module,
            path=path,
            source_lines=len(source_text.splitlines()),
            source_bytes=len(source_text.encode("utf-8")),
            function_count=0,
            branch_count=0,
            max_nesting_depth=0,
            imports=(),
            findings=(
                _finding(
                    "BASE_LIB.SYNTAX",
                    str(exc),
                    path=path,
                    module=module,
                    line=exc.lineno,
                    column=exc.offset,
                ),
            ),
        )

    counter = _ComplexityCounter()
    counter.visit(tree)
    from vibeflow.core.rules import RuleContext, compile_ruleset, execute_rule_plan
    from vibeflow.core.rules.builtin import builtin_rule_resources
    from vibeflow.targets.python.quality.rules import python_rule_handlers
    from vibeflow.targets.python.quality.source_context import PythonSourceFile
    rules, rulesets = builtin_rule_resources()
    plan = compile_ruleset("vibeflow.base_lib", rules={item.id:item for item in rules},
        rulesets={item.id:item for item in rulesets}, entrypoint="static")
    context = RuleContext(facts={"base_lib_file":PythonSourceFile(path,module,source_text,_tree=tree),"purity_policy":policy},
        subject={"kind":"base_lib","id":module,"source_identity":("python",path,source_text)},target="python")
    result = execute_rule_plan(plan,context,handlers=python_rule_handlers())
    findings = tuple(BaseLibFinding(rule_id=item.code,message=item.message,severity=item.severity,
        object_id=module,source_location=item.source_location,details=item.details) for item in result.findings)
    imports = tuple(sorted({imported for item in ast.walk(tree) if isinstance(item,(ast.Import,ast.ImportFrom)) for imported in import_modules(item)}))
    return BaseLibModuleReport(module,path,len(source_text.splitlines()),len(source_text.encode()),
        counter.function_count,counter.branch_count,counter.max_nesting_depth,imports,findings)


def build_base_lib_scan_report(
    *,
    roots: tuple[str, ...],
    modules: tuple[BaseLibModuleReport, ...],
) -> BaseLibScanReport:
    """Build dependency edges and closure findings from module reports."""

    reports = {report.module: report for report in modules}
    dependency_edges = tuple(
        (report.module, resolved)
        for report in modules
        for imported in report.imports
        for resolved in (_resolve_base_lib_import(imported, reports),)
        if resolved
    )
    findings = [finding for report in modules for finding in report.findings]
    findings.extend(_dependency_closure_findings(reports, dependency_edges))
    return BaseLibScanReport(
        roots=roots,
        modules=modules,
        dependency_edges=dependency_edges,
        findings=tuple(findings),
    )


def summarize_base_lib_dependency_chain(
    imported_modules: tuple[str, ...],
    report: BaseLibScanReport,
) -> BaseLibDependencySummary:
    module_reports = {module.module: module for module in report.modules}
    edges: dict[str, set[str]] = {}
    for source, target in report.dependency_edges:
        edges.setdefault(source, set()).add(target)

    starts = tuple(
        dict.fromkeys(
            resolved or imported
            for imported in imported_modules
            for resolved in (_resolve_base_lib_import(imported, module_reports),)
        )
    )
    from vibeflow.core.quality.implementation import analyze_call_graph

    graph = {module: tuple(targets) for module, targets in edges.items()}
    for module in (*module_reports, *starts):
        graph.setdefault(module, ())
    graph["node"] = starts
    chain = analyze_call_graph(graph, entry="node") if starts else None
    return BaseLibDependencySummary(
        imported_modules=starts,
        longest_chain_length=chain.length if chain else 0,
        longest_chain=chain.path if chain else (),
        recursive_chains=chain.recursive_paths if chain else (),
    )


def base_lib_imports_from_source(source_text: str) -> tuple[str, ...]:
    """Return base_lib imports from already-loaded Python source."""

    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return ()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(
                alias.name for alias in node.names if _is_base_lib_module(alias.name)
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and _is_base_lib_module(node.module)
        ):
            imports.add(node.module)
    return tuple(sorted(imports))


def scan_base_lib(
    project_root: Path,
    *,
    policy: PurityPolicy | None = None,
) -> BaseLibScanReport:
    """Discover and analyze Python base_lib files for one project root."""

    policy = policy or PurityPolicy()
    roots = _discover_roots(project_root, policy=policy)
    reports = tuple(
        analyze_base_lib_source(
            path.read_text(encoding="utf-8"),
            module=_module_name(path, root=root),
            path=str(path),
            policy=policy,
        )
        for root in roots
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    )
    return build_base_lib_scan_report(
        roots=tuple(str(root) for root in roots),
        modules=reports,
    )


def node_base_lib_imports(node_cls: type) -> tuple[str, ...]:
    """Read a registered Python node and return its base_lib imports."""

    path = Path(inspect.getsourcefile(node_cls) or "")
    if not path.exists():
        return ()
    return base_lib_imports_from_source(path.read_text(encoding="utf-8"))


def _discover_roots(
    project_root: Path,
    *,
    policy: PurityPolicy,
) -> tuple[Path, ...]:
    roots: list[Path] = []
    for value in policy.allowed_base_lib_paths:
        path = Path(value)
        if not path.is_absolute():
            path = project_root / path
        if path.exists() and path.is_dir():
            roots.append(path.resolve())
    default = project_root / "base_lib"
    if not roots and default.exists() and default.is_dir():
        roots.append(default.resolve())
    return tuple(dict.fromkeys(roots))


def _module_name(path: Path, *, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = tuple(part for part in rel.parts if part != "__init__")
    prefix = root.name if root.name else "base_lib"
    return ".".join((prefix, *parts)) if parts else prefix


class _ComplexityCounter(ast.NodeVisitor):
    def __init__(self) -> None:
        self.function_count = 0
        self.branch_count = 0
        self.max_nesting_depth = 0
        self._nesting = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_count += 1
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_If(self, node: ast.If) -> None:
        self._branch(node)

    def visit_For(self, node: ast.For) -> None:
        self._branch(node)

    def visit_While(self, node: ast.While) -> None:
        self._branch(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.branch_count += max(1, len(node.handlers))
        self._nested(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.branch_count += boolop_branch_count(node)
        self.generic_visit(node)

    def _branch(self, node: ast.AST) -> None:
        self.branch_count += 1
        self._nested(node)

    def _nested(self, node: ast.AST) -> None:
        self._nesting += 1
        self.max_nesting_depth = max(self.max_nesting_depth, self._nesting)
        self.generic_visit(node)
        self._nesting -= 1


def _dependency_closure_findings(
    reports: dict[str, BaseLibModuleReport],
    edges: tuple[tuple[str, str], ...],
) -> tuple[BaseLibFinding, ...]:
    bad_modules = {report.module for report in reports.values() if report.findings}
    if not bad_modules:
        return ()
    findings: list[BaseLibFinding] = []
    for source, target in edges:
        if target in bad_modules:
            report = reports[source]
            findings.append(
                _finding(
                    "BASE_LIB.DEPENDENCY_CLOSURE_VIOLATION",
                    "base_lib module depends on unhealthy base_lib module: "
                    f"{source} -> {target}",
                    path=report.path,
                    module=source,
                    details={"dependency": target},
                )
            )
    return tuple(findings)


def _resolve_base_lib_import(
    module: str,
    reports: Mapping[str, BaseLibModuleReport],
) -> str:
    if module in reports:
        return module
    for candidate in reports:
        if (
            module == candidate
            or candidate.endswith(f".{module}")
            or module.endswith(f".{candidate}")
        ):
            return candidate
    return ""


def _is_base_lib_module(module: str) -> bool:
    return "base_lib" in tuple(part for part in module.split(".") if part)


def _finding(
    rule_id: str,
    message: str,
    *,
    path: str,
    module: str,
    line: int | None = None,
    column: int | None = None,
    details: Mapping[str, object] | None = None,
) -> BaseLibFinding:
    location: dict[str, object] = {"path": path}
    if line is not None:
        location["line"] = line
    if column is not None:
        location["column"] = column
    return BaseLibFinding(
        rule_id=rule_id,
        message=message,
        object_id=module,
        source_location=location,
        details=details or {},
    )


__all__ = [
    "analyze_base_lib_source", "base_lib_imports_from_source",
    "build_base_lib_scan_report", "node_base_lib_imports", "scan_base_lib",
    "summarize_base_lib_dependency_chain",
]
