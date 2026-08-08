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
from vibeflow.targets.python.quality.source_analysis.effects import call_violation
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
_SAFE_DECLARATIVE_BUILTINS = frozenset(
    {
        *_SAFE_METADATA_BUILTINS,
        "abs",
        "all",
        "any",
        "bool",
        "enumerate",
        "float",
        "int",
        "isinstance",
        "len",
        "max",
        "min",
        "range",
        "round",
        "sorted",
        "str",
        "sum",
        "type",
        "zip",
    }
)
_SAFE_DECLARATIVE_METHODS = frozenset(
    {
        "copy",
        "endswith",
        "get",
        "isascii",
        "items",
        "keys",
        "lower",
        "removeprefix",
        "removesuffix",
        "replace",
        "rsplit",
        "split",
        "startswith",
        "strip",
        "upper",
        "values",
    }
)
_UNSAFE_DECLARATIVE_HELPER_NODES = (
    ast.AsyncFor,
    ast.AsyncFunctionDef,
    ast.AsyncWith,
    ast.Await,
    ast.Delete,
    ast.For,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Lambda,
    ast.Nonlocal,
    ast.Raise,
    ast.Try,
    ast.While,
    ast.With,
    ast.Yield,
    ast.YieldFrom,
)
_SAFE_BUILTIN_BASES = frozenset(
    {
        "BaseException",
        "Exception",
        "LookupError",
        "RuntimeError",
        "TypeError",
        "ValueError",
        "dict",
        "list",
        "object",
        "set",
        "tuple",
    }
)
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
    module_name: str = ""
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
    metadata_helpers = _proven_metadata_helpers(sources)
    safe_class_bases = _proven_safe_class_bases(sources)
    _preflight_fact(
        entry_source_id,
        source_by_id=source_by_id,
        inherited_scopes=(),
        active=set(),
        visited=set(),
        findings=findings,
        metadata_helpers=metadata_helpers,
        safe_class_bases=safe_class_bases,
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
    metadata_helpers: frozenset[str],
    safe_class_bases: frozenset[str],
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
        _append_module_findings(
            path,
            tree,
            import_time_scopes,
            findings,
            metadata_helpers=metadata_helpers,
            safe_class_bases=safe_class_bases,
            skip_import_scope=(
                not own_scopes
                and (
                    _module_declares_node(tree)
                    or (fact.is_base_lib and not inherited_scopes)
                )
            ),
            module_name=fact.module_name,
        )
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
            metadata_helpers=metadata_helpers,
            safe_class_bases=safe_class_bases,
        )
    active.remove(source_id)


