from __future__ import annotations

import ast
import inspect
from pathlib import Path

from vibeflow.purity.ast_rules import (
    boolop_branch_count,
    import_aliases_from_node,
    import_modules,
    module_assignment_is_allowed,
    module_matches,
    module_statement_kind,
)
from vibeflow.base_lib_types import BaseLibDependencySummary, BaseLibFinding, BaseLibModuleReport, BaseLibScanReport
from vibeflow.node import EFFECT_SCOPE_NONE
from vibeflow.purity.effects import (
    call_violation,
    import_violation_code,
    process_argv_import_is_forbidden,
    process_argv_reference,
    system_exit_is_forbidden,
    system_exit_reference,
)
from vibeflow.purity.types import PurityPolicy


FORBIDDEN_PROJECT_IMPORT_PARTS = {"boundary", "boundaries", "nodes", "plugin", "plugins", "runtime"}


def scan_base_lib(project_root: Path, *, policy: PurityPolicy | None = None) -> BaseLibScanReport:
    policy = policy or PurityPolicy()
    roots = _discover_roots(project_root, policy=policy)
    module_reports: list[BaseLibModuleReport] = []
    module_to_report: dict[str, BaseLibModuleReport] = {}
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            report = _scan_file(path, root=root, policy=policy)
            module_reports.append(report)
            module_to_report[report.module] = report

    dependency_edges: list[tuple[str, str]] = []
    for report in module_reports:
        for imported in report.imports:
            resolved = _resolve_base_lib_import(imported, module_to_report)
            if resolved:
                dependency_edges.append((report.module, resolved))

    findings = [finding for report in module_reports for finding in report.findings]
    findings.extend(_dependency_closure_findings(module_to_report, tuple(dependency_edges)))
    return BaseLibScanReport(
        roots=tuple(str(root) for root in roots),
        modules=tuple(module_reports),
        dependency_edges=tuple(dependency_edges),
        findings=tuple(findings),
    )


def summarize_base_lib_dependency_chain(imported_modules: tuple[str, ...], report: BaseLibScanReport) -> BaseLibDependencySummary:
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
    best_chain: tuple[str, ...] = ()
    recursive_chains: list[tuple[str, ...]] = []

    def dfs(module: str, path: tuple[str, ...]) -> None:
        nonlocal best_chain
        if len(path) > len(best_chain):
            best_chain = path
        for target in sorted(edges.get(module, ())):
            if target in path:
                cycle = (*path[path.index(target):], target)
                if cycle not in recursive_chains:
                    recursive_chains.append(cycle)
                continue
            dfs(target, (*path, target))

    for start in starts:
        dfs(start, ("node", start))
    return BaseLibDependencySummary(
        imported_modules=starts,
        longest_chain_length=len(best_chain),
        longest_chain=best_chain,
        recursive_chains=tuple(recursive_chains),
    )


def node_base_lib_imports(node_cls: type) -> tuple[str, ...]:
    path = Path(inspect.getsourcefile(node_cls) or "")
    if not path.exists():
        return ()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return ()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_base_lib_module(alias.name):
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and _is_base_lib_module(node.module):
            imports.add(node.module)
    return tuple(sorted(imports))


def _discover_roots(project_root: Path, *, policy: PurityPolicy) -> tuple[Path, ...]:
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


