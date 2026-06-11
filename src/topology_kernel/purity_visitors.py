from __future__ import annotations

import ast

from .ast_rules import import_aliases_from_node, import_modules, module_statement_kind, name_targets, path_effect_call_name
from .node import NodeContract
from .purity_helpers import (
    _assigns_resource_field,
    _call_name,
    _class_looks_like_node,
    _dict_literal_keys,
    _is_base_lib_module,
    _is_boundary_import,
    _is_inputs_subscript,
    _is_node_module,
    _literal_subscript_key,
    _matches_prefix,
    _module_assignment_is_allowed,
    _module_matches,
    _root_name,
    _violation,
)
from .purity_types import (
    BANNED_ATTR_CALLS,
    BANNED_CALL_NAMES,
    BANNED_IMPORT_ROOTS,
    MUTATING_METHODS,
    PurityPolicy,
    PurityViolation,
    _SourceInfo,
)


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
        self._check_import(module, node)

    def _record_import_aliases(self, node: ast.Import | ast.ImportFrom) -> None:
        aliases = getattr(self, "_import_aliases", None)
        if isinstance(aliases, dict):
            aliases.update(import_aliases_from_node(node))


class NodePurityVisitor(_PurityImportVisitor):
    def __init__(
        self,
        *,
        policy: PurityPolicy,
        source: _SourceInfo,
        contract: NodeContract | None,
        known_node_modules: tuple[str, ...],
        known_node_class_names: tuple[str, ...],
        line_offset: int,
    ) -> None:
        self.policy = policy
        self.source = source
        self.contract = contract
        self.known_node_modules = set(known_node_modules)
        self.known_node_class_names = set(known_node_class_names)
        self.line_offset = line_offset
        self.violations: list[PurityViolation] = []
        self._input_aliases: set[str] = set()
        self._output_dicts: dict[str, set[str]] = {}
        self._current_function = ""
        self._import_aliases: dict[str, str] = {"Path": "pathlib.Path"}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
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
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_assignment_target(node.target, node)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if _is_inputs_subscript(target):
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
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if self._current_function != "run_pure" or self.contract is None:
            self.generic_visit(node)
            return
        keys, dynamic = self._return_keys(node.value)
        if dynamic:
            self._add("dynamic_output_key", "run_pure output keys must be string literals declared in CONTRACT.provides", node, suggested_fix_type="fix_contract")
        elif keys is not None:
            provides = set(self.contract.provides)
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
            if key and self.contract is not None and key not in self.contract.params_schema:
                self._add("undeclared_param", f"params key is not declared in CONTRACT.params_schema: {key}", node, failure_layer="contract", suggested_fix_type="fix_contract")
        self.generic_visit(node)

    def _check_import(self, module: str, node: ast.AST) -> None:
        root = module.split(".", 1)[0]
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
        banned = set(self.policy.banned_import_roots or tuple(sorted(BANNED_IMPORT_ROOTS)))
        allowed = set(self.policy.allowed_import_roots)
        if root in banned and root not in allowed:
            self._add("banned_import", f"banned import: {module}", node, suggested_fix_type="move_to_boundary")

    def _track_input_alias(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Subscript) and isinstance(node.value.value, ast.Name) and node.value.value.id == "inputs":
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._input_aliases.add(target.id)

    def _track_output_literal(self, node: ast.Assign) -> None:
        if not isinstance(node.value, ast.Dict):
            return
        keys, dynamic = _dict_literal_keys(node.value)
        if dynamic or keys is None:
            return
        for target in name_targets(node.targets):
            self._output_dicts[target.id] = keys

    def _track_output_key_assignment(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id in self._output_dicts:
                self._record_output_key(target, node)

    def _record_output_key(self, target: ast.Subscript, node: ast.Assign) -> None:
        key = _literal_subscript_key(target)
        if key and isinstance(target.value, ast.Name):
            self._output_dicts[target.value.id].add(key)
        else:
            self._add("dynamic_output_key", "output dict assignment key must be a string literal", node, suggested_fix_type="fix_contract")

    def _check_banned_call(self, name: str, node: ast.Call) -> None:
        root = name.split(".", 1)[0]
        banned = False
        if name in BANNED_CALL_NAMES or name in BANNED_ATTR_CALLS or root in BANNED_CALL_NAMES:
            banned = True
            self._add("banned_call", f"banned call: {name}", node, suggested_fix_type="move_to_boundary")
        elif _matches_prefix(name, BANNED_ATTR_CALLS):
            banned = True
            self._add("banned_call", f"banned call: {name}", node, suggested_fix_type="move_to_boundary")
        path_effect = path_effect_call_name(node, self._import_aliases)
        if path_effect and not banned:
            self._add("banned_call", f"banned call: {path_effect}", node, suggested_fix_type="move_to_boundary")

    def _check_monkey_patch_call(self, name: str, node: ast.Call) -> None:
        if name in {"setattr", "delattr"}:
            self._add("monkey_patch", f"monkey patching is forbidden: {name}", node, suggested_fix_type="fix_node")

    def _check_node_coupling_call(self, name: str, node: ast.Call) -> None:
        root = name.split(".", 1)[0]
        if name.endswith(".run_pure") or root in self.known_node_class_names:
            self._add("node_direct_call", f"node must not directly call another node: {name}", node, suggested_fix_type="move_to_nodeset")

    def _check_input_mutation_call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name):
            return
        if node.func.value.id in {"inputs", *self._input_aliases} and node.func.attr in MUTATING_METHODS:
            self._add("input_mutation", f"node must not mutate inputs via {node.func.attr}", node, suggested_fix_type="fix_node")

    def _check_params_get_call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name):
            return
        if node.func.value.id == "params" and node.func.attr == "get" and node.args:
            self._check_params_key_node(node.args[0], node)

    def _check_params_key_node(self, key_node: ast.AST, node: ast.Call) -> None:
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            key = key_node.value
            if self.contract is not None and key not in self.contract.params_schema:
                self._add("undeclared_param", f"params key is not declared in CONTRACT.params_schema: {key}", node, failure_layer="contract", suggested_fix_type="fix_contract")

    def _check_assignment_target(self, target: ast.AST, node: ast.AST) -> None:
        if _is_inputs_subscript(target):
            self._add("input_mutation", "node must not mutate inputs", node, suggested_fix_type="fix_node")
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id != "self":
            self._add("monkey_patch", "assigning to external object attributes is forbidden", node, suggested_fix_type="fix_node")

    def _return_keys(self, value: ast.AST | None) -> tuple[set[str] | None, bool]:
        if isinstance(value, ast.Dict):
            return _dict_literal_keys(value)
        if isinstance(value, ast.Name) and value.id in self._output_dicts:
            return set(self._output_dicts[value.id]), False
        return None, True

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
    ) -> None:
        self.policy = policy
        self.source = source
        self.node_class_name = node_class_name
        self.known_node_modules = set(known_node_modules)
        self.known_node_class_names = set(known_node_class_names)
        self.violations: list[PurityViolation] = []

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            self._visit_module_statement(stmt)

    def _visit_module_statement(self, stmt: ast.stmt) -> None:
        kind = module_statement_kind(stmt)
        if kind == "import":
            self.visit(stmt)
        elif isinstance(stmt, ast.ClassDef):
            self._record_module_class(stmt)
        elif kind == "assignment":
            self._check_module_assignment(stmt)
        elif kind not in {"definition", "docstring"}:
            self._add("module_side_effect", "node module top level may only contain imports, definitions, immutable constants, and docstrings", stmt, suggested_fix_type="move_to_boundary")

    def _check_import(self, module: str, node: ast.AST) -> None:
        root = module.split(".", 1)[0]
        if _is_boundary_import(module):
            self._add("boundary_import", f"node must not import boundary APIs: {module}", node, suggested_fix_type="move_to_boundary")
            return
        if _is_node_module(module) or module in self.known_node_modules:
            self._add("node_import", f"node must not import another node module: {module}", node, suggested_fix_type="move_to_nodeset")
            return
        banned = set(self.policy.banned_import_roots or tuple(sorted(BANNED_IMPORT_ROOTS)))
        allowed = set(self.policy.allowed_import_roots)
        if root in banned and root not in allowed:
            self._add("banned_import", f"banned import: {module}", node, suggested_fix_type="move_to_boundary")

    def _record_module_class(self, node: ast.ClassDef) -> None:
        if node.name != self.node_class_name and _class_looks_like_node(node):
            self.known_node_class_names.add(node.name)

    def _check_module_assignment(self, node: ast.Assign | ast.AnnAssign) -> None:
        if not _module_assignment_is_allowed(node):
            self._add("module_global_state", "module-level mutable state or side-effect construction is forbidden", node, suggested_fix_type="move_to_boundary")

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


