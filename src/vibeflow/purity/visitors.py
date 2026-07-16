from __future__ import annotations

import ast

from vibeflow.purity.ast_rules import (
    import_aliases,
    import_aliases_from_node,
    import_modules,
    module_statement_kind,
)
from vibeflow.data_contract import provider_keys
from vibeflow.node import EFFECT_SCOPE_NONE, NodeContract
from vibeflow.purity.effects import (
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
from vibeflow.purity.helpers import (
    _assigns_resource_field,
    _call_name,
    _class_looks_like_node,
    _is_base_lib_module,
    _is_boundary_import,
    _is_node_module,
    _literal_subscript_key,
    _module_assignment_is_allowed,
    _module_matches,
    _root_name,
    _violation,
)
from vibeflow.purity.input_tracking import (
    _NodeDataTrackingMixin,
    _is_input_reference,
    _reachable_module_helpers,
    _trace_helper_input_parameters,
)
from vibeflow.purity.types import MUTATING_METHODS, PurityPolicy, PurityViolation, _SourceInfo


class _PurityImportVisitor(ast.NodeVisitor):
    def visit_Import(self, node: ast.Import) -> None:
        self._record_import_aliases(node)
        for module in import_modules(node):
            self._check_import(module, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._record_import_aliases(node)
        module = node.module or ""
        if _is_boundary_import(module) or any(alias.name in {"GlobalBoundary", "BoundaryRegistry"} for alias in node.names):
            self._add("boundary_import", f"node must not import boundary APIs: {module}", node, suggested_fix_type="move_to_boundary")
            return
        effect_scope = str(getattr(self, "effect_scope", EFFECT_SCOPE_NONE))
        imported_names = {alias.name for alias in node.names}
        if process_argv_import_is_forbidden(module, imported_names):
            self._add("effect_import", "process sys.argv is forbidden; use the declared cli.argv input", node, suggested_fix_type="fix_contract")
            return
        if terminal_stream_import_is_forbidden(module, imported_names, effect_scope=effect_scope):
            self._add("effect_import", "terminal streams require flow_kind='io'", node, suggested_fix_type="move_to_boundary")
            return
        if from_import_effect_is_forbidden(module, imported_names, effect_scope=effect_scope):
            self._add("effect_import", f"Python IO import requires flow_kind='document' or 'data_store': {module}", node, suggested_fix_type="fix_contract")
            return
        self._check_import(module, node)

    def _record_import_aliases(self, node: ast.Import | ast.ImportFrom) -> None:
        aliases = getattr(self, "_import_aliases", None)
        if isinstance(aliases, dict):
            aliases.update(import_aliases_from_node(node))


class NodePurityVisitor(_NodeDataTrackingMixin, _PurityImportVisitor):
    def __init__(
        self,
        *,
        policy: PurityPolicy,
        source: _SourceInfo,
        contract: NodeContract | None,
        known_node_modules: tuple[str, ...],
        known_node_class_names: tuple[str, ...],
        line_offset: int,
        effect_scope: str = EFFECT_SCOPE_NONE,
    ) -> None:
        self.policy = policy
        self.source = source
        self.contract = contract
        self.known_node_modules = set(known_node_modules)
        self.known_node_class_names = set(known_node_class_names)
        self.line_offset = line_offset
        self.effect_scope = effect_scope
        self.violations: list[PurityViolation] = []
        self._input_aliases: set[str] = set()
        self._output_dicts: dict[str, set[str]] = {}
        self._current_function = ""
        self._import_aliases: dict[str, str] = {"Path": "pathlib.Path"}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._import_aliases.update(import_aliases(node))
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.visit(stmt)
            elif isinstance(stmt, (ast.Assign, ast.AnnAssign)) and _assigns_resource_field(stmt):
                self._add("resource_field", "node must not hold Context, boundary, session, browser, client, driver, cursor, or engine", stmt)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node.name == "run_pure":
            self._add("async_run_pure", "run_pure must not be async", node, suggested_fix_type="fix_contract")
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self._current_function
        self._current_function = node.name
        if node.name == "run_pure":
            for child in ast.walk(node):
                if isinstance(child, (ast.Yield, ast.YieldFrom)):
                    self._add("generator_run_pure", "run_pure must not yield values", child, suggested_fix_type="fix_contract")
        self.generic_visit(node)
        self._current_function = previous

    def visit_Global(self, node: ast.Global) -> None:
        self._add("global_state", "global mutation is forbidden", node, suggested_fix_type="move_to_boundary")

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self._add("global_state", "nonlocal mutation is forbidden", node, suggested_fix_type="move_to_boundary")

    def visit_Assign(self, node: ast.Assign) -> None:
        self._track_input_alias(node)
        self._track_output_literal(node)
        self._track_output_key_assignment(node)
        if _assigns_resource_field(node):
            self._add("resource_field", "node must not hold Context, boundary, session, browser, client, driver, cursor, or engine", node)
        for target in node.targets:
            self._check_assignment_target(target, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if _assigns_resource_field(node):
            self._add("resource_field", "node must not hold Context, boundary, session, browser, client, driver, cursor, or engine", node)
        self._check_assignment_target(node.target, node)
        if isinstance(node.target, ast.Name):
            if node.value is not None and self._is_node_input_reference(node.value):
                self._input_aliases.add(node.target.id)
            else:
                self._input_aliases.discard(node.target.id)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_assignment_target(node.target, node)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if self._target_mutates_node_input(target):
                self._add("input_mutation", "node must not delete values from inputs", node, suggested_fix_type="fix_node")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        self._check_banned_call(name, node)
        self._check_monkey_patch_call(name, node)
        self._check_node_coupling_call(name, node)
        self._check_input_mutation_call(node)
        self._check_params_get_call(node)
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        if self._current_function == "run_pure":
            self._add(
                "internal_loop",
                "run_pure must not use while loops; model repeated execution with topology loops",
                node,
                suggested_fix_type="fix_config",
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        root = _root_name(node)
        if root in self.known_node_class_names and node.attr in {"NODE_INFO", "CONTRACT"}:
            self._add("node_internal_read", f"node must not read another node internals: {root}.{node.attr}", node, suggested_fix_type="move_to_nodeset")
        argv_reference = process_argv_reference(node, self._import_aliases)
        if argv_reference:
            self._add("effect_call", f"banned process argument access: {argv_reference}; use the declared cli.argv input", node, suggested_fix_type="fix_contract")
        terminal_reference = terminal_stream_reference(node, self._import_aliases)
        if terminal_reference and terminal_stream_is_forbidden(self.effect_scope):
            self._add("effect_call", f"banned terminal stream access: {terminal_reference}", node, suggested_fix_type="move_to_boundary")
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if not isinstance(node.exc, ast.Call):
            reference = system_exit_reference(node.exc, self._import_aliases)
            if reference and system_exit_is_forbidden(self.effect_scope):
                self._add("effect_call", f"banned process exit: {reference}", node, suggested_fix_type="move_to_boundary")
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if self._current_function != "run_pure" or self.contract is None:
            self.generic_visit(node)
            return
        keys, dynamic = self._return_keys(node.value)
        if dynamic:
            self._add("dynamic_output_key", "run_pure output keys must be string literals declared in CONTRACT.provides", node, suggested_fix_type="fix_contract")
        elif keys is not None:
            provides = set(provider_keys(self.contract.provides))
            extra = keys - provides
            missing = provides - keys
            if extra:
                self._add("undeclared_output", f"run_pure returns undeclared outputs: {sorted(extra)}", node, suggested_fix_type="fix_contract")
            if missing:
                self._add("missing_output", f"run_pure misses declared outputs: {sorted(missing)}", node, suggested_fix_type="fix_contract")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.value, ast.Name) and node.value.id == "params":
            key = _literal_subscript_key(node)
            if key and key != "_global" and self.contract is not None and key not in self.contract.params_schema:
                self._add("undeclared_param", f"params key is not declared in CONTRACT.params_schema: {key}", node, failure_layer="contract", suggested_fix_type="fix_contract")
        self.generic_visit(node)

    def _check_import(self, module: str, node: ast.AST) -> None:
        if _is_boundary_import(module):
            self._add("boundary_import", f"node must not import boundary APIs: {module}", node, suggested_fix_type="move_to_boundary")
            return
        if _is_node_module(module) or module in self.known_node_modules:
            self._add("node_import", f"node must not import another node module: {module}", node, suggested_fix_type="move_to_nodeset")
            return
        if _is_base_lib_module(module):
            if _module_matches(module, self.policy.banned_base_lib_modules):
                self._add("base_lib_banned", f"node imports banned base_lib module: {module}", node, suggested_fix_type="fix_base_lib")
                return
            if not _module_matches(module, self.policy.allowed_base_lib_modules):
                self._add("base_lib_undeclared", f"node imports base_lib module not allowed by policy: {module}", node, suggested_fix_type="fix_base_lib")
                return
        violation_code = import_violation_code(module, effect_scope=self.effect_scope, policy=self.policy)
        if violation_code:
            self._add(violation_code, f"banned import: {module}", node, suggested_fix_type="move_to_boundary")

    def _check_banned_call(self, name: str, node: ast.Call) -> None:
        del name  # qualified aliases and scope are handled by the shared gate.
        violation_code, forbidden = call_violation(node, aliases=self._import_aliases, effect_scope=self.effect_scope)
        if violation_code:
            self._add(violation_code, f"banned call: {forbidden}", node, suggested_fix_type="move_to_boundary")

    def _check_monkey_patch_call(self, name: str, node: ast.Call) -> None:
        if name in {"setattr", "delattr"}:
            self._add("monkey_patch", f"monkey patching is forbidden: {name}", node, suggested_fix_type="fix_node")

    def _check_node_coupling_call(self, name: str, node: ast.Call) -> None:
        root = name.split(".", 1)[0]
        if name.endswith(".run_pure") or root in self.known_node_class_names:
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


class ModulePurityVisitor(_PurityImportVisitor):
    def __init__(
        self,
        *,
        policy: PurityPolicy,
        source: _SourceInfo,
        node_class_name: str,
        known_node_modules: tuple[str, ...],
        known_node_class_names: tuple[str, ...],
        effect_scope: str = EFFECT_SCOPE_NONE,
    ) -> None:
        self.policy = policy
        self.source = source
        self.node_class_name = node_class_name
        self.known_node_modules = set(known_node_modules)
        self.known_node_class_names = set(known_node_class_names)
        self.effect_scope = effect_scope
        self.violations: list[PurityViolation] = []
        self._import_aliases: dict[str, str] = {"Path": "pathlib.Path"}
        self._helper_input_parameters: dict[str, set[str]] = {}
        self._current_input_aliases: set[str] = set()

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                self._import_aliases.update(import_aliases_from_node(stmt))
        self._helper_input_parameters = _trace_helper_input_parameters(node, self.node_class_name)
        reachable_helpers = _reachable_module_helpers(node, self.node_class_name)
        for stmt in node.body:
            self._visit_module_statement(stmt, reachable_helpers=reachable_helpers)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self._current_input_aliases
        self._current_input_aliases = set(self._helper_input_parameters.get(node.name, ()))
        self.generic_visit(node)
        self._current_input_aliases = previous

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_helper_input_assignment(target, node)
        aliases_input = self._is_helper_input_reference(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                if aliases_input:
                    self._current_input_aliases.add(target.id)
                else:
                    self._current_input_aliases.discard(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_helper_input_assignment(node.target, node)
        if isinstance(node.target, ast.Name):
            if node.value is not None and self._is_helper_input_reference(node.value):
                self._current_input_aliases.add(node.target.id)
            else:
                self._current_input_aliases.discard(node.target.id)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_helper_input_assignment(node.target, node)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if self._helper_target_mutates_input(target):
                self._add("input_mutation", "module helper must not delete values from inputs", node, suggested_fix_type="fix_node")
        self.generic_visit(node)

    def _visit_module_statement(self, stmt: ast.stmt, *, reachable_helpers: set[str]) -> None:
        kind = module_statement_kind(stmt)
        if kind == "import":
            self.visit(stmt)
        elif isinstance(stmt, ast.ClassDef):
            self._record_module_class(stmt)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name in reachable_helpers:
            self.visit(stmt)
        elif kind == "assignment":
            self._check_module_assignment(stmt)
        elif kind not in {"definition", "docstring"}:
            self._add("module_side_effect", "node module top level may only contain imports, definitions, immutable constants, and docstrings", stmt, suggested_fix_type="move_to_boundary")

    def visit_Call(self, node: ast.Call) -> None:
        violation_code, forbidden = call_violation(node, aliases=self._import_aliases, effect_scope=self.effect_scope)
        if violation_code:
            self._add(violation_code, f"banned call in module helper: {forbidden}", node, suggested_fix_type="move_to_boundary")
        name = _call_name(node.func)
        root = name.split(".", 1)[0]
        if name.endswith(".run_pure") or root in self.known_node_class_names:
            self._add("node_direct_call", f"module helper must not directly call another node: {name}", node, suggested_fix_type="move_to_nodeset")
        if name in {"setattr", "delattr"}:
            self._add("monkey_patch", f"monkey patching is forbidden in module helper: {name}", node, suggested_fix_type="fix_node")
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in MUTATING_METHODS
            and self._is_helper_input_reference(node.func.value)
        ):
            self._add("input_mutation", f"module helper must not mutate inputs via {node.func.attr}", node, suggested_fix_type="fix_node")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        argv_reference = process_argv_reference(node, self._import_aliases)
        if argv_reference:
            self._add("effect_call", f"banned process argument access in module helper: {argv_reference}", node, suggested_fix_type="fix_contract")
        terminal_reference = terminal_stream_reference(node, self._import_aliases)
        if terminal_reference and terminal_stream_is_forbidden(self.effect_scope):
            self._add("effect_call", f"banned terminal stream access in module helper: {terminal_reference}", node, suggested_fix_type="move_to_boundary")
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if not isinstance(node.exc, ast.Call):
            reference = system_exit_reference(node.exc, self._import_aliases)
            if reference and system_exit_is_forbidden(self.effect_scope):
                self._add("effect_call", f"banned process exit in module helper: {reference}", node, suggested_fix_type="move_to_boundary")
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        self._add("global_state", "global mutation is forbidden in module helper", node, suggested_fix_type="move_to_boundary")

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self._add("global_state", "nonlocal mutation is forbidden in module helper", node, suggested_fix_type="move_to_boundary")

    def _check_import(self, module: str, node: ast.AST) -> None:
        if _is_boundary_import(module):
            self._add("boundary_import", f"node must not import boundary APIs: {module}", node, suggested_fix_type="move_to_boundary")
            return
        if _is_node_module(module) or module in self.known_node_modules:
            self._add("node_import", f"node must not import another node module: {module}", node, suggested_fix_type="move_to_nodeset")
            return
        violation_code = import_violation_code(module, effect_scope=self.effect_scope, policy=self.policy)
        if violation_code:
            self._add(violation_code, f"banned import: {module}", node, suggested_fix_type="move_to_boundary")

    def _record_module_class(self, node: ast.ClassDef) -> None:
        if node.name != self.node_class_name and _class_looks_like_node(node):
            self.known_node_class_names.add(node.name)

    def _check_module_assignment(self, node: ast.Assign | ast.AnnAssign) -> None:
        if not _module_assignment_is_allowed(node):
            self._add("module_global_state", "module-level mutable state or side-effect construction is forbidden", node, suggested_fix_type="move_to_boundary")

    def _check_helper_input_assignment(self, target: ast.AST, node: ast.AST) -> None:
        if self._helper_target_mutates_input(target):
            self._add("input_mutation", "module helper must not mutate inputs", node, suggested_fix_type="fix_node")

    def _helper_target_mutates_input(self, target: ast.AST) -> bool:
        return isinstance(target, (ast.Subscript, ast.Attribute)) and self._is_helper_input_reference(target.value)

    def _is_helper_input_reference(self, node: ast.AST) -> bool:
        return _is_input_reference(node, self._current_input_aliases)

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
