"""Python planned-stub signature and source safety analysis."""

from __future__ import annotations

import ast
import inspect
from typing import Mapping

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.project.node import EFFECT_SCOPE_NONE
from vibeflow.targets.python.quality.source_analysis.ast_rules import import_aliases
from vibeflow.targets.python.quality.source_analysis.effects import (
    call_violation,
    from_import_effect_is_forbidden,
    import_violation_code,
    process_argv_import_is_forbidden,
    process_argv_reference,
    system_exit_is_forbidden,
    system_exit_reference,
    terminal_stream_import_is_forbidden,
    terminal_stream_is_forbidden,
    terminal_stream_reference,
)
from vibeflow.targets.python.quality.source_analysis.types import PurityPolicy


def validate_python_stub_source(
    source_text: str,
    *,
    path: str,
    object_type: str,
    object_id: str,
) -> tuple[HealthFinding, ...]:
    """Validate an already-loaded planned stub without filesystem access."""

    try:
        tree = ast.parse(source_text, filename=path)
    except SyntaxError as exc:
        return (
            planned_stub_finding(
                "GRAPH.PLANNED.STUB_SYNTAX",
                f"planned python_stub syntax error: {exc}",
                object_type,
                object_id,
            ),
        )
    findings = _validate_stub_entry(
        tree,
        object_type=object_type,
        object_id=object_id,
    )
    findings.extend(
        _validate_stub_ast(
            tree,
            object_type=object_type,
            object_id=object_id,
            path=path,
        )
    )
    return tuple(findings)


def _validate_stub_entry(
    tree: ast.Module,
    *,
    object_type: str,
    object_id: str,
) -> list[HealthFinding]:
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "run_stub"
    ]
    if not matches:
        return [
            planned_stub_finding(
                "GRAPH.PLANNED.STUB_ENTRY",
                "planned python_stub must define run_stub(inputs, params)",
                object_type,
                object_id,
            )
        ]
    function = matches[0]
    findings: list[HealthFinding] = []
    if isinstance(function, ast.AsyncFunctionDef):
        findings.append(
            planned_stub_finding(
                "GRAPH.PLANNED.STUB_ENTRY",
                "planned python_stub run_stub must not be async",
                object_type,
                object_id,
            )
        )
    args = function.args
    positional = [*args.posonlyargs, *args.args]
    names = tuple(arg.arg for arg in positional)
    if (
        names != ("inputs", "params")
        or args.vararg
        or args.kwarg
        or args.kwonlyargs
        or args.defaults
        or args.kw_defaults
    ):
        findings.append(
            planned_stub_finding(
                "GRAPH.PLANNED.STUB_ENTRY",
                "planned python_stub entry must have signature "
                "run_stub(inputs, params)",
                object_type,
                object_id,
            )
        )
    return findings


def _validate_stub_ast(
    tree: ast.Module,
    *,
    object_type: str,
    object_id: str,
    path: str,
) -> list[HealthFinding]:
    visitor = _StubSafetyVisitor(
        object_type=object_type,
        object_id=object_id,
        path=path,
    )
    visitor.visit(tree)
    return visitor.findings


