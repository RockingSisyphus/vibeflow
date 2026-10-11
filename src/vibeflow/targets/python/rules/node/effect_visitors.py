from __future__ import annotations

import ast

from vibeflow.targets.python.quality.source_analysis.ast_facts import (
    import_aliases,
    import_aliases_from_node,
    imported_module_roots,
    import_modules,
    module_statement_kind,
    qualified_reference_name,
)
from vibeflow.core.constants import EFFECT_SCOPE_GLOBAL_STATE, EFFECT_SCOPE_NONE
from vibeflow.core.descriptors import NodeContractDescriptor
from vibeflow.targets.python.rules.node.effect_policy import (
    ambient_assignment_is_forbidden,
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
from vibeflow.targets.python.quality.source_analysis.ast_facts import call_name as _call_name
from vibeflow.targets.python.rules.node.effect_policy import module_assignment_is_allowed as _module_assignment_is_allowed
from vibeflow.targets.python.quality.source_analysis.helpers import (
    _module_matches,
    _root_name,
    _violation,
)
from vibeflow.targets.python.quality.source_analysis.ast_facts import _reachable_module_helpers
from vibeflow.targets.python.quality.source_analysis.types import PurityViolation, _SourceInfo
from vibeflow.targets.python.rules.node.policy import PurityPolicy


from vibeflow.targets.python.quality.source_analysis.bindings import _bound_names, _comprehension_evaluation_steps, _comprehension_outer_bindings, _function_definition_expressions, _function_scope_bindings, _FunctionBindingCollector


_LOCAL_EFFECT_PREFIX = "<local>."


class _EffectAliases(dict):
    """Canonical aliases plus possible targets retained by a local branch join."""

    def __init__(self, values=()):
        super().__init__(values)
        self.alternatives = {}

    def __setitem__(self, key, value):
        self.alternatives.pop(key, None)
        super().__setitem__(key, value)

    def update(self, values=(), **kwargs):
        for key, value in dict(values, **kwargs).items():
            self[key] = value

    def pop(self, key, *default):
        self.alternatives.pop(key, None)
        return super().pop(key, *default)

    def copy(self):
        result = _EffectAliases(self)
        result.alternatives = dict(self.alternatives)
        return result

    def candidates(self, key):
        return self.alternatives.get(key, (self[key],)) if key in self else ()


def _is_literal_process_state(node: ast.AST | None) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return all(_is_literal_process_state(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            (key is None or _is_literal_process_state(key))
            and _is_literal_process_state(value)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    return node is None


def _visit_if_with_conservative_aliases(visitor, node: ast.If) -> None:
    visitor.visit(node.test)
    if isinstance(node.test, ast.Constant):
        branch = node.body if bool(node.test.value) else node.orelse
        for statement in branch:
            visitor.visit(statement)
        return

    before = visitor._import_aliases.copy()
    for statement in node.body:
        visitor.visit(statement)
    body_aliases = visitor._import_aliases.copy()

    visitor._import_aliases = before.copy()
    for statement in node.orelse:
        visitor.visit(statement)
    else_aliases = visitor._import_aliases.copy()
    visitor._import_aliases = _merge_branch_aliases(
        visitor,
        body_aliases,
        else_aliases,
    )


def _merge_branch_aliases(visitor, *branches: _EffectAliases) -> _EffectAliases:
    merged = _EffectAliases()
    keys = set().union(*(branch.keys() for branch in branches))
    for key in keys:
        candidates = tuple(dict.fromkeys(value for branch in branches for value in branch.candidates(key)))
        forbidden = tuple(candidate for candidate in candidates if _alias_call_is_forbidden(visitor, candidate))
        if candidates:
            merged[key] = forbidden[0] if forbidden else candidates[0]
        if len(candidates) > 1:
            merged.alternatives[key] = candidates
    return merged


def _alias_call_is_forbidden(visitor, candidate: str) -> bool:
    local = candidate.startswith(_LOCAL_EFFECT_PREFIX)
    reference = candidate.removeprefix(_LOCAL_EFFECT_PREFIX)
    try:
        expression = ast.parse(f"{reference}()", mode="eval").body
    except SyntaxError:
        return False
    if not isinstance(expression, ast.Call):
        return False
    violation_code, _ = call_violation(
        expression,
        aliases={},
        effect_scope=visitor.effect_scope,
        imported_roots=visitor._imported_module_roots,
        module_state_names=visitor._module_state_names,
        local_names=visitor._current_local_names - visitor._current_import_names,
        local_reference=local,
    )
    return bool(violation_code)


class _PurityImportVisitor(ast.NodeVisitor):
    def visit_Import(self, node: ast.Import) -> None:
        self._record_import_aliases(node)
        for module in import_modules(node):
            self._check_import(module, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._record_import_aliases(node)
        module = node.module or ""
        effect_scope = str(getattr(self, "effect_scope", EFFECT_SCOPE_NONE))
        imported_names = {alias.name for alias in node.names}
        if process_argv_import_is_forbidden(module, imported_names):
            self._add("effect_import", "process sys.argv is forbidden; use the declared cli.argv input", node, suggested_fix_type="fix_contract")
            return
        if terminal_stream_import_is_forbidden(module, imported_names, effect_scope=effect_scope):
            self._add("effect_import", "terminal streams are forbidden by the selected effect policy", node, suggested_fix_type="fix_ruleset")
            return
        if from_import_effect_is_forbidden(module, imported_names, effect_scope=effect_scope):
            self._add("effect_import", f"Python IO import is forbidden by the selected effect policy: {module}", node, suggested_fix_type="fix_ruleset")
            return
        self._check_import(module, node)

    def _record_import_aliases(self, node: ast.Import | ast.ImportFrom) -> None:
        aliases = getattr(self, "_import_aliases", None)
        if isinstance(aliases, dict):
            aliases.update(import_aliases_from_node(node))
        roots = getattr(self, "_imported_module_roots", None)
        if isinstance(roots, set):
            roots.update(imported_module_roots(node))


class _EffectVisitor(_PurityImportVisitor):
    """One effect traversal; resource structure and Node contracts stay outside."""

    def _init_effect_state(self, *, policy, effect_scope, resolved_calls=frozenset(),
                           initial_aliases=None, imported_roots=(), module_state_names=()):
        self.policy = policy
        self.effect_scope = effect_scope
        self._import_aliases = _EffectAliases(dict(initial_aliases or {}))
        self._module_effect_aliases = self._import_aliases.copy()
        self._imported_module_roots = set(imported_roots)
        self._module_state_names = set(module_state_names)
        self._current_local_names = set()
        self._current_import_names = set()
        self._current_global_names = set()
        self._resolved_calls = resolved_calls

    def _prepare_effect_module(self, node):
        for statement in node.body:
            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                self._record_import_aliases(statement)
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
                for target in targets:
                    self._module_state_names.update(_bound_names(target))
        from vibeflow.targets.python.quality.source_analysis.sdk_declarations import declaration_calls
        self._sdk_calls = declaration_calls(node)
        self._module_effect_aliases = self._import_aliases.copy()

    def visit_Module(self, node):
        self._prepare_effect_module(node)
        self._visit_module_body(node)

    def _visit_module_body(self, node, visit_statement=None):
        visit_statement = self.visit if visit_statement is None else visit_statement
        for statement in node.body:
            visit_statement(statement)
            self._module_effect_aliases = self._import_aliases.copy()

    def visit_FunctionDef(self, node):
        # Definition expressions use the enclosing scope. Parameters and body
        # assignments only bind names after entering the new function body.
        for expression in _function_definition_expressions(node):
            self.visit(expression)
        self._check_global_binding(node.name, node)
        self._visit_function_body(node)

    def visit_Lambda(self, node):
        for expression in _function_definition_expressions(node):
            self.visit(expression)
        self._visit_function_body(node)

    def _visit_function_body(self, node):
        self._visit_scoped_body(node)


    def _visit_scoped_body(self, node):
        previous_aliases = self._import_aliases.copy()
        previous_locals, previous_imports = self._current_local_names, self._current_import_names
        previous_globals = self._current_global_names
        bindings = _function_scope_bindings(node)
        self._current_global_names = bindings.global_names
        local_names = bindings.names - bindings.global_names - bindings.nonlocal_names
        self._current_local_names = (previous_locals | local_names) - bindings.global_names
        self._current_import_names = (previous_imports - local_names) | bindings.import_names
        for name in local_names:
            self._import_aliases.pop(name, None)
        for name in bindings.global_names:
            self._import_aliases.pop(name, None)
            if name in self._module_effect_aliases:
                self._import_aliases[name] = self._module_effect_aliases[name]
                if name in self._module_effect_aliases.alternatives:
                    self._import_aliases.alternatives[name] = self._module_effect_aliases.alternatives[name]
        try:
            if isinstance(node, ast.Lambda):
                self.visit(node.body)
            else:
                for statement in node.body:
                    self.visit(statement)
        finally:
            self._import_aliases = previous_aliases
            self._current_local_names, self._current_import_names = previous_locals, previous_imports
            self._current_global_names = previous_globals

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        for expression in (*node.bases, *(item.value for item in node.keywords), *node.decorator_list):
            self.visit(expression)
        self._check_global_binding(node.name, node)
        previous_globals = self._current_global_names
        bindings = _FunctionBindingCollector()
        for statement in node.body:
            bindings.visit(statement)
        self._current_global_names = bindings.global_names
        try:
            for statement in node.body:
                self.visit(statement)
        finally:
            self._current_global_names = previous_globals

    def visit_ListComp(self, node):
        steps = iter(_comprehension_evaluation_steps(node))
        first_iterable, _ = next(steps)
        self.visit(first_iterable)
        remaining = tuple(steps)
        local_names = remaining[0][1]
        outer_bindings = _comprehension_outer_bindings(node)
        previous_aliases = self._import_aliases.copy()
        previous_locals, previous_imports = self._current_local_names, self._current_import_names
        previous_globals = self._current_global_names
        self._current_local_names = previous_locals | local_names
        self._current_import_names = previous_imports - local_names
        self._current_global_names = previous_globals - local_names
        for name in local_names:
            self._import_aliases.pop(name, None)
        targets = {generator.target for generator in node.generators}
        try:
            for expression, _ in remaining:
                if expression in targets:
                    self._check_comprehension_target(expression)
                self.visit(expression)
        finally:
            # Assignment expressions bind the containing function. Iterations
            # may be empty, so retain both pre-loop and written alias facts.
            written_aliases = previous_aliases.copy()
            for name in outer_bindings:
                written_aliases.pop(name, None)
                if name in self._import_aliases:
                    written_aliases[name] = self._import_aliases[name]
                    if name in self._import_aliases.alternatives:
                        written_aliases.alternatives[name] = self._import_aliases.alternatives[name]
            self._current_local_names, self._current_import_names = previous_locals, previous_imports
            self._current_global_names = previous_globals
            self._import_aliases = (_merge_branch_aliases(self, previous_aliases, written_aliases)
                if outer_bindings else previous_aliases)

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def _check_comprehension_target(self, target):
        if isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._check_comprehension_target(item)
        elif isinstance(target, ast.Starred):
            self._check_comprehension_target(target.value)
        else:
            self._check_ambient_assignment(target, target)

    def _alias_views(self, *expressions):
        # Each view changes one joined alias. This is linear in the facts and
        # intentionally does not model correlations between independent aliases.
        names = sorted({item.id for expression in expressions if expression is not None
                        for item in ast.walk(expression) if isinstance(item, ast.Name)
                        and item.id in self._import_aliases.alternatives})
        yield self._import_aliases
        for name in names:
            for value in self._import_aliases.candidates(name):
                if value != self._import_aliases[name]:
                    yield {**self._import_aliases, name:value}

    def _call_alias_views(self, node):
        expressions = [node.func]
        functions = {qualified_reference_name(node.func, aliases) for aliases in self._alias_views(node.func)}
        if functions & {"getattr", "builtins.getattr", "vars", "builtins.vars"} and node.args:
            expressions.append(node.args[0])
        if functions & {"print", "builtins.print"}:
            expressions.extend(item.value for item in node.keywords if item.arg == "file")
        return self._alias_views(*expressions)

    def _reference_root(self, expression, aliases=None):
        aliases = self._import_aliases if aliases is None else aliases
        while isinstance(expression, ast.Subscript):
            expression = expression.value
        if isinstance(expression, ast.Call):
            function = qualified_reference_name(expression.func, aliases)
            if function in {"getattr", "builtins.getattr", "vars", "builtins.vars"} and expression.args:
                return self._reference_root(expression.args[0], aliases)
            if isinstance(expression.func, ast.Attribute) and expression.func.attr == "get":
                return self._reference_root(expression.func.value, aliases)
        return _root_name(expression) if expression is not None else ""

    def _is_local_reference(self, expression, aliases=None):
        aliases = self._import_aliases if aliases is None else aliases
        root = self._reference_root(expression, aliases)
        return (root in self._current_local_names and root not in aliases
                or aliases.get(root, "").startswith(_LOCAL_EFFECT_PREFIX))

    def _record_effect_assignment_aliases(self, node):
        candidates = []
        for aliases in self._alias_views(node.value):
            value = qualified_reference_name(node.value, aliases)
            if isinstance(node.value, ast.Call) and qualified_reference_name(node.value.func, aliases) in {"pathlib.Path", "argparse.ArgumentParser"}:
                value = qualified_reference_name(node.value.func, aliases)
            if value and self._is_local_reference(node.value, aliases) and not value.startswith(_LOCAL_EFFECT_PREFIX):
                # Preserve the leaf for conservative IO classification without
                # turning an unresolved local spelling into a host namespace.
                value = _LOCAL_EFFECT_PREFIX + value
            if value and value not in candidates:
                candidates.append(value)
        targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            values = tuple(value for value in candidates if value != target.id)
            if values:
                self._import_aliases[target.id] = values[0]
                if len(values) > 1:
                    self._import_aliases.alternatives[target.id] = values
            else:
                self._import_aliases.pop(target.id, None)

    def visit_Assign(self, node):
        self._record_effect_assignment_aliases(node)
        for target in node.targets:
            self._check_ambient_assignment(target, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self._record_effect_assignment_aliases(node)
            self._check_ambient_assignment(node.target, node)
            self.generic_visit(node)
        else:
            if not isinstance(node.target, ast.Name):
                self.visit(node.target)
            self.visit(node.annotation)

    def _check_global_binding(self, name, node):
        if name in self._current_global_names and self.effect_scope != EFFECT_SCOPE_GLOBAL_STATE:
            self._add("global_state", f"must not write module global: {name}", node,
                suggested_fix_type="configure_effect_rules")

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self._check_global_binding(node.id, node)

    def _record_import_aliases(self, node):
        for name in import_aliases_from_node(node):
            self._check_global_binding(name, node)
        super()._record_import_aliases(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            self._check_global_binding(node.name, node)
        self.generic_visit(node)

    def visit_match_case(self, node):
        bindings = _FunctionBindingCollector()
        bindings.visit(node.pattern)
        for name in sorted(bindings.names):
            self._check_global_binding(name, node.pattern)
        self.generic_visit(node)

    def visit_NamedExpr(self, node):
        self._record_effect_assignment_aliases(node)
        self._check_ambient_assignment(node.target, node)
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        self._check_ambient_assignment(node.target, node)
        self.generic_visit(node)

    def visit_Delete(self, node):
        for target in node.targets:
            self._check_ambient_assignment(target, node)
        self.generic_visit(node)

    def visit_If(self, node):
        _visit_if_with_conservative_aliases(self, node)

    def visit_Call(self, node):
        self._check_effect_reference(node)
        self._check_effect_call(node)
        self.generic_visit(node)

    def _check_effect_call(self, node):
        for aliases in self._call_alias_views(node):
            code, forbidden = call_violation(node, aliases=aliases,
                effect_scope=self.effect_scope, imported_roots=self._imported_module_roots,
                module_state_names=self._module_state_names - self._current_local_names,
                local_names=self._current_local_names - aliases.keys(),
                source_resolved=getattr(node, "_source_reference_position", (node.lineno, node.col_offset + 1)) in self._resolved_calls,
                local_reference=(not isinstance(node.func, ast.Name) and self._is_local_reference(node.func, aliases)
                    or qualified_reference_name(node.func, aliases).startswith(_LOCAL_EFFECT_PREFIX)))
            if code:
                if forbidden.startswith(_LOCAL_EFFECT_PREFIX):
                    forbidden = _call_name(node.func)
                self._add(code, f"banned call: {forbidden}", node, suggested_fix_type="configure_effect_rules")
                break

    def _check_effect_reference(self, node):
        views = self._call_alias_views(node) if isinstance(node, ast.Call) else self._alias_views(node)
        for aliases in views:
            if self._is_local_reference(node, aliases):
                continue
            argv_reference = process_argv_reference(node, aliases)
            if argv_reference:
                self._add("effect_call", f"banned process argument access: {argv_reference}; use the declared cli.argv input", node, suggested_fix_type="fix_contract")
                break
            terminal_reference = terminal_stream_reference(node, aliases)
            if terminal_reference and terminal_stream_is_forbidden(self.effect_scope):
                self._add("effect_call", f"banned terminal stream access: {terminal_reference}", node, suggested_fix_type="configure_effect_rules")
                break

    def visit_Attribute(self, node):
        self._check_effect_reference(node)
        self.generic_visit(node)

    def visit_Subscript(self, node):
        self._check_effect_reference(node)
        self.generic_visit(node)

    def visit_Raise(self, node):
        if not isinstance(node.exc, ast.Call):
            for aliases in self._alias_views(node.exc):
                if self._is_local_reference(node.exc, aliases):
                    continue
                reference = system_exit_reference(node.exc, aliases)
                if reference and system_exit_is_forbidden(self.effect_scope):
                    self._add("effect_call", f"banned process exit: {reference}", node, suggested_fix_type="configure_effect_rules")
                    break
        self.generic_visit(node)

    def _ambient_targets(self, target):
        if not isinstance(target, (ast.Attribute, ast.Subscript)):
            return ()
        reference = target if isinstance(target, ast.Attribute) else target.value
        names = tuple(dict.fromkeys(qualified_reference_name(reference, aliases) for aliases in self._alias_views(reference)
            if not self._is_local_reference(reference, aliases)))
        return tuple(name for name in names if name.split(".", 1)[0] in self._imported_module_roots
                     or name.split(".", 1)[0] in self._module_state_names)


    def _check_ambient_assignment(self, target, node):
        if isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._check_ambient_assignment(item, node)
            return
        if isinstance(target, ast.Starred):
            self._check_ambient_assignment(target.value, node)
            return
        names = self._ambient_targets(target)
        forbidden = next((name for name in names if ambient_assignment_is_forbidden(name)), "")
        if forbidden:
            self._add("effect_call", f"must not mutate forbidden process state: {forbidden}", node, suggested_fix_type="configure_effect_rules")
        elif names and self.effect_scope != EFFECT_SCOPE_GLOBAL_STATE:
            self._add("global_state", f"must not mutate ambient module state: {names[0]}", node, suggested_fix_type="configure_effect_rules")

    def _check_import(self, module, node):
        code = import_violation_code(module, effect_scope=self.effect_scope, policy=self.policy,
            imported_names={alias.name for alias in node.names} if isinstance(node, ast.ImportFrom) else None)
        if code:
            self._add(code, f"banned import: {module}", node, suggested_fix_type="configure_effect_rules")


class NodePurityVisitor(_EffectVisitor):
    """Selected effects in a borrowed Node source slice."""

    def __init__(self, *, policy, source, effect_scope=EFFECT_SCOPE_NONE,
                 initial_aliases=None, imported_roots=(), module_state_names=(), resolved_calls=frozenset()):
        self.source = source
        self.violations = []
        self._init_effect_state(policy=policy, effect_scope=effect_scope, initial_aliases=initial_aliases,
            imported_roots=imported_roots, module_state_names=module_state_names, resolved_calls=resolved_calls)

    def _add(self, code, message, node, *, suggested_fix_type="fix_node"):
        self.violations.append(_violation(code, message, source=self.source,
            line=getattr(node, "lineno", 1), column=getattr(node, "col_offset", 0) + 1,
            suggested_fix_type=suggested_fix_type))


class ModulePurityVisitor(NodePurityVisitor):
    """Selected effects and finite declaration structure for module source."""

    def __init__(self, *, policy, source, node_class_name="", audit_all_definitions=False,
                 effect_scope=EFFECT_SCOPE_NONE, resolved_calls=frozenset()):
        self.node_class_name = node_class_name
        self.audit_all_definitions = audit_all_definitions
        super().__init__(policy=policy, source=source, effect_scope=effect_scope, resolved_calls=resolved_calls)

    def visit_Module(self, node):
        self._prepare_effect_module(node)
        reachable_helpers = ({statement.name for statement in node.body
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))}
            if self.audit_all_definitions else _reachable_module_helpers(node, self.node_class_name))
        self._visit_module_body(node, lambda statement:
            self._visit_module_statement(statement, reachable_helpers=reachable_helpers))

    def _visit_module_statement(self, stmt, *, reachable_helpers):
        kind = module_statement_kind(stmt)
        if kind == "import":
            self.visit(stmt)
        elif isinstance(stmt, ast.ClassDef):
            if self.audit_all_definitions:
                self.visit(stmt)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name in reachable_helpers:
            self.visit(stmt)
        elif kind == "assignment":
            if (stmt.value not in getattr(self, "_sdk_calls", ()) and not _module_assignment_is_allowed(stmt)
                    and not (self.effect_scope == EFFECT_SCOPE_GLOBAL_STATE and _is_literal_process_state(stmt.value))):
                self._add("module_global_state", "module-level mutable state or initialization is forbidden by the selected declaration policy", stmt,
                    suggested_fix_type="configure_effect_rules")
            self.visit(stmt)
        elif kind not in {"definition", "docstring"}:
            self._add("module_side_effect", "module top level must separate declarations from initialization", stmt,
                suggested_fix_type="move_to_lifecycle")