def _scan_file(path: Path, *, root: Path, policy: PurityPolicy) -> BaseLibModuleReport:
    text = path.read_text(encoding="utf-8")
    module = _module_name(path, root=root)
    findings: list[BaseLibFinding] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return BaseLibModuleReport(
            module=module,
            path=str(path),
            source_lines=len(text.splitlines()),
            source_bytes=len(text.encode("utf-8")),
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
    scanner = _BaseLibAstScanner(path=path, module=module, policy=policy)
    counter.visit(tree)
    scanner.visit(tree)
    findings.extend(scanner.findings)
    findings.extend(_size_findings(path, module, text, policy=policy))
    findings.extend(_complexity_findings(path, module, counter, policy=policy))
    return BaseLibModuleReport(
        module=module,
        path=str(path),
        source_lines=len(text.splitlines()),
        source_bytes=len(text.encode("utf-8")),
        function_count=counter.function_count,
        branch_count=counter.branch_count,
        max_nesting_depth=counter.max_nesting_depth,
        imports=tuple(sorted(scanner.imports)),
        findings=tuple(findings),
    )


class _BaseLibAstScanner(ast.NodeVisitor):
    def __init__(self, *, path: Path, module: str, policy: PurityPolicy) -> None:
        self.path = path
        self.module = module
        self.policy = policy
        self.imports: set[str] = set()
        self.findings: list[BaseLibFinding] = []
        self.import_aliases: dict[str, str] = {"Path": "pathlib.Path"}

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            kind = module_statement_kind(stmt)
            if kind in {"import", "definition"}:
                self.visit(stmt)
            elif kind == "assignment":
                self._visit_module_assignment(stmt)
            elif kind == "docstring":
                continue
            else:
                self._add("BASE_LIB.TOP_LEVEL_SIDE_EFFECT", "base_lib top level may only contain imports, definitions, immutable constants, and docstrings", stmt)

    def visit_Import(self, node: ast.Import) -> None:
        self._check_import_node(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if process_argv_import_is_forbidden(module, {alias.name for alias in node.names}):
            self._add("BASE_LIB.BANNED_IMPORT", "base_lib must not import process sys.argv", node)
        self._check_import_node(node)

    def visit_Call(self, node: ast.Call) -> None:
        violation_code, forbidden = call_violation(
            node,
            aliases=self.import_aliases,
            effect_scope=EFFECT_SCOPE_NONE,
        )
        if violation_code:
            self._add("BASE_LIB.SIDE_EFFECT_CALL", f"base_lib banned side-effect call: {forbidden}", node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        reference = process_argv_reference(node, self.import_aliases)
        if reference:
            self._add("BASE_LIB.SIDE_EFFECT_CALL", f"base_lib banned process argument access: {reference}", node)
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if not isinstance(node.exc, ast.Call):
            reference = system_exit_reference(node.exc, self.import_aliases)
            if reference and system_exit_is_forbidden(EFFECT_SCOPE_NONE):
                self._add("BASE_LIB.SIDE_EFFECT_CALL", f"base_lib banned process exit: {reference}", node)
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        self._add("BASE_LIB.GLOBAL_STATE", "base_lib must not use global mutation", node)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self._add("BASE_LIB.GLOBAL_STATE", "base_lib must not use nonlocal mutation", node)

    def _visit_module_assignment(self, node: ast.Assign | ast.AnnAssign) -> None:
        if _is_base_lib_info_assignment(node):
            self.visit(node)
            return
        if not module_assignment_is_allowed(node):
            self._add("BASE_LIB.GLOBAL_STATE", "base_lib must not hold mutable module-level state", node)
        self.visit(node)

    def _check_import_node(self, node: ast.Import | ast.ImportFrom) -> None:
        self.import_aliases.update(import_aliases_from_node(node))
        modules = import_modules(node)
        if not modules:
            return
        for module in modules:
            self._check_import(module, node)

    def _check_import(self, module: str, node: ast.AST) -> None:
        self.imports.add(module)
        if any(part in FORBIDDEN_PROJECT_IMPORT_PARTS for part in module.split(".")):
            self._add("BASE_LIB.FORBIDDEN_PROJECT_IMPORT", f"base_lib must not import node, plugin, boundary, runtime, or side-effect layer: {module}", node)
            return
        if module_matches(module, self.policy.banned_base_lib_modules):
            self._add("BASE_LIB.BANNED_MODULE", f"base_lib module is banned by policy: {module}", node)
            return
        if import_violation_code(module, effect_scope=EFFECT_SCOPE_NONE, policy=self.policy):
            self._add("BASE_LIB.BANNED_IMPORT", f"base_lib banned import: {module}", node)

    def _add(self, rule_id: str, message: str, node: ast.AST) -> None:
        self.findings.append(
            _finding(
                rule_id,
                message,
                path=self.path,
                module=self.module,
                line=getattr(node, "lineno", None),
                column=(getattr(node, "col_offset", 0) + 1) if hasattr(node, "col_offset") else None,
            )
        )


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
        branch_delta = boolop_branch_count(node)
        self.branch_count += branch_delta
        self.generic_visit(node)

    def _branch(self, node: ast.AST) -> None:
        self.branch_count += 1
        self._nested(node)

    def _nested(self, node: ast.AST) -> None:
        self._nesting += 1
        self.max_nesting_depth = max(self.max_nesting_depth, self._nesting)
        self.generic_visit(node)
        self._nesting -= 1


def _size_findings(path: Path, module: str, text: str, *, policy: PurityPolicy) -> tuple[BaseLibFinding, ...]:
    findings: list[BaseLibFinding] = []
    lines = len(text.splitlines())
    bytes_ = len(text.encode("utf-8"))
    if lines > policy.max_source_lines:
        findings.append(_finding("BASE_LIB.SOURCE.MAX_LINES", f"base_lib file has {lines} lines > {policy.max_source_lines}", path=path, module=module, details={"lines": lines, "limit": policy.max_source_lines}))
    if bytes_ > policy.max_source_bytes:
        findings.append(_finding("BASE_LIB.SOURCE.MAX_BYTES", f"base_lib file has {bytes_} bytes > {policy.max_source_bytes}", path=path, module=module, details={"bytes": bytes_, "limit": policy.max_source_bytes}))
    return tuple(findings)


def _complexity_findings(path: Path, module: str, counter: _ComplexityCounter, *, policy: PurityPolicy) -> tuple[BaseLibFinding, ...]:
    checks = (
        ("BASE_LIB.COMPLEXITY.MAX_FUNCTIONS", policy.max_functions, counter.function_count, "function_count"),
        ("BASE_LIB.COMPLEXITY.MAX_BRANCHES", policy.max_branches, counter.branch_count, "branch_count"),
        ("BASE_LIB.COMPLEXITY.MAX_NESTING_DEPTH", policy.max_nesting_depth, counter.max_nesting_depth, "max_nesting_depth"),
    )
    findings: list[BaseLibFinding] = []
    for rule_id, limit, actual, key in checks:
        if limit is not None and actual > limit:
            findings.append(_finding(rule_id, f"base_lib {key} is {actual} > policy limit {limit}", path=path, module=module, details={key: actual, "limit": limit}))
    return tuple(findings)


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
                    f"base_lib module depends on unhealthy base_lib module: {source} -> {target}",
                    path=Path(report.path),
                    module=source,
                    details={"dependency": target},
                )
            )
    return tuple(findings)


def _resolve_base_lib_import(module: str, reports: dict[str, BaseLibModuleReport]) -> str:
    if module in reports:
        return module
    for candidate in reports:
        if module == candidate or candidate.endswith(f".{module}") or module.endswith(f".{candidate}"):
            return candidate
    return ""


def _is_base_lib_info_assignment(node: ast.Assign | ast.AnnAssign) -> bool:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    if not any(isinstance(target, ast.Name) and target.id == "BASE_LIB_INFO" for target in targets):
        return False
    value = node.value
    return isinstance(value, (ast.Call, ast.Dict))


def _module_name(path: Path, *, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = tuple(part for part in rel.parts if part != "__init__")
    prefix = root.name if root.name else "base_lib"
    return ".".join((prefix, *parts)) if parts else prefix


def _is_base_lib_module(module: str) -> bool:
    return "base_lib" in tuple(part for part in module.split(".") if part)




def _finding(
    rule_id: str,
    message: str,
    *,
    path: Path,
    module: str,
    line: int | None = None,
    column: int | None = None,
    details: Mapping[str, object] | None = None,
) -> BaseLibFinding:
    location: dict[str, object] = {"path": str(path)}
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
