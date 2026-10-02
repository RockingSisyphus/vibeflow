"""Python source-to-facts frontend for Core quality evaluation."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
from typing import Any

from vibeflow.core.quality import (
    FileQuality,
    FunctionQuality,
    ImportSite,
    QualityFinding,
)
from vibeflow.targets.python.quality.source_analysis.ast_rules import (
    import_aliases,
    import_roots,
    path_effect_call_name,
    qualified_call_name,
)


BRANCH_NODES = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.BoolOp,
    ast.Match,
)

@dataclass(frozen=True)
class PythonSource:
    """One source unit supplied by Tooling; paths are display-only strings."""

    module: str
    relative_path: str
    source_path: str
    text: str


@dataclass(frozen=True)
class PythonSourceQuality:
    file: FileQuality
    findings: tuple[QualityFinding, ...] = ()


def analyze_python_source(
    source: PythonSource,
    *,
    check_side_effects: bool = False,
) -> PythonSourceQuality:
    """Extract ordinary facts from Python source without filesystem access."""

    byte_count = len(source.text.encode("utf-8"))
    line_count = len(source.text.splitlines())
    try:
        tree = ast.parse(source.text, filename=source.source_path)
    except SyntaxError as exc:
        return _syntax_error(source, line_count, byte_count, exc)

    return analyze_python_source_tree(source, tree, check_side_effects=check_side_effects)


def analyze_python_source_tree(source: PythonSource, tree: ast.Module, *, check_side_effects: bool = False) -> PythonSourceQuality:
    """Extract the same facts from an already parsed, Target-owned tree."""
    byte_count = len(source.text.encode("utf-8"))
    line_count = len(source.text.splitlines())
    functions = tuple(_collect_functions(tree))
    function_count = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    )
    class_count = sum(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
    public_api_count = sum(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
        for node in tree.body
    )
    branches, nesting = _branch_and_nesting(tree)
    import_sites = _collect_import_sites(
        source.module,
        source.relative_path,
        tree,
    )
    findings = _selected_source_effect_findings(source,tree) if check_side_effects else ()
    return PythonSourceQuality(
        file=FileQuality(
            path=source.relative_path,
            module=source.module,
            lines=line_count,
            bytes=byte_count,
            function_count=function_count,
            class_count=class_count,
            public_api_count=public_api_count,
            branch_count=branches,
            max_nesting_depth=nesting,
            imports=tuple(sorted(site.imported for site in import_sites)),
            functions=functions,
            import_sites=import_sites,
        ),
        findings=findings,
    )


def _selected_source_effect_findings(source,tree):
    from vibeflow.core.rules import RuleCall, RuleContext, RulesetDescriptor, compile_ruleset, execute_rule_plan
    from vibeflow.core.rules.builtin import builtin_rule_resources
    from vibeflow.targets.python.quality.rules import python_rule_handlers
    from vibeflow.targets.python.quality.source_context import PythonSourceFile
    rules, _ = builtin_rule_resources()
    selection = RulesetDescriptor("vibeflow.python.source_effects",calls=(RuleCall("effects",rule_id="vibeflow.no_side_effects"),))
    plan = compile_ruleset(selection,rules={item.id:item for item in rules})
    context = RuleContext(facts={"python_source":source,
        "source_file":PythonSourceFile(source.source_path,source.module,source.text,_tree=tree)},
        subject={"kind":"python_source","id":source.relative_path},target="python")
    result = execute_rule_plan(plan,context,handlers=python_rule_handlers())
    return tuple(QualityFinding(rule_id=item.code,severity=item.severity,object_type=item.object_type,object_id=item.object_id,
        message=item.message,source_location=item.source_location,suggested_fix_type=item.suggested_fix_type,
        details=item.details,definition_id=item.definition_id) for item in result.findings)


def _syntax_error(
    source: PythonSource,
    line_count: int,
    byte_count: int,
    exc: SyntaxError,
) -> PythonSourceQuality:
    return PythonSourceQuality(
        file=FileQuality(
            path=source.relative_path,
            module=source.module,
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
        ),
        findings=(
            QualityFinding(
                rule_id="QUALITY.SYNTAX.PYTHON",
                severity="error",
                object_type="file",
                object_id=source.relative_path,
                source_location={
                    "path": source.source_path,
                    "line": exc.lineno or 1,
                    "column": exc.offset or 1,
                },
                message=str(exc),
                suggested_fix_type="fix_syntax",
            ),
        ),
    )


def _collect_import_sites(
    module: str,
    relative_path: str,
    tree: ast.AST,
) -> tuple[ImportSite, ...]:
    sites: list[ImportSite] = []
    for node in getattr(tree, "body", ()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                sites.append(
                    ImportSite(
                        source_module=module,
                        imported=alias.name,
                        raw_import=f"import {alias.name}",
                        path=relative_path,
                        line=getattr(node, "lineno", 1),
                        column=getattr(node, "col_offset", 0) + 1,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            base = (
                _resolve_relative_import(module, node.module, node.level)
                if node.level
                else node.module
            )
            if not base:
                continue
            raw_import = _raw_import_from(node)
            sites.append(
                ImportSite(
                    source_module=module,
                    imported=base,
                    raw_import=raw_import,
                    path=relative_path,
                    line=getattr(node, "lineno", 1),
                    column=getattr(node, "col_offset", 0) + 1,
                )
            )
            for alias in node.names:
                if alias.name == "*":
                    continue
                sites.append(
                    ImportSite(
                        source_module=module,
                        imported=f"{base}.{alias.name}",
                        raw_import=_raw_import_from(node, alias.name),
                        path=relative_path,
                        line=getattr(node, "lineno", 1),
                        column=getattr(node, "col_offset", 0) + 1,
                    )
                )
    deduped = {
        (site.imported, site.raw_import, site.line, site.column): site
        for site in sites
    }
    return tuple(deduped[key] for key in sorted(deduped))


def _raw_import_from(
    node: ast.ImportFrom,
    alias_name: str | None = None,
) -> str:
    dots = "." * int(getattr(node, "level", 0) or 0)
    module = getattr(node, "module", None) or ""
    imported = alias_name or ", ".join(alias.name for alias in node.names)
    return f"from {dots}{module} import {imported}".strip()


def _resolve_relative_import(
    module: str,
    imported: str | None,
    level: int,
) -> str | None:
    parts = module.split(".")
    base = parts[: max(0, len(parts) - level)]
    if imported:
        base.extend(imported.split("."))
    return ".".join(part for part in base if part)


def _collect_functions(tree: ast.AST) -> tuple[FunctionQuality, ...]:
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
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef


def _param_count(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    is_method: bool,
) -> int:
    args = node.args
    positional = (*args.posonlyargs, *args.args)
    count = (
        len(positional)
        - len(args.defaults)
        + sum(default is None for default in args.kw_defaults)
        + int(args.vararg is not None)
        + int(args.kwarg is not None)
    )
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
            return ast.copy_location(
                ast.arg(arg="_arg", annotation=None, type_comment=None),
                arg,
            )

        def visit_Constant(self, constant: ast.Constant) -> ast.AST:
            return ast.copy_location(ast.Constant(value="_constant"), constant)

    clone = Normalizer().visit(ast.fix_missing_locations(copy.deepcopy(node)))
    ast.fix_missing_locations(clone)
    return ast.dump(clone, include_attributes=False)


__all__ = [
    "PythonSource",
    "PythonSourceQuality",
    "analyze_python_source",
    "analyze_python_source_tree",
]
