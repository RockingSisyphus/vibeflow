from __future__ import annotations

import ast

from vibeflow.targets.python.quality.source_analysis.ast_rules import (
    import_aliases,
    import_aliases_from_node,
    imported_module_roots,
    import_modules,
    module_statement_kind,
    qualified_reference_name,
    record_assignment_aliases,
)
from vibeflow.core.contracts import provider_keys
from vibeflow.core.constants import EFFECT_SCOPE_GLOBAL_STATE, EFFECT_SCOPE_NONE
from vibeflow.core.descriptors import NodeContractDescriptor
from vibeflow.targets.python.quality.source_analysis.effects import (
    ambient_assignment_is_forbidden,
    call_violation,
    dynamic_namespace_reference,
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
from vibeflow.targets.python.quality.source_analysis.ast_rules import call_name as _call_name, module_assignment_is_allowed as _module_assignment_is_allowed
from vibeflow.targets.python.quality.source_analysis.helpers import (
    _assigns_resource_field,
    _literal_subscript_key,
    _module_matches,
    _root_name,
    _violation,
)
from vibeflow.targets.python.quality.source_analysis.input_tracking import (
    _NodeDataTrackingMixin,
    _is_input_reference,
    _reachable_module_helpers,
    _trace_helper_input_parameters,
)
from vibeflow.targets.python.quality.source_analysis.types import MUTATING_METHODS, PurityPolicy, PurityViolation, _SourceInfo


from vibeflow.targets.python.quality.source_analysis.bindings import _bound_names, _comprehension_evaluation_steps, _comprehension_outer_bindings, _function_definition_expressions, _function_scope_bindings


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
    try:
        expression = ast.parse(f"{candidate}()", mode="eval").body
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
        self._import_aliases = _EffectAliases({"Path": "pathlib.Path", **dict(initial_aliases or {})})
        self._module_effect_aliases = self._import_aliases.copy()
        self._imported_module_roots = set(imported_roots)
        self._module_state_names = set(module_state_names)
        self._current_local_names = set()
        self._input_aliases = set()
        self._current_import_names = set()
        self._resolved_calls = resolved_calls
        from vibeflow.targets.python.quality.source_analysis.exit_stacks import ExitStackCalls
        self._exit_stacks = ExitStackCalls(frozenset(), {})

    def _prepare_effect_module(self, node):
        for statement in node.body:
            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                self._record_import_aliases(statement)
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
                for target in targets:
                    self._module_state_names.update(_bound_names(target))
        from vibeflow.targets.python.quality.source_analysis.exit_stacks import analyze_exit_stacks
        self._exit_stacks = analyze_exit_stacks(node, self._import_aliases)
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
        bindings = _function_scope_bindings(node)
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

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_ListComp(self, node):
        steps = iter(_comprehension_evaluation_steps(node))
        first_iterable, _ = next(steps)
        self.visit(first_iterable)
        remaining = tuple(steps)
        local_names = remaining[0][1]
        outer_bindings = _comprehension_outer_bindings(node)
        previous_aliases = self._import_aliases.copy()
        previous_locals, previous_imports = self._current_local_names, self._current_import_names
        previous_inputs = self._input_aliases
        self._current_local_names = previous_locals | local_names
        self._current_import_names = previous_imports - local_names
        self._input_aliases = previous_inputs - local_names
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
            escaping_inputs = self._input_aliases & outer_bindings
            self._current_local_names, self._current_import_names = previous_locals, previous_imports
            self._import_aliases = (_merge_branch_aliases(self, previous_aliases, written_aliases)
                if outer_bindings else previous_aliases)
            self._input_aliases = previous_inputs | escaping_inputs

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
            if isinstance(target, (ast.Attribute, ast.Subscript)) and _is_input_reference(target.value, self._input_aliases):
                self._add("input_mutation", "must not mutate inputs in comprehension target", target, suggested_fix_type="fix_node")

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

    def _reference_root(self, expression):
        while isinstance(expression, ast.Subscript):
            expression = expression.value
        if isinstance(expression, ast.Call):
            function = qualified_reference_name(expression.func, self._import_aliases)
            if function in {"getattr", "builtins.getattr", "vars", "builtins.vars"} and expression.args:
                return self._reference_root(expression.args[0])
            if isinstance(expression.func, ast.Attribute) and expression.func.attr == "get":
                return self._reference_root(expression.func.value)
        return _root_name(expression) if expression is not None else ""

    def _is_local_reference(self, expression):
        root = self._reference_root(expression)
        return root in self._current_local_names and root not in self._import_aliases

    def _record_effect_assignment_aliases(self, node):
        candidates = tuple(dict.fromkeys(qualified_reference_name(node.value, aliases)
            for aliases in self._alias_views(node.value)))
        candidates = tuple(value for value in candidates if value)
        record_assignment_aliases(node, self._import_aliases)
        if len(candidates) > 1:
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            for target in targets:
                if isinstance(target, ast.Name):
                    self._import_aliases[target.id] = candidates[0]
                    self._import_aliases.alternatives[target.id] = candidates

    def visit_Assign(self, node):
        self._record_effect_assignment_aliases(node)
        for target in node.targets:
            self._check_ambient_assignment(target, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        self._record_effect_assignment_aliases(node)
        self._check_ambient_assignment(node.target, node)
        self.generic_visit(node)

    def visit_NamedExpr(self, node):
        if isinstance(node.target, ast.Name):
            if _is_input_reference(node.value, self._input_aliases):
                self._input_aliases.add(node.target.id)
            else:
                self._input_aliases.discard(node.target.id)
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
                stack_cleanup=id(node) in self._exit_stacks.closes,
                local_reference=not isinstance(node.func, ast.Name) and self._is_local_reference(node.func))
            if code:
                self._add(code, f"banned call: {forbidden}", node, suggested_fix_type="configure_effect_rules")
                break
        deferred = self._exit_stacks.deferred.get(id(node))
        if deferred is not None:
            self._check_effect_call(deferred)

    def _check_effect_reference(self, node):
        if self._is_local_reference(node):
            return
        views = self._call_alias_views(node) if isinstance(node, ast.Call) else self._alias_views(node)
        for aliases in views:
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
        if not self._is_local_reference(node):
            for aliases in self._alias_views(node):
                reference = dynamic_namespace_reference(node, aliases=aliases, imported_roots=self._imported_module_roots)
                if reference:
                    self._add("banned_call", f"dynamic module namespace lookup is forbidden: {reference}", node, suggested_fix_type="configure_effect_rules")
                    break
        self.generic_visit(node)

    def visit_Raise(self, node):
        if not isinstance(node.exc, ast.Call) and not self._is_local_reference(node.exc):
            for aliases in self._alias_views(node.exc):
                reference = system_exit_reference(node.exc, aliases)
                if reference and system_exit_is_forbidden(self.effect_scope):
                    self._add("effect_call", f"banned process exit: {reference}", node, suggested_fix_type="configure_effect_rules")
                    break
        self.generic_visit(node)

    def visit_Global(self, node):
        if self.effect_scope != EFFECT_SCOPE_GLOBAL_STATE:
            self._add("global_state", "global mutation is forbidden", node, suggested_fix_type="configure_effect_rules")

    def visit_Nonlocal(self, node):
        if self.effect_scope != EFFECT_SCOPE_GLOBAL_STATE:
            self._add("global_state", "nonlocal mutation is forbidden", node, suggested_fix_type="configure_effect_rules")

    def _ambient_targets(self, target):
        if not isinstance(target, (ast.Attribute, ast.Subscript)) or self._is_local_reference(target):
            return ()
        reference = target if isinstance(target, ast.Attribute) else target.value
        names = tuple(dict.fromkeys(qualified_reference_name(reference, aliases) for aliases in self._alias_views(reference)))
        return tuple(name for name in names if name.split(".", 1)[0] in self._imported_module_roots
                     or name.split(".", 1)[0] in self._module_state_names)

    def _ambient_target(self, target):
        return next(iter(self._ambient_targets(target)), "")

    def _check_ambient_assignment(self, target, node):
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


class NodePurityVisitor(_NodeDataTrackingMixin, _EffectVisitor):

    def __init__(self, *, policy, source, contract, known_node_modules, line_offset,
                 effect_scope=EFFECT_SCOPE_NONE, initial_aliases=None, authorized_resource_imports=None,
                 imported_roots=None, module_state_names=None, resolved_calls=frozenset(), input_parameters=None,
                 node_call_sites=frozenset(), node_internal_read_sites=frozenset()):
        self.source, self.contract, self.line_offset = source, contract, line_offset
        self.known_node_modules = set(known_node_modules)
        self.authorized_resource_imports = authorized_resource_imports or set()
        self._node_call_sites, self._node_internal_read_sites = node_call_sites, node_internal_read_sites
        self.violations = []
        self._input_parameters = input_parameters or {}
        self._output_dicts = {}
        self._current_function = ""
        self._init_effect_state(policy=policy, effect_scope=effect_scope, resolved_calls=resolved_calls,
            initial_aliases=initial_aliases, imported_roots=imported_roots or (), module_state_names=module_state_names or ())

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in (*node.bases, *(item.value for item in node.keywords), *node.decorator_list):
            self.visit(expression)
        self._import_aliases.update(import_aliases(node))
        for child in ast.walk(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                self._imported_module_roots.update(imported_module_roots(child))
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.visit(stmt)
            else:
                self.visit(stmt)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node.name == "run_pure":
            self._add("async_run_pure", "run_pure must not be async", node, suggested_fix_type="fix_contract")
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def _visit_function_body(self, node):
        previous, previous_inputs = self._current_function, self._input_aliases
        self._current_function = getattr(node, "name", "")
        bindings = _function_scope_bindings(node)
        shadowed = (bindings.names - bindings.nonlocal_names) | bindings.global_names
        self._input_aliases = (previous_inputs - shadowed) | set(self._input_parameters.get(self._current_function, ()))
        if self._current_function == "run_pure":
            if any(argument.arg == "inputs" for argument in
                   (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)):
                self._input_aliases.add("inputs")
            for child in ast.walk(node):
                if isinstance(child, (ast.Yield, ast.YieldFrom)):
                    self._add("generator_run_pure", "run_pure must not yield values", child, suggested_fix_type="fix_contract")
        try:
            super()._visit_function_body(node)
        finally:
            self._current_function, self._input_aliases = previous, previous_inputs

    def visit_Assign(self, node: ast.Assign) -> None:
        self._track_input_alias(node)
        self._track_output_literal(node)
        self._track_output_key_assignment(node)
        if _assigns_resource_field(node):
            self._add("resource_field", "node must not hold Context, boundary, session, browser, client, driver, cursor, or engine", node)
        for target in node.targets:
            self._check_assignment_target(target, node)
        super().visit_Assign(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if _assigns_resource_field(node):
            self._add("resource_field", "node must not hold Context, boundary, session, browser, client, driver, cursor, or engine", node)
        self._check_assignment_target(node.target, node)
        if isinstance(node.target, ast.Name):
            if node.value is not None and self._is_node_input_reference(node.value):
                self._input_aliases.add(node.target.id)
            else:
                self._input_aliases.discard(node.target.id)
        super().visit_AnnAssign(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_assignment_target(node.target, node)
        super().visit_AugAssign(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._check_assignment_target(target, node)
        super().visit_Delete(node)

    def visit_Call(self, node):
        name = _call_name(node.func)
        self._check_monkey_patch_call(name, node)
        self._check_node_coupling_call(name, node)
        self._check_input_mutation_call(node)
        self._check_params_get_call(node)
        super().visit_Call(node)

    def visit_While(self, node: ast.While) -> None:
        if self._current_function == "run_pure":
            self._add(
                "internal_loop",
                "run_pure must not use while loops; model repeated execution with topology loops",
                node,
                suggested_fix_type="fix_config",
            )
        self.generic_visit(node)

    def visit_Attribute(self, node):
        root = _root_name(node)
        if (node.lineno, node.col_offset + 1) in self._node_internal_read_sites:
            self._add("node_internal_read", f"node must not read another node internals: {root}.{node.attr}", node, suggested_fix_type="move_to_nodeset")
        super().visit_Attribute(node)

    def visit_Return(self, node: ast.Return) -> None:
        if self._current_function != "run_pure" or self.contract is None:
            self.generic_visit(node)
            return
        keys, dynamic = self._return_keys(node.value)
        if dynamic:
            self._add("dynamic_output_key", "run_pure output keys must be string literals declared in descriptor contract.provides", node, suggested_fix_type="fix_contract")
        elif keys is not None:
            provides = set(provider_keys(self.contract.provides))
            extra = keys - provides
            missing = provides - keys
            if extra:
                self._add("undeclared_output", f"run_pure returns undeclared outputs: {sorted(extra)}", node, suggested_fix_type="fix_contract")
            if missing:
                self._add("missing_output", f"run_pure misses declared outputs: {sorted(missing)}", node, suggested_fix_type="fix_contract")
        self.generic_visit(node)

    def _check_import(self, module, node):
        if module in self.known_node_modules and (getattr(node, "lineno", 0), module) not in self.authorized_resource_imports:
            self._add("node_import", f"node must not import another node module: {module}", node, suggested_fix_type="move_to_nodeset")
            return
        super()._check_import(module, node)

    def _check_monkey_patch_call(self, name: str, node: ast.Call) -> None:
        if name in {"setattr", "delattr"}:
            self._add("monkey_patch", f"monkey patching is forbidden: {name}", node, suggested_fix_type="fix_node")

    def _check_node_coupling_call(self, name: str, node: ast.Call) -> None:
        if (node.lineno, node.col_offset + 1) in self._node_call_sites:
            self._add("node_direct_call", f"node must not directly call another node: {name}", node, suggested_fix_type="move_to_nodeset")

    def _add(
        self,
        code: str,
        message: str,
        node: ast.AST,
        *,
        failure_layer: str = "implementation",
        suggested_fix_type: str = "fix_node",
    ) -> None:
        self.violations.append(
            _violation(
                code,
                message,
                source=self.source,
                line=self.line_offset + getattr(node, "lineno", 1),
                column=getattr(node, "col_offset", 0) + 1,
                failure_layer=failure_layer,
                suggested_fix_type=suggested_fix_type,
            )
        )


class ModulePurityVisitor(_EffectVisitor):
    def __init__(self, *, policy, source, node_class_name, known_node_modules,
                 effect_scope=EFFECT_SCOPE_NONE, audit_all_definitions=False, input_parameters=None,
                 authorized_resource_imports=None, resolved_calls=frozenset(), node_call_sites=frozenset(),
                 node_internal_read_sites=frozenset()):
        self.source, self.node_class_name = source, node_class_name
        self.known_node_modules = set(known_node_modules)
        self.authorized_resource_imports = authorized_resource_imports or set()
        self._node_call_sites, self._node_internal_read_sites = node_call_sites, node_internal_read_sites
        self.audit_all_definitions = audit_all_definitions
        self.violations = []
        self._helper_input_parameters = {}
        self._input_parameters = input_parameters
        self._init_effect_state(policy=policy, effect_scope=effect_scope, resolved_calls=resolved_calls)

    def visit_Module(self, node: ast.Module) -> None:
        self._prepare_effect_module(node)
        self._helper_input_parameters = self._input_parameters if self._input_parameters is not None else _trace_helper_input_parameters(node, self.node_class_name)
        reachable_helpers = (
            {
                statement.name
                for statement in node.body
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if self.audit_all_definitions
            else _reachable_module_helpers(node, self.node_class_name)
        )
        self._visit_module_body(node, lambda statement:
            self._visit_module_statement(statement, reachable_helpers=reachable_helpers))

    def _visit_function_body(self, node):
        previous = self._input_aliases
        bindings = _function_scope_bindings(node)
        shadowed = (bindings.names - bindings.nonlocal_names) | bindings.global_names
        self._input_aliases = (previous - shadowed) | set(self._helper_input_parameters.get(getattr(node, "name", ""), ()))
        try:
            super()._visit_function_body(node)
        finally:
            self._input_aliases = previous

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_helper_input_assignment(target, node)
        aliases_input = self._is_helper_input_reference(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                if aliases_input:
                    self._input_aliases.add(target.id)
                else:
                    self._input_aliases.discard(target.id)
        super().visit_Assign(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_helper_input_assignment(node.target, node)
        if isinstance(node.target, ast.Name):
            if node.value is not None and self._is_helper_input_reference(node.value):
                self._input_aliases.add(node.target.id)
            else:
                self._input_aliases.discard(node.target.id)
        super().visit_AnnAssign(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_helper_input_assignment(node.target, node)
        super().visit_AugAssign(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if self._helper_target_mutates_input(target):
                self._add("input_mutation", "module helper must not delete values from inputs", node, suggested_fix_type="fix_node")
        super().visit_Delete(node)

    def _visit_module_statement(self, stmt: ast.stmt, *, reachable_helpers: set[str]) -> None:
        kind = module_statement_kind(stmt)
        if kind == "import":
            self.visit(stmt)
        elif isinstance(stmt, ast.ClassDef):
            if self.audit_all_definitions:
                self.generic_visit(stmt)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name in reachable_helpers:
            self.visit(stmt)
        elif kind == "assignment":
            self._check_module_assignment(stmt)
        elif kind not in {"definition", "docstring"}:
            self._add("module_side_effect", "node module top level may only contain imports, definitions, immutable constants, and docstrings", stmt, suggested_fix_type="move_to_lifecycle")

    def visit_Call(self, node):
        name = _call_name(node.func)
        if (node.lineno, node.col_offset + 1) in self._node_call_sites:
            self._add("node_direct_call", f"module helper must not directly call another node: {name}", node, suggested_fix_type="move_to_nodeset")
        if name in {"setattr", "delattr"}:
            self._add("monkey_patch", f"monkey patching is forbidden in module helper: {name}", node, suggested_fix_type="fix_node")
        if isinstance(node.func, ast.Attribute) and node.func.attr in MUTATING_METHODS and self._is_helper_input_reference(node.func.value):
            self._add("input_mutation", f"module helper must not mutate inputs via {node.func.attr}", node, suggested_fix_type="fix_node")
        super().visit_Call(node)

    def visit_Attribute(self, node):
        if (node.lineno, node.col_offset + 1) in self._node_internal_read_sites:
            self._add("node_internal_read", "module helper must not read another node internals", node, suggested_fix_type="move_to_nodeset")
        super().visit_Attribute(node)

    def _check_import(self, module, node):
        if module in self.known_node_modules and (getattr(node, "lineno", 0), module) not in self.authorized_resource_imports:
            self._add("node_import", f"node must not import another node module: {module}", node, suggested_fix_type="move_to_nodeset")
            return
        super()._check_import(module, node)

    def _check_module_assignment(self, node: ast.Assign | ast.AnnAssign) -> None:
        if node.value in getattr(self, "_sdk_calls", ()):
            self.visit(node)
            return
        if not _module_assignment_is_allowed(node) and not (
            self.effect_scope == EFFECT_SCOPE_GLOBAL_STATE
            and _is_literal_process_state(node.value)
        ):
            self._add("module_global_state", "module-level mutable state or side-effect construction is forbidden", node, suggested_fix_type="configure_effect_rules")
        self.visit(node)

    def _check_helper_input_assignment(self, target: ast.AST, node: ast.AST) -> None:
        if self._helper_target_mutates_input(target):
            self._add("input_mutation", "module helper must not mutate inputs", node, suggested_fix_type="fix_node")

    def _helper_target_mutates_input(self, target: ast.AST) -> bool:
        return isinstance(target, (ast.Subscript, ast.Attribute)) and self._is_helper_input_reference(target.value)

    def _is_helper_input_reference(self, node: ast.AST) -> bool:
        return _is_input_reference(node, self._input_aliases)

    def _add(self, code: str, message: str, node: ast.AST, *, suggested_fix_type: str) -> None:
        self.violations.append(
            _violation(
                code,
                message,
                source=self.source,
                line=getattr(node, "lineno", 1),
                column=getattr(node, "col_offset", 0) + 1,
                suggested_fix_type=suggested_fix_type,
            )
        )