class _StubSafetyVisitor(ast.NodeVisitor):
    def __init__(self, *, object_type: str, object_id: str, path: str) -> None:
        self.object_type = object_type
        self.object_id = object_id
        self.path = path
        self.aliases: dict[str, str] = {}
        self.policy = PurityPolicy()
        self.findings: list[HealthFinding] = []

    def visit_Module(self, node: ast.Module) -> None:
        self.aliases = import_aliases(node)
        for stmt in node.body:
            self._check_top_level(stmt)
            self.visit(stmt)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(alias.name, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            names = {alias.name for alias in node.names}
            if process_argv_import_is_forbidden(node.module, names):
                self._add(
                    "GRAPH.PLANNED.STUB_UNSAFE_IMPORT",
                    "planned python_stub must not import process sys.argv",
                    node,
                )
            if terminal_stream_import_is_forbidden(
                node.module,
                names,
                effect_scope=EFFECT_SCOPE_NONE,
            ):
                self._add(
                    "GRAPH.PLANNED.STUB_UNSAFE_IMPORT",
                    "planned python_stub must not import terminal streams",
                    node,
                )
            if from_import_effect_is_forbidden(
                node.module,
                names,
                effect_scope=EFFECT_SCOPE_NONE,
            ):
                self._add(
                    "GRAPH.PLANNED.STUB_UNSAFE_IMPORT",
                    "planned python_stub imports high-risk member from: "
                    f"{node.module}",
                    node,
                )
            self._check_import(node.module, node)

    def visit_Call(self, node: ast.Call) -> None:
        violation_code, forbidden = call_violation(
            node,
            aliases=self.aliases,
            effect_scope=EFFECT_SCOPE_NONE,
        )
        if violation_code:
            self._add(
                "GRAPH.PLANNED.STUB_UNSAFE_CALL",
                f"planned python_stub uses banned call: {forbidden}",
                node,
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        reference = process_argv_reference(node, self.aliases)
        if reference:
            self._add(
                "GRAPH.PLANNED.STUB_UNSAFE_CALL",
                f"planned python_stub uses process arguments: {reference}",
                node,
            )
        reference = terminal_stream_reference(node, self.aliases)
        if reference and terminal_stream_is_forbidden(EFFECT_SCOPE_NONE):
            self._add(
                "GRAPH.PLANNED.STUB_UNSAFE_CALL",
                f"planned python_stub uses terminal stream: {reference}",
                node,
            )
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if not isinstance(node.exc, ast.Call):
            reference = system_exit_reference(node.exc, self.aliases)
            if reference and system_exit_is_forbidden(EFFECT_SCOPE_NONE):
                self._add(
                    "GRAPH.PLANNED.STUB_UNSAFE_CALL",
                    f"planned python_stub uses process exit: {reference}",
                    node,
                )
        self.generic_visit(node)

    def _check_import(self, module: str, node: ast.AST) -> None:
        if import_violation_code(
            module,
            effect_scope=EFFECT_SCOPE_NONE,
            policy=self.policy,
        ):
            self._add(
                "GRAPH.PLANNED.STUB_UNSAFE_IMPORT",
                f"planned python_stub imports high-risk module: {module}",
                node,
            )

    def _check_top_level(self, stmt: ast.stmt) -> None:
        if isinstance(
            stmt,
            (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            return
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            return
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and _immutable_assignment(
            stmt
        ):
            return
        self._add(
            "GRAPH.PLANNED.STUB_TOP_LEVEL",
            "planned python_stub module top level may only contain imports, "
            "functions, immutable constants, and docstrings",
            stmt,
        )

    def _add(self, rule_id: str, message: str, node: ast.AST) -> None:
        self.findings.append(
            planned_stub_finding(
                rule_id,
                message,
                self.object_type,
                self.object_id,
                source_location={
                    "path": self.path,
                    "line": getattr(node, "lineno", 1),
                    "column": getattr(node, "col_offset", 0) + 1,
                },
            )
        )


def _immutable_assignment(stmt: ast.Assign | ast.AnnAssign) -> bool:
    return stmt.value is None or _is_immutable(stmt.value)


def _is_immutable(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, int, float, bool, type(None)))
    if isinstance(node, ast.Tuple):
        return all(_is_immutable(item) for item in node.elts)
    return False


def planned_stub_finding(
    rule_id: str,
    message: str,
    object_type: str,
    object_id: str,
    *,
    source_location: Mapping[str, object] | None = None,
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type=object_type,
        object_id=object_id,
        source_location=dict(source_location or {}),
        failure_layer="topology",
        message=message,
        suggested_fix_type="fix_stub",
    )


def signature_is_run_stub(func: object) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    params = tuple(signature.parameters.values())
    valid_kinds = {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    }
    return (
        len(params) == 2
        and tuple(param.name for param in params) == ("inputs", "params")
        and all(param.kind in valid_kinds for param in params)
        and all(param.default is inspect.Parameter.empty for param in params)
    )

__all__ = [
    "planned_stub_finding",
    "signature_is_run_stub",
    "validate_python_stub_source",
]