def _append_module_findings(
    path: str,
    tree: ast.Module,
    scopes: tuple[str, ...],
    findings: list[PythonPreflightFinding],
    *,
    metadata_helpers: frozenset[str],
    safe_class_bases: frozenset[str],
    skip_import_scope: bool,
    module_name: str,
) -> None:
    visitor = _ImportTimeVisitor(
        path=path,
        scopes=scopes,
        metadata_helpers=metadata_helpers,
        safe_class_bases=safe_class_bases,
        skip_import_scope=skip_import_scope,
        module_name=module_name,
    )
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
    def __init__(
        self,
        *,
        path: str,
        scopes: tuple[str, ...],
        metadata_helpers: frozenset[str],
        safe_class_bases: frozenset[str],
        skip_import_scope: bool,
        module_name: str,
    ) -> None:
        self.path = path
        self.scopes = scopes
        self.policy = PurityPolicy()
        self.aliases: dict[str, str] = {}
        self.findings: list[PythonPreflightFinding] = []
        self._safe_metadata = False
        self._safe_metadata_helpers: set[str] = set(metadata_helpers)
        if module_name:
            prefix = f"{module_name}."
            self._safe_metadata_helpers.update(
                name[len(prefix):]
                for name in metadata_helpers
                if name.startswith(prefix) and "." not in name[len(prefix):]
            )
        local_class_bases = set(safe_class_bases)
        if module_name:
            prefix = f"{module_name}."
            local_class_bases.update(
                name[len(prefix):]
                for name in safe_class_bases
                if name.startswith(prefix) and "." not in name[len(prefix):]
            )
        self._safe_class_bases = frozenset(local_class_bases)
        self._skip_import_scope = skip_import_scope
        self._shadowed_names: set[str] = set()

    def visit_Module(self, node: ast.Module) -> None:
        self.aliases.update(import_aliases(node))
        self._shadowed_names = _module_shadowed_names(node)
        self._safe_metadata_helpers.update(_safe_metadata_helpers(node))
        for statement in node.body:
            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                self.visit(statement)
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._visit_function_header(statement)
            elif isinstance(statement, ast.ClassDef):
                self.visit(statement)
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                metadata = _metadata_assignment(statement) or _immutable_declaration_assignment(statement)
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
            raw_name = qualified_call_name(expression, {})
            if not _safe_class_base_is_allowed(
                name,
                raw_name=raw_name,
                safe_class_bases=self._safe_class_bases,
                shadowed_names=self._shadowed_names,
            ):
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
                self._safe_metadata = _metadata_assignment(statement) or _immutable_declaration_assignment(statement)
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
        safe_class_wrapper = (
            name in _SAFE_IMPLICIT_DECORATORS
            and raw_name.split(".", 1)[0] not in self._shadowed_names
        )
        if not safe_class_wrapper and (
            not self._safe_metadata
            or not _safe_metadata_call_is_allowed(
                name,
                raw_name=raw_name,
                helpers=self._safe_metadata_helpers,
                shadowed_names=self._shadowed_names,
            )
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
        if self._skip_import_scope:
            return
        violations = tuple(
            (
                scope,
                import_violation_code(
                    module,
                    effect_scope=scope,
                    policy=self.policy,
                ),
            )
            for scope in self.scopes
        )
        denied = tuple((scope, code) for scope, code in violations if code)
        if denied and len(denied) == len(violations):
            scope, violation_code = denied[0]
            self._add(
                node,
                f"audited node import chain uses a forbidden import for scope {scope!r}: {module}",
                legacy_code=violation_code,
            )

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
        if not (
            isinstance(value, ast.Call)
            and qualified_call_name(value.func, {}).rsplit(".", 1)[-1] == "NodeInfo"
        ):
            continue
        flow_node = _call_argument(value, "flow_kind", 5)
        external_node = _call_argument(value, "external", 9)
        flow_kind = _static_flow_kind(flow_node)
        external = isinstance(external_node, ast.Constant) and external_node.value is True
        info = SimpleNamespace(flow_kind=flow_kind, external=external)
        scopes.append(effective_effect_scope(info))
    return tuple(scopes)


def _module_declares_node(tree: ast.Module) -> bool:
    return any(
        isinstance(item, ast.ClassDef)
        and any(
            isinstance(statement, (ast.Assign, ast.AnnAssign))
            and _assignment_has_name(statement, "NODE_INFO")
            for statement in item.body
        )
        for item in tree.body
    )


def _proven_metadata_helpers(
    sources: tuple[PythonSourceFact, ...],
) -> frozenset[str]:
    candidates: dict[str, tuple[ast.FunctionDef, ast.Module]] = {}
    for fact in sources:
        if not fact.module_name:
            continue
        try:
            tree = ast.parse(fact.source, filename=fact.path)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                candidates[f"{fact.module_name}.{node.name}"] = (node, tree)

    proven: set[str] = set()
    changed = True
    while changed:
        changed = False
        for qualified_name, (node, tree) in candidates.items():
            if qualified_name in proven:
                continue
            module_name = qualified_name.rsplit(".", 1)[0]
            if _declarative_helper_is_proven(
                node,
                tree=tree,
                module_name=module_name,
                candidates=candidates,
                proven=proven,
            ):
                proven.add(qualified_name)
                changed = True
    return frozenset(proven)


def _declarative_helper_is_proven(
    node: ast.FunctionDef,
    *,
    tree: ast.Module,
    module_name: str,
    candidates: Mapping[str, tuple[ast.FunctionDef, ast.Module]],
    proven: set[str],
) -> bool:
    for nested in ast.walk(node):
        if isinstance(nested, _UNSAFE_DECLARATIVE_HELPER_NODES):
            return False
        if isinstance(nested, (ast.FunctionDef, ast.ClassDef)) and nested is not node:
            return False

    aliases = import_aliases(tree)
    imported_roots = {
        value.split(".", 1)[0]
        for value in aliases.values()
        if value
    }
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
    local_names = _function_local_names(node)
    module_state_names = _module_bound_names(tree)
    callable_aliases = {
        key: value
        for key, value in aliases.items()
        if key not in local_names and key not in parameters
    }

    for nested in ast.walk(node):
        if isinstance(nested, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = nested.targets if isinstance(nested, ast.Assign) else (nested.target,)
            if any(
                not _declarative_assignment_target_is_safe(
                    target,
                    local_names=local_names,
                    parameters=parameters,
                )
                for target in targets
            ):
                return False
        if not isinstance(nested, ast.Call):
            continue
        violation_code, _ = call_violation(
            nested,
            aliases=callable_aliases,
            effect_scope=EFFECT_SCOPE_NONE,
            imported_roots=imported_roots,
            module_state_names=module_state_names,
            local_names=local_names | parameters,
        )
        if violation_code:
            return False
        name = qualified_call_name(nested.func, callable_aliases)
        raw_name = qualified_call_name(nested.func, {})
        if _declarative_call_is_intrinsically_safe(name, raw_name=raw_name):
            continue
        resolved = _resolve_local_callable(
            name,
            module_name=module_name,
            candidates=candidates,
        )
        if resolved not in proven:
            return False
    return True


def _function_local_names(node: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for nested in ast.walk(node):
        if isinstance(nested, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = nested.targets if isinstance(nested, ast.Assign) else (nested.target,)
            for target in targets:
                names.update(_target_names(target))
        elif isinstance(nested, ast.comprehension):
            names.update(_target_names(nested.target))
    return names


def _module_bound_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(statement.name)
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                names.update(_target_names(target))
        elif isinstance(statement, ast.AnnAssign):
            names.update(_target_names(statement.target))
    return names


def _declarative_assignment_target_is_safe(
    target: ast.AST,
    *,
    local_names: set[str],
    parameters: set[str],
) -> bool:
    if isinstance(target, ast.Name):
        return True
    if isinstance(target, (ast.List, ast.Tuple)):
        return all(
            _declarative_assignment_target_is_safe(
                item,
                local_names=local_names,
                parameters=parameters,
            )
            for item in target.elts
        )
    if isinstance(target, (ast.Attribute, ast.Subscript)):
        root = target.value
        while isinstance(root, (ast.Attribute, ast.Subscript)):
            root = root.value
        return (
            isinstance(root, ast.Name)
            and root.id in local_names
            and root.id not in parameters
        )
    return False


def _declarative_call_is_intrinsically_safe(name: str, *, raw_name: str) -> bool:
    leaf = name.rsplit(".", 1)[-1]
    if leaf in _SAFE_DECLARATIVE_BUILTINS:
        return name in {leaf, f"builtins.{leaf}"}
    if leaf in _SAFE_METADATA_TYPES and name.startswith("vibeflow."):
        return True
    return (
        isinstance(raw_name, str)
        and "." in raw_name
        and leaf in _SAFE_DECLARATIVE_METHODS
    )


def _resolve_local_callable(
    name: str,
    *,
    module_name: str,
    candidates: Mapping[str, object],
) -> str:
    if name in candidates:
        return name
    if "." not in name:
        local_name = f"{module_name}.{name}"
        if local_name in candidates:
            return local_name
    return ""


def _proven_safe_class_bases(
    sources: tuple[PythonSourceFact, ...],
) -> frozenset[str]:
    candidates: dict[str, tuple[ast.ClassDef, ast.Module]] = {}
    for fact in sources:
        if not fact.module_name:
            continue
        try:
            tree = ast.parse(fact.source, filename=fact.path)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                candidates[f"{fact.module_name}.{node.name}"] = (node, tree)

    proven: set[str] = set()
    changed = True
    while changed:
        changed = False
        for qualified_name, (node, tree) in candidates.items():
            if qualified_name in proven or node.keywords:
                continue
            if any(
                isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
                and statement.name == "__init_subclass__"
                for statement in node.body
            ):
                continue
            aliases = import_aliases(tree)
            module_name = qualified_name.rsplit(".", 1)[0]
            if all(
                _class_candidate_base_is_proven(
                    base,
                    aliases=aliases,
                    module_name=module_name,
                    candidates=candidates,
                    proven=proven,
                )
                for base in node.bases
            ):
                proven.add(qualified_name)
                changed = True
    return frozenset(proven)


def _class_candidate_base_is_proven(
    node: ast.AST,
    *,
    aliases: Mapping[str, str],
    module_name: str,
    candidates: Mapping[str, object],
    proven: set[str],
) -> bool:
    name = qualified_call_name(node, aliases)
    raw_name = qualified_call_name(node, {})
    if _safe_builtin_base_is_allowed(name, raw_name=raw_name):
        return True
    resolved = _resolve_local_callable(
        name,
        module_name=module_name,
        candidates=candidates,
    )
    return resolved in proven


def _safe_builtin_base_is_allowed(name: str, *, raw_name: str) -> bool:
    leaf = name.rsplit(".", 1)[-1]
    return leaf in _SAFE_BUILTIN_BASES and name in {leaf, f"builtins.{leaf}"}


def _safe_class_base_is_allowed(
    name: str,
    *,
    raw_name: str,
    safe_class_bases: frozenset[str],
    shadowed_names: set[str],
) -> bool:
    if name in safe_class_bases or raw_name in safe_class_bases:
        return True
    raw_root = raw_name.split(".", 1)[0]
    if raw_root in shadowed_names:
        return False
    return _safe_builtin_base_is_allowed(name, raw_name=raw_name)


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
    leaf = name.rsplit(".", 1)[-1]
    base = name.rsplit(".", 1)[0] if "." in name else ""
    raw_base = raw_name.rsplit(".", 1)[0] if "." in raw_name else ""
    if leaf in _SAFE_DECLARATIVE_METHODS and (
        base in helpers or raw_base in helpers
    ):
        return True
    raw_root = raw_name.split(".", 1)[0]
    if raw_root in shadowed_names:
        return False
    if _declarative_call_is_intrinsically_safe(name, raw_name=raw_name):
        return True
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


def _immutable_declaration_assignment(node: ast.Assign | ast.AnnAssign) -> bool:
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    if not targets or not all(
        isinstance(target, ast.Name) and target.id.isupper()
        for target in targets
    ):
        return False
    return node.value is not None and _is_immutable_declaration_expression(node.value)


def _is_immutable_declaration_expression(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Tuple):
        return all(_is_immutable_declaration_expression(item) for item in node.elts)
    if not isinstance(node, ast.Call):
        return False
    name = qualified_call_name(node.func, {})
    return (
        name in {"frozenset", "builtins.frozenset"}
        and not node.keywords
        and len(node.args) == 1
        and isinstance(node.args[0], (ast.Set, ast.Tuple, ast.List))
        and all(
            _is_immutable_declaration_expression(item)
            for item in node.args[0].elts
        )
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
