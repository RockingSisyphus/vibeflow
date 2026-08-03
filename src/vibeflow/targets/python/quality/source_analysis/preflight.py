"""Read-only AST preflight for project modules before Python executes them."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Mapping

from vibeflow.targets.python.project.node import (
    EFFECT_SCOPE_NONE,
    EFFECT_SCOPE_TRUSTED,
    effective_effect_scope,
)
from vibeflow.targets.python.quality.source_analysis.ast_rules import (
    import_aliases,
    import_modules,
    qualified_call_name,
)
from vibeflow.targets.python.quality.source_analysis.effects import import_violation_code
from vibeflow.targets.python.quality.source_analysis.types import PurityPolicy, _SourceInfo
from vibeflow.targets.python.quality.source_analysis.visitors import ModulePurityVisitor


_SAFE_METADATA_CALLS = frozenset(
    {
        "BaseLibInfo",
        "DataProvider",
        "DataRequirement",
        "NodeContract",
        "NodeInfo",
        "PluginInfo",
        "dict",
        "frozenset",
        "list",
        "set",
        "tuple",
    }
)
_SAFE_METADATA_BUILTINS = frozenset({"dict", "frozenset", "list", "set", "tuple"})
_SAFE_METADATA_TYPES = _SAFE_METADATA_CALLS - _SAFE_METADATA_BUILTINS
_SAFE_IMPLICIT_DECORATORS = frozenset(
    {
        "builtins.classmethod",
        "builtins.property",
        "builtins.staticmethod",
        "classmethod",
        "property",
        "staticmethod",
    }
)
_FLOW_KIND_CONSTANTS = {
    "FLOW_KIND_DATA_STORE": "data_store",
    "FLOW_KIND_DECISION": "decision",
    "FLOW_KIND_DOCUMENT": "document",
    "FLOW_KIND_GLOBAL_STATE": "global_state",
    "FLOW_KIND_IO": "io",
    "FLOW_KIND_PREDEFINED": "predefined",
    "FLOW_KIND_PREPARATION": "preparation",
    "FLOW_KIND_PROCESS": "process",
    "FLOW_KIND_TERMINAL": "terminal",
}


@dataclass(frozen=True)
class PythonPreflightFinding:
    path: str
    line: int
    column: int
    message: str
    legacy_code: str = ""


@dataclass(frozen=True)
class PythonSourceFact:
    """Plain project-adapter facts for one Python source module."""

    source_id: str
    path: str
    source: str
    import_time_dependencies: tuple[str, ...] = ()
    runtime_dependencies: tuple[str, ...] = ()
    is_base_lib: bool = False
    load_error: str = ""


class PythonSourcePreflightError(ValueError):
    def __init__(self, findings: tuple[PythonPreflightFinding, ...]) -> None:
        self.findings = findings
        first = findings[0]
        summary = f"{first.path}:{first.line}:{first.column}: {first.message}"
        if len(findings) > 1:
            summary += f" ({len(findings)} preflight violations)"
        super().__init__(summary)


def preflight_python_source_facts(
    entry_source_id: str,
    sources: tuple[PythonSourceFact, ...],
) -> None:
    """Audit an in-memory local import graph before its project loader executes it."""

    source_by_id: Mapping[str, PythonSourceFact] = {
        source.source_id: source
        for source in sources
    }
    findings: list[PythonPreflightFinding] = []
    _preflight_fact(
        entry_source_id,
        source_by_id=source_by_id,
        inherited_scopes=(),
        active=set(),
        visited=set(),
        findings=findings,
    )
    deduped = tuple(
        dict.fromkeys(
            (
                finding.path,
                finding.line,
                finding.column,
                finding.message,
                finding.legacy_code,
            )
            for finding in findings
        )
    )
    if deduped:
        raise PythonSourcePreflightError(
            tuple(PythonPreflightFinding(*finding) for finding in deduped)
        )


def _preflight_fact(
    source_id: str,
    *,
    source_by_id: Mapping[str, PythonSourceFact],
    inherited_scopes: tuple[str, ...],
    active: set[str],
    visited: set[tuple[str, tuple[str, ...]]],
    findings: list[PythonPreflightFinding],
) -> None:
    if source_id in active:
        return
    fact = source_by_id.get(source_id)
    if fact is None:
        return
    path = fact.path
    if fact.load_error:
        findings.append(
            PythonPreflightFinding(
                path,
                1,
                1,
                f"Python source preflight could not load module: {fact.load_error}",
            )
        )
        return
    try:
        tree = ast.parse(fact.source, filename=path)
    except SyntaxError as exc:
        findings.append(
            PythonPreflightFinding(
                path,
                int(getattr(exc, "lineno", 1) or 1),
                int(getattr(exc, "offset", 1) or 1),
                f"Python source preflight could not parse module: {exc}",
            )
        )
        return

    own_scopes = _node_effect_scopes(tree)
    scopes = tuple(sorted(set((*inherited_scopes, *own_scopes))))
    key = (source_id, scopes)
    if key in visited:
        return
    visited.add(key)
    active.add(source_id)
    audited_scopes = tuple(scope for scope in scopes if scope != EFFECT_SCOPE_TRUSTED)
    import_time_scopes = audited_scopes or ((EFFECT_SCOPE_NONE,) if not scopes else ())
    if import_time_scopes:
        _append_module_findings(path, tree, import_time_scopes, findings)
    if audited_scopes:
        if (
            not own_scopes
            and not fact.is_base_lib
            and not _module_assigns_name(tree, "PLUGIN_INFO")
        ):
            _append_helper_findings(
                path,
                fact.source,
                tree,
                audited_scopes,
                findings,
            )

    dependencies = list(fact.import_time_dependencies)
    if audited_scopes:
        dependencies.extend(fact.runtime_dependencies)
    for dependency in dict.fromkeys(dependencies):
        _preflight_fact(
            dependency,
            source_by_id=source_by_id,
            inherited_scopes=audited_scopes,
            active=active,
            visited=visited,
            findings=findings,
        )
    active.remove(source_id)


def _append_module_findings(
    path: str,
    tree: ast.Module,
    scopes: tuple[str, ...],
    findings: list[PythonPreflightFinding],
) -> None:
    visitor = _ImportTimeVisitor(path=path, scopes=scopes)
    visitor.visit(tree)
    findings.extend(visitor.findings)


def _append_helper_findings(
    path: str,
    text: str,
    tree: ast.Module,
    scopes: tuple[str, ...],
    findings: list[PythonPreflightFinding],
) -> None:
    source = _SourceInfo(
        path=path,
        class_text=None,
        class_start_line=1,
        module_text=text,
    )
    for scope in scopes:
        visitor = ModulePurityVisitor(
            policy=PurityPolicy(),
            source=source,
            node_class_name="",
            known_node_modules=(),
            known_node_class_names=(),
            effect_scope=scope,
            audit_all_definitions=True,
        )
        visitor.visit(tree)
        findings.extend(
            PythonPreflightFinding(
                str(item.source_location.get("path", path)),
                int(item.source_location.get("line", 1)),
                int(item.source_location.get("column", 1)),
                f"local helper quality violation: {item.message}",
                item.code,
            )
            for item in visitor.violations
            if item.severity == "error"
        )


class _ImportTimeVisitor(ast.NodeVisitor):
    def __init__(self, *, path: str, scopes: tuple[str, ...]) -> None:
        self.path = path
        self.scopes = scopes
        self.policy = PurityPolicy()
        self.aliases: dict[str, str] = {}
        self.findings: list[PythonPreflightFinding] = []
        self._safe_metadata = False
        self._safe_metadata_helpers: set[str] = set()
        self._shadowed_names: set[str] = set()

    def visit_Module(self, node: ast.Module) -> None:
        self.aliases.update(import_aliases(node))
        self._shadowed_names = _module_shadowed_names(node)
        self._safe_metadata_helpers = _safe_metadata_helpers(node)
        for statement in node.body:
            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                self.visit(statement)
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._visit_function_header(statement)
            elif isinstance(statement, ast.ClassDef):
                self.visit(statement)
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                metadata = _metadata_assignment(statement)
                if isinstance(statement, ast.AnnAssign):
                    self.visit(statement.annotation)
                previous = self._safe_metadata
                self._safe_metadata = metadata
                self.visit(statement.value) if statement.value is not None else None
                self._safe_metadata = previous
            elif _is_docstring(statement) or isinstance(statement, ast.Pass):
                continue
            elif _is_type_checking_block(statement):
                for nested in statement.body:
                    if isinstance(nested, (ast.Import, ast.ImportFrom)):
                        self.visit(nested)
            else:
                self.visit(statement)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in node.decorator_list:
            self._visit_decorator(expression)
        for expression in node.bases:
            self.visit(expression)
            name = qualified_call_name(expression, self.aliases)
            if name not in {"builtins.object", "object"}:
                self._add(
                    expression,
                    "audited node import chain must not invoke __init_subclass__ before source validation",
                    legacy_code="module_side_effect",
                )
        for keyword in node.keywords:
            self.visit(keyword.value)
            self._add(
                keyword,
                "audited node import chain must not invoke a metaclass or class keyword hook before source validation",
                legacy_code="module_side_effect",
            )
        previous_shadowed = self._shadowed_names
        self._shadowed_names = previous_shadowed | _class_shadowed_names(node)
        for statement in node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._visit_function_header(statement)
            elif isinstance(statement, ast.ClassDef):
                self.visit(statement)
            elif isinstance(statement, (ast.Import, ast.ImportFrom)):
                self.visit(statement)
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                if isinstance(statement, ast.AnnAssign):
                    self.visit(statement.annotation)
                previous = self._safe_metadata
                self._safe_metadata = _metadata_assignment(statement)
                if statement.value is not None:
                    self.visit(statement.value)
                self._safe_metadata = previous
            elif _is_docstring(statement) or isinstance(statement, ast.Pass):
                continue
            else:
                self.visit(statement)
        self._shadowed_names = previous_shadowed

    def visit_Import(self, node: ast.Import) -> None:
        for module in import_modules(node):
            self._check_import(module, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for module in import_modules(node):
            self._check_import(module, node)

    def visit_Call(self, node: ast.Call) -> None:
        name = qualified_call_name(node.func, self.aliases)
        raw_name = qualified_call_name(node.func, {})
        if not self._safe_metadata or not _safe_metadata_call_is_allowed(
            name,
            raw_name=raw_name,
            helpers=self._safe_metadata_helpers,
            shadowed_names=self._shadowed_names,
        ):
            self._add(
                node,
                f"audited node import chain executes a call before source validation: {name or '<dynamic>'}",
                legacy_code="module_side_effect",
            )
            return
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._add(
            node,
            "audited node import chain must not execute a top-level loop",
            legacy_code="module_side_effect",
        )

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._add(
            node,
            "audited node import chain must not execute a top-level async loop",
            legacy_code="module_side_effect",
        )

    def visit_While(self, node: ast.While) -> None:
        self._add(
            node,
            "audited node import chain must not execute a top-level loop",
            legacy_code="module_side_effect",
        )

    def visit_With(self, node: ast.With) -> None:
        self._add(
            node,
            "audited node import chain must not enter a top-level context manager",
            legacy_code="module_side_effect",
        )

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._add(
            node,
            "audited node import chain must not enter a top-level async context manager",
            legacy_code="module_side_effect",
        )

    def visit_Raise(self, node: ast.Raise) -> None:
        self._add(
            node,
            "audited node import chain must not raise during import",
            legacy_code="module_side_effect",
        )

    def _visit_function_header(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for expression in node.decorator_list:
            self._visit_decorator(expression)
        for expression in (*node.args.defaults, *(item for item in node.args.kw_defaults if item is not None)):
            self.visit(expression)
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ):
            if argument.annotation is not None:
                self.visit(argument.annotation)
        for argument in (node.args.vararg, node.args.kwarg):
            if argument is not None and argument.annotation is not None:
                self.visit(argument.annotation)
        if node.returns is not None:
            self.visit(node.returns)

    def _visit_decorator(self, node: ast.AST) -> None:
        self.visit(node)
        if isinstance(node, ast.Call):
            return
        name = qualified_call_name(node, self.aliases)
        if name not in _SAFE_IMPLICIT_DECORATORS:
            self._add(
                node,
                f"audited node import chain invokes a decorator before source validation: {name or '<dynamic>'}",
                legacy_code="module_side_effect",
            )

    def _check_import(self, module: str, node: ast.AST) -> None:
        for scope in self.scopes:
            violation_code = import_violation_code(
                module,
                effect_scope=scope,
                policy=self.policy,
            )
            if violation_code:
                self._add(
                    node,
                    f"audited node import chain uses a forbidden import for scope {scope!r}: {module}",
                    legacy_code=violation_code,
                )
                return

    def _add(
        self,
        node: ast.AST,
        message: str,
        *,
        legacy_code: str = "",
    ) -> None:
        self.findings.append(
            PythonPreflightFinding(
                str(self.path),
                int(getattr(node, "lineno", 1) or 1),
                int(getattr(node, "col_offset", 0) or 0) + 1,
                message,
                legacy_code,
            )
        )


def _node_effect_scopes(tree: ast.Module) -> tuple[str, ...]:
    scopes: list[str] = []
    for class_node in (item for item in tree.body if isinstance(item, ast.ClassDef)):
        assignment = next(
            (
                item
                for item in class_node.body
                if isinstance(item, (ast.Assign, ast.AnnAssign))
                and _assignment_has_name(item, "NODE_INFO")
            ),
            None,
        )
        if assignment is None:
            continue
        value = assignment.value
        flow_kind = ""
        external = False
        if isinstance(value, ast.Call) and qualified_call_name(value.func, {}).rsplit(".", 1)[-1] == "NodeInfo":
            flow_node = _call_argument(value, "flow_kind", 5)
            external_node = _call_argument(value, "external", 9)
            flow_kind = _static_flow_kind(flow_node)
            external = isinstance(external_node, ast.Constant) and external_node.value is True
        info = SimpleNamespace(flow_kind=flow_kind, external=external)
        scopes.append(effective_effect_scope(info))
    return tuple(scopes)


def _safe_metadata_helpers(tree: ast.Module) -> set[str]:
    aliases = import_aliases(tree)
    shadowed_names = _module_shadowed_names(tree)
    candidates = tuple(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Return)
        and node.body[0].value is not None
    )
    helpers: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in candidates:
            if node.name in helpers:
                continue
            parameters = {
                argument.arg
                for argument in (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
            }
            if node.args.vararg is not None:
                parameters.add(node.args.vararg.arg)
            if node.args.kwarg is not None:
                parameters.add(node.args.kwarg.arg)
            statement = node.body[0]
            assert isinstance(statement, ast.Return) and statement.value is not None
            if _is_declarative_metadata_expression(
                statement.value,
                parameters=parameters,
                aliases=aliases,
                helpers=helpers,
                shadowed_names=shadowed_names | parameters,
            ):
                helpers.add(node.name)
                changed = True
    return helpers


def _is_declarative_metadata_expression(
    node: ast.AST,
    *,
    parameters: set[str],
    aliases: dict[str, str],
    helpers: set[str],
    shadowed_names: set[str],
) -> bool:
    """Prove that a metadata helper only builds declarative values."""

    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return node.id in parameters
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return all(
            _is_declarative_metadata_expression(
                item,
                parameters=parameters,
                aliases=aliases,
                helpers=helpers,
                shadowed_names=shadowed_names,
            )
            for item in node.elts
        )
    if isinstance(node, ast.Dict):
        return all(
            (key is None or _is_declarative_metadata_expression(
                key,
                parameters=parameters,
                aliases=aliases,
                helpers=helpers,
                shadowed_names=shadowed_names,
            ))
            and _is_declarative_metadata_expression(
                value,
                parameters=parameters,
                aliases=aliases,
                helpers=helpers,
                shadowed_names=shadowed_names,
            )
            for key, value in zip(node.keys, node.values, strict=True)
        )
    if isinstance(node, ast.BoolOp):
        return all(
            _is_declarative_metadata_expression(
                value,
                parameters=parameters,
                aliases=aliases,
                helpers=helpers,
                shadowed_names=shadowed_names,
            )
            for value in node.values
        )
    if isinstance(node, ast.IfExp):
        return all(
            _is_declarative_metadata_expression(
                value,
                parameters=parameters,
                aliases=aliases,
                helpers=helpers,
                shadowed_names=shadowed_names,
            )
            for value in (node.test, node.body, node.orelse)
        )
    if isinstance(node, ast.Starred):
        return _is_declarative_metadata_expression(
            node.value,
            parameters=parameters,
            aliases=aliases,
            helpers=helpers,
            shadowed_names=shadowed_names,
        )
    if not isinstance(node, ast.Call):
        return False
    name = qualified_call_name(node.func, aliases)
    raw_name = qualified_call_name(node.func, {})
    if not _safe_metadata_call_is_allowed(
        name,
        raw_name=raw_name,
        helpers=helpers,
        shadowed_names=shadowed_names,
    ):
        return False
    return all(
        _is_declarative_metadata_expression(
            value,
            parameters=parameters,
            aliases=aliases,
            helpers=helpers,
            shadowed_names=shadowed_names,
        )
        for value in (*node.args, *(keyword.value for keyword in node.keywords))
    )


def _safe_metadata_call_is_allowed(
    name: str,
    *,
    raw_name: str,
    helpers: set[str],
    shadowed_names: set[str],
) -> bool:
    if name in helpers:
        return True
    raw_root = raw_name.split(".", 1)[0]
    if raw_root in shadowed_names:
        return False
    leaf = name.rsplit(".", 1)[-1]
    if leaf in _SAFE_METADATA_BUILTINS:
        return name in {leaf, f"builtins.{leaf}"}
    return leaf in _SAFE_METADATA_TYPES and name.startswith("vibeflow.")


def _module_shadowed_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(_target_names(target))
        elif isinstance(node, ast.AnnAssign):
            names.update(_target_names(node.target))
    return names


def _class_shadowed_names(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for statement in node.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(statement.name)
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                names.update(_target_names(target))
        elif isinstance(statement, ast.AnnAssign):
            names.update(_target_names(statement.target))
    return names


def _target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.List, ast.Tuple)):
        names: set[str] = set()
        for item in node.elts:
            names.update(_target_names(item))
        return names
    return set()


def _call_argument(node: ast.Call, keyword_name: str, position: int) -> ast.AST | None:
    keyword = next((item.value for item in node.keywords if item.arg == keyword_name), None)
    if keyword is not None:
        return keyword
    return node.args[position] if len(node.args) > position else None


def _static_flow_kind(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return _FLOW_KIND_CONSTANTS.get(node.id, "")
    if isinstance(node, ast.Attribute):
        return _FLOW_KIND_CONSTANTS.get(node.attr, "")
    return ""


def _metadata_assignment(node: ast.Assign | ast.AnnAssign) -> bool:
    return any(
        _assignment_has_name(node, name)
        for name in {"BASE_LIB_INFO", "CONTRACT", "NODE_INFO", "PLUGIN_INFO"}
    )


def _module_assigns_name(tree: ast.Module, name: str) -> bool:
    return any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and _assignment_has_name(node, name)
        for node in tree.body
    )


def _assignment_has_name(node: ast.Assign | ast.AnnAssign, name: str) -> bool:
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    return any(isinstance(target, ast.Name) and target.id == name for target in targets)


def _is_docstring(node: ast.AST) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _is_type_checking_block(node: ast.AST) -> bool:
    return isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"


__all__ = [
    "PythonPreflightFinding",
    "PythonSourceFact",
    "PythonSourcePreflightError",
    "preflight_python_source_facts",
]
