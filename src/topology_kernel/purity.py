from __future__ import annotations

import ast
import inspect
import json
from dataclasses import dataclass, field
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .node import NodeContract, NodeInfo, PureNode


BANNED_IMPORT_ROOTS = {
    "boto3",
    "dotenv",
    "httpx",
    "importlib",
    "asyncio",
    "boundaries",
    "boundary",
    "multiprocessing",
    "nodriver",
    "os",
    "pathlib",
    "playwright",
    "psycopg2",
    "pymongo",
    "pymysql",
    "redis",
    "requests",
    "selenium",
    "shutil",
    "socket",
    "sqlalchemy",
    "sqlite3",
    "subprocess",
    "threading",
    "urllib",
}
BANNED_CALL_NAMES = {"__import__", "compile", "eval", "exec", "input", "open"}
BANNED_ATTR_CALLS = {
    "Path.read_bytes",
    "Path.read_text",
    "Path.rename",
    "Path.unlink",
    "Path.write_bytes",
    "Path.write_text",
    "httpx.get",
    "httpx.post",
    "importlib.import_module",
    "os.getenv",
    "os.system",
    "requests.get",
    "requests.post",
    "socket.socket",
    "sqlite3.connect",
    "sqlalchemy.create_engine",
    "subprocess.call",
    "subprocess.Popen",
    "subprocess.run",
    "time.sleep",
}
RESOURCE_FIELD_NAMES = {
    "boundary",
    "browser",
    "client",
    "connection",
    "context",
    "cursor",
    "driver",
    "engine",
    "session",
}
MUTATING_METHODS = {
    "append",
    "clear",
    "extend",
    "insert",
    "pop",
    "popitem",
    "remove",
    "setdefault",
    "sort",
    "update",
}
IMMUTABLE_CONSTANT_TYPES = (str, int, float, bool, type(None), tuple)


@dataclass(frozen=True)
class PurityPolicy:
    max_source_lines: int = 500
    max_source_bytes: int = 60000
    warn_source_lines: int | None = None
    warn_source_bytes: int | None = None
    allowed_import_roots: tuple[str, ...] = ()
    banned_import_roots: tuple[str, ...] = tuple(sorted(BANNED_IMPORT_ROOTS))
    max_functions: int | None = None
    max_branches: int | None = None
    max_nesting_depth: int | None = None
    max_params: int | None = None
    max_contract_keys: int | None = None
    allowed_base_lib_paths: tuple[str, ...] = ()
    allowed_base_lib_modules: tuple[str, ...] = ()
    banned_base_lib_modules: tuple[str, ...] = ()


@dataclass(frozen=True)
class NodeMetrics:
    source_lines: int = 0
    source_bytes: int = 0
    function_count: int = 0
    branch_count: int = 0
    max_nesting_depth: int = 0
    param_count: int = 0
    requires_count: int = 0
    provides_count: int = 0
    contract_key_count: int = 0
    function_names: tuple[str, ...] = ()
    run_pure_fingerprint: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "source_lines": self.source_lines,
            "source_bytes": self.source_bytes,
            "function_count": self.function_count,
            "branch_count": self.branch_count,
            "max_nesting_depth": self.max_nesting_depth,
            "param_count": self.param_count,
            "requires_count": self.requires_count,
            "provides_count": self.provides_count,
            "contract_key_count": self.contract_key_count,
            "function_names": list(self.function_names),
            "run_pure_fingerprint": self.run_pure_fingerprint,
        }


@dataclass(frozen=True)
class PurityViolation:
    code: str
    message: str
    rule_id: str = ""
    severity: str = "error"
    source_location: Mapping[str, object] = field(default_factory=dict)
    failure_layer: str = "implementation"
    suggested_fix_type: str = "fix_node"
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rule_id:
            object.__setattr__(self, "rule_id", _default_rule_id(self.code))


def validate_node_class(
    node_cls: type[PureNode],
    *,
    policy: PurityPolicy | None = None,
    expected_type: str | None = None,
    known_node_modules: tuple[str, ...] = (),
    known_node_class_names: tuple[str, ...] = (),
    scan_module: bool = False,
) -> list[PurityViolation]:
    policy = policy or PurityPolicy()
    source = _source_info(node_cls)
    violations: list[PurityViolation] = []
    info = getattr(node_cls, "NODE_INFO", None)
    contract = getattr(node_cls, "CONTRACT", None)

    violations.extend(_validate_node_info(info, expected_type=expected_type, source=source))
    violations.extend(_validate_contract(contract, source=source))
    violations.extend(_validate_interface(node_cls, source=source))

    if source.class_text is None:
        violations.append(
            _violation(
                "source_unavailable",
                "node source is unavailable for static purity check",
                source=source,
                suggested_fix_type="fix_node",
            )
        )
        return violations

    violations.extend(_validate_source_size(source.class_text, policy=policy, source=source))
    class_tree = _parse_source(source.class_text, source=source)
    if isinstance(class_tree, PurityViolation):
        violations.append(class_tree)
        return violations
    metrics = collect_node_metrics(node_cls)
    violations.extend(_validate_complexity_metrics(metrics, policy=policy, source=source))
    if isinstance(info, NodeInfo) and isinstance(contract, NodeContract):
        violations.extend(_validate_architecture_smells(info, contract, source=source, metrics=metrics))

    visitor = NodePurityVisitor(
        policy=policy,
        source=source,
        contract=contract if isinstance(contract, NodeContract) else None,
        known_node_modules=known_node_modules,
        known_node_class_names=known_node_class_names,
        line_offset=source.class_start_line - 1,
    )
    visitor.visit(class_tree)
    violations.extend(visitor.violations)
    if isinstance(contract, NodeContract) and not any(violation.severity == "error" for violation in violations):
        violations.extend(_validate_examples(node_cls, contract, source=source))

    if scan_module and source.module_text:
        module_tree = _parse_source(source.module_text, source=source)
        if isinstance(module_tree, PurityViolation):
            violations.append(module_tree)
        else:
            module_visitor = ModulePurityVisitor(
                policy=policy,
                source=source,
                node_class_name=node_cls.__name__,
                known_node_modules=known_node_modules,
                known_node_class_names=known_node_class_names,
            )
            module_visitor.visit(module_tree)
            violations.extend(module_visitor.violations)

    return _dedupe_violations(violations)


def collect_node_metrics(node_cls: type[Any]) -> NodeMetrics:
    source = _source_info(node_cls)
    contract = getattr(node_cls, "CONTRACT", None)
    if source.class_text is None:
        return NodeMetrics()
    tree = _parse_source(source.class_text, source=source)
    if isinstance(tree, PurityViolation):
        return NodeMetrics(source_lines=len(source.class_text.splitlines()), source_bytes=len(source.class_text.encode("utf-8")))
    counter = _ComplexityCounter()
    counter.visit(tree)
    requires = getattr(contract, "requires", ()) if isinstance(contract, NodeContract) else ()
    provides = getattr(contract, "provides", ()) if isinstance(contract, NodeContract) else ()
    params_schema = getattr(contract, "params_schema", {}) if isinstance(contract, NodeContract) else {}
    return NodeMetrics(
        source_lines=len(source.class_text.splitlines()),
        source_bytes=len(source.class_text.encode("utf-8")),
        function_count=counter.function_count,
        branch_count=counter.branch_count,
        max_nesting_depth=counter.max_nesting_depth,
        param_count=len(params_schema) if isinstance(params_schema, Mapping) else 0,
        requires_count=len(requires),
        provides_count=len(provides),
        contract_key_count=len(requires) + len(provides),
        function_names=tuple(counter.function_names),
        run_pure_fingerprint=counter.run_pure_fingerprint,
    )


@dataclass(frozen=True)
class _SourceInfo:
    path: str
    class_text: str | None
    class_start_line: int
    module_text: str

    def location(self, *, line: int | None = None, column: int | None = None) -> dict[str, object]:
        out: dict[str, object] = {}
        if self.path:
            out["path"] = self.path
        if line is not None:
            out["line"] = line
        if column is not None:
            out["column"] = column
        return out


class NodePurityVisitor(ast.NodeVisitor):
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

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(alias.name, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if _is_boundary_import(module) or any(alias.name in {"GlobalBoundary", "BoundaryRegistry"} for alias in node.names):
            self._add("boundary_import", f"node must not import boundary APIs: {module}", node, suggested_fix_type="move_to_boundary")
            return
        self._check_import(module, node)

    def visit_Global(self, node: ast.Global) -> None:
        self._add("global_state", "global mutation is forbidden", node, suggested_fix_type="move_to_boundary")

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self._add("global_state", "nonlocal mutation is forbidden", node, suggested_fix_type="move_to_boundary")

    def visit_Assign(self, node: ast.Assign) -> None:
        self._track_input_alias(node)
        self._track_output_dict(node)
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
        root = name.split(".", 1)[0]
        if name in BANNED_CALL_NAMES or name in BANNED_ATTR_CALLS or root in BANNED_CALL_NAMES:
            self._add("banned_call", f"banned call: {name}", node, suggested_fix_type="move_to_boundary")
        elif _matches_prefix(name, BANNED_ATTR_CALLS):
            self._add("banned_call", f"banned call: {name}", node, suggested_fix_type="move_to_boundary")
        if name in {"setattr", "delattr"}:
            self._add("monkey_patch", f"monkey patching is forbidden: {name}", node, suggested_fix_type="fix_node")
        if name.endswith(".run_pure") or root in self.known_node_class_names:
            self._add("node_direct_call", f"node must not directly call another node: {name}", node, suggested_fix_type="move_to_nodeset")
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id in {"inputs", *self._input_aliases} and node.func.attr in MUTATING_METHODS:
                self._add("input_mutation", f"node must not mutate inputs via {node.func.attr}", node, suggested_fix_type="fix_node")
            if node.func.value.id == "params" and node.func.attr == "get" and node.args:
                key_node = node.args[0]
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    key = key_node.value
                    if self.contract is not None and key not in self.contract.params_schema:
                        self._add("undeclared_param", f"params key is not declared in CONTRACT.params_schema: {key}", node, failure_layer="contract", suggested_fix_type="fix_contract")
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

    def _track_output_dict(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Dict):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    keys, dynamic = _dict_literal_keys(node.value)
                    if not dynamic and keys is not None:
                        self._output_dicts[target.id] = keys
        for target in node.targets:
            if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id in self._output_dicts:
                key = _literal_subscript_key(target)
                if key:
                    self._output_dicts[target.value.id].add(key)
                else:
                    self._add("dynamic_output_key", "output dict assignment key must be a string literal", node, suggested_fix_type="fix_contract")

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


class ModulePurityVisitor(ast.NodeVisitor):
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
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                self.visit(stmt)
            elif isinstance(stmt, ast.ClassDef):
                if stmt.name != self.node_class_name and _class_looks_like_node(stmt):
                    self.known_node_class_names.add(stmt.name)
                continue
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                if not _module_assignment_is_allowed(stmt):
                    self._add("module_global_state", "module-level mutable state or side-effect construction is forbidden", stmt, suggested_fix_type="move_to_boundary")
            elif not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Constant) or not isinstance(stmt.value.value, str):
                self._add("module_side_effect", "node module top level may only contain imports, definitions, immutable constants, and docstrings", stmt, suggested_fix_type="move_to_boundary")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(alias.name, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if _is_boundary_import(module) or any(alias.name in {"GlobalBoundary", "BoundaryRegistry"} for alias in node.names):
            self._add("boundary_import", f"node must not import boundary APIs: {module}", node, suggested_fix_type="move_to_boundary")
            return
        self._check_import(module, node)

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


class _ComplexityCounter(ast.NodeVisitor):
    def __init__(self) -> None:
        self.function_count = 0
        self.branch_count = 0
        self.max_nesting_depth = 0
        self.function_names: list[str] = []
        self.run_pure_fingerprint = ""
        self._nesting = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_count += 1
        self.function_names.append(node.name)
        if node.name == "run_pure":
            self.run_pure_fingerprint = _fingerprint_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_If(self, node: ast.If) -> None:
        self._visit_branch(node)

    def visit_For(self, node: ast.For) -> None:
        self._visit_branch(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_branch(node)

    def visit_While(self, node: ast.While) -> None:
        self._visit_branch(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.branch_count += max(1, len(node.handlers))
        self._with_nesting(lambda: self.generic_visit(node))

    def visit_TryStar(self, node: ast.TryStar) -> None:
        self.visit_Try(node)  # type: ignore[arg-type]

    def visit_Match(self, node: ast.Match) -> None:
        self.branch_count += max(1, len(node.cases))
        self._with_nesting(lambda: self.generic_visit(node))

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.branch_count += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._visit_branch(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.branch_count += 1 + len(node.ifs)
        self.generic_visit(node)

    def _visit_branch(self, node: ast.AST) -> None:
        self.branch_count += 1
        self._with_nesting(lambda: self.generic_visit(node))

    def _with_nesting(self, callback: Any) -> None:
        self._nesting += 1
        self.max_nesting_depth = max(self.max_nesting_depth, self._nesting)
        callback()
        self._nesting -= 1


def _validate_node_info(info: object, *, expected_type: str | None, source: _SourceInfo) -> list[PurityViolation]:
    if not isinstance(info, NodeInfo):
        return [_violation("missing_node_info", "node must define NODE_INFO: NodeInfo", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    violations: list[PurityViolation] = []
    for field_name in ("type_key", "display_name", "category", "description", "version", "purity"):
        if not _non_empty_string(getattr(info, field_name, None)):
            violations.append(_violation(f"node_info_{field_name}", f"NODE_INFO.{field_name} must be a non-empty string", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    if info.purity != "pure":
        violations.append(_violation("non_pure_node", "NODE_INFO.purity must be 'pure'", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    if expected_type and info.type_key != expected_type:
        violations.append(_violation("type_mismatch", f"NODE_INFO.type_key {info.type_key!r} does not match expected type {expected_type!r}", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    return violations


def _validate_contract(contract: object, *, source: _SourceInfo) -> list[PurityViolation]:
    if not isinstance(contract, NodeContract):
        return [_violation("missing_contract", "node must define CONTRACT: NodeContract", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    violations: list[PurityViolation] = []
    requires = _validate_key_tuple(contract.requires, "CONTRACT.requires", source=source, violations=violations)
    provides = _validate_key_tuple(contract.provides, "CONTRACT.provides", source=source, violations=violations)
    if set(requires) & set(provides):
        violations.append(_violation("contract_overlap", "CONTRACT.requires and CONTRACT.provides must not overlap", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    violations.extend(_validate_semantics(contract.input_semantics, requires, "CONTRACT.input_semantics", required=bool(requires), source=source))
    violations.extend(_validate_semantics(contract.output_semantics, provides, "CONTRACT.output_semantics", required=bool(provides), source=source))
    violations.extend(_validate_schema_mapping(contract.params_schema, (), "CONTRACT.params_schema", source=source, require_all=False))
    violations.extend(_validate_schema_mapping(contract.output_schema, provides, "CONTRACT.output_schema", source=source, require_all=bool(provides)))
    violations.extend(_validate_contract_examples_shape(contract.examples, source=source))
    return violations


def _validate_interface(node_cls: type[PureNode], *, source: _SourceInfo) -> list[PurityViolation]:
    violations: list[PurityViolation] = []
    if "run" in node_cls.__dict__:
        violations.append(_violation("context_run_forbidden", "pure node must not define run(context, ...)", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    run_pure = node_cls.__dict__.get("run_pure")
    if run_pure is None:
        violations.append(_violation("missing_run_pure", "node must define run_pure(self, inputs, params)", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    elif inspect.iscoroutinefunction(run_pure):
        violations.append(_violation("async_run_pure", "run_pure must not be async", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    else:
        violations.extend(_validate_signature(run_pure, ("self", "inputs", "params"), "run_pure", source=source))
    init = node_cls.__dict__.get("__init__")
    if init is not None:
        violations.extend(_validate_signature(init, ("self",), "__init__", source=source, allow_defaulted=False))
    for name, value in node_cls.__dict__.items():
        if name.startswith("_") or name in {"run_pure"}:
            continue
        if callable(value):
            violations.append(_violation("public_callable", f"node must not expose public callable method: {name}", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    return violations


def _validate_signature(
    func: object,
    expected_names: tuple[str, ...],
    function_name: str,
    *,
    source: _SourceInfo,
    allow_defaulted: bool = True,
) -> list[PurityViolation]:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError) as exc:
        return [_violation("signature_unavailable", f"{function_name} signature is unavailable: {exc}", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    params = list(signature.parameters.values())
    valid_kinds = {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY}
    if len(params) != len(expected_names) or tuple(param.name for param in params) != expected_names:
        return [_violation("run_pure_signature" if function_name == "run_pure" else "init_signature", f"{function_name} must have signature ({', '.join(expected_names)})", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    for param in params:
        if param.kind not in valid_kinds:
            return [_violation("run_pure_signature" if function_name == "run_pure" else "init_signature", f"{function_name} must not use *args, **kwargs, or keyword-only parameters", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
        if not allow_defaulted and param.default is not inspect.Parameter.empty:
            return [_violation("init_signature", "__init__ must not accept configured parameters", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    return []


def _validate_source_size(source_text: str, *, policy: PurityPolicy, source: _SourceInfo) -> list[PurityViolation]:
    violations: list[PurityViolation] = []
    line_count = len(source_text.splitlines())
    byte_count = len(source_text.encode("utf-8"))
    if line_count > policy.max_source_lines:
        violations.append(_violation("source_too_large", f"node source has {line_count} lines > {policy.max_source_lines}", source=source, suggested_fix_type="split_node", details={"lines": line_count, "limit": policy.max_source_lines}))
    elif policy.warn_source_lines is not None and line_count >= policy.warn_source_lines:
        violations.append(_violation("source_near_limit", f"node source has {line_count} lines >= warning threshold {policy.warn_source_lines}", source=source, severity="warning", suggested_fix_type="split_node", details={"lines": line_count, "limit": policy.warn_source_lines}))
    if byte_count > policy.max_source_bytes:
        violations.append(_violation("source_bytes_too_large", f"node source has {byte_count} bytes > {policy.max_source_bytes}", source=source, suggested_fix_type="split_node", details={"bytes": byte_count, "limit": policy.max_source_bytes}))
    elif policy.warn_source_bytes is not None and byte_count >= policy.warn_source_bytes:
        violations.append(_violation("source_bytes_near_limit", f"node source has {byte_count} bytes >= warning threshold {policy.warn_source_bytes}", source=source, severity="warning", suggested_fix_type="split_node", details={"bytes": byte_count, "limit": policy.warn_source_bytes}))
    return violations


def _validate_complexity_metrics(metrics: NodeMetrics, *, policy: PurityPolicy, source: _SourceInfo) -> list[PurityViolation]:
    checks = (
        ("max_functions", policy.max_functions, metrics.function_count, "function_count", "split_node"),
        ("max_branches", policy.max_branches, metrics.branch_count, "branch_count", "split_node"),
        ("max_nesting_depth", policy.max_nesting_depth, metrics.max_nesting_depth, "max_nesting_depth", "split_node"),
        ("max_params", policy.max_params, metrics.param_count, "param_count", "fix_contract"),
        ("max_contract_keys", policy.max_contract_keys, metrics.contract_key_count, "contract_key_count", "fix_contract"),
    )
    violations: list[PurityViolation] = []
    for code, limit, actual, detail_key, fix_type in checks:
        if limit is not None and actual > limit:
            violations.append(
                _violation(
                    f"complexity_{code}",
                    f"node {detail_key} is {actual} > policy limit {limit}",
                    source=source,
                    suggested_fix_type=fix_type,
                    details={detail_key: actual, "limit": limit, "metrics": metrics.to_dict()},
                )
            )
    return violations


def _validate_architecture_smells(
    info: NodeInfo,
    contract: NodeContract,
    *,
    source: _SourceInfo,
    metrics: NodeMetrics,
) -> list[PurityViolation]:
    warnings: list[PurityViolation] = []
    metadata_tokens = _tokens(" ".join((info.type_key, info.display_name, info.category, info.description)))
    contract_tokens = _tokens(" ".join((*contract.requires, *contract.provides)))
    semantic_tokens = _tokens(" ".join(part for values in (*contract.input_semantics.values(), *contract.output_semantics.values()) for part in values))
    if contract_tokens and not (contract_tokens & (metadata_tokens | semantic_tokens)):
        warnings.append(
            _violation(
                "responsibility_mismatch",
                "node metadata/semantics do not visibly describe contract keys",
                source=source,
                severity="warning",
                failure_layer="contract",
                suggested_fix_type="fix_contract",
                details={"metadata_tokens": sorted(metadata_tokens), "contract_tokens": sorted(contract_tokens)},
            )
        )
    for key in (*contract.requires, *contract.provides):
        if _looks_temporary_key(key):
            warnings.append(
                _violation(
                    "temporary_key",
                    f"contract key looks temporary or unstable: {key}",
                    source=source,
                    severity="warning",
                    failure_layer="contract",
                    suggested_fix_type="fix_contract",
                    details={"key": key},
                )
            )
        if not _looks_structured_key(key):
            warnings.append(
                _violation(
                    "confusing_key_name",
                    f"contract key should use lowercase dot/underscore segments: {key}",
                    source=source,
                    severity="warning",
                    failure_layer="contract",
                    suggested_fix_type="fix_contract",
                    details={"key": key},
                )
            )
    if metrics.contract_key_count > 10:
        warnings.append(
            _violation(
                "wide_contract",
                f"node contract is wide with {metrics.contract_key_count} keys",
                source=source,
                severity="warning",
                failure_layer="contract",
                suggested_fix_type="split_node",
                details={"metrics": metrics.to_dict()},
            )
        )
    return warnings


def _validate_contract_examples_shape(value: object, *, source: _SourceInfo) -> list[PurityViolation]:
    if not isinstance(value, tuple):
        return [_violation("example_shape", "CONTRACT.examples must be a tuple of example mappings", source=source, severity="warning", failure_layer="contract", suggested_fix_type="fix_contract")]
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            return [_violation("example_shape", f"CONTRACT.examples[{index}] must be a mapping", source=source, severity="warning", failure_layer="contract", suggested_fix_type="fix_contract")]
        for field_name in ("inputs", "params", "outputs"):
            if field_name not in item or not isinstance(item[field_name], Mapping):
                return [_violation("example_shape", f"CONTRACT.examples[{index}].{field_name} must be a mapping", source=source, severity="warning", failure_layer="contract", suggested_fix_type="fix_contract")]
    return []


def _validate_examples(node_cls: type[PureNode], contract: NodeContract, *, source: _SourceInfo) -> list[PurityViolation]:
    if not contract.examples:
        return [
            _violation(
                "missing_examples",
                "node should provide at least one minimal example in CONTRACT.examples",
                source=source,
                severity="warning",
                failure_layer="contract",
                suggested_fix_type="fix_contract",
            )
        ]
    findings: list[PurityViolation] = []
    covers_contract = False
    for index, example in enumerate(contract.examples):
        if not isinstance(example, Mapping):
            continue
        inputs = dict(example.get("inputs", {}))
        params = dict(example.get("params", {}))
        expected_outputs = dict(example.get("outputs", {}))
        if set(contract.requires) <= set(inputs) and set(expected_outputs) == set(contract.provides):
            covers_contract = True
        else:
            findings.append(
                _violation(
                    "example_contract_gap",
                    f"CONTRACT.examples[{index}] does not cover requires/provides",
                    source=source,
                    severity="warning",
                    failure_layer="contract",
                    suggested_fix_type="fix_contract",
                    details={"example_index": index},
                )
            )
            continue
        try:
            actual_outputs = node_cls().run_pure(deepcopy(inputs), deepcopy(params))
        except Exception as exc:  # noqa: BLE001 - health report must contain checker-visible failure.
            findings.append(
                _violation(
                    "example_failed",
                    f"CONTRACT.examples[{index}] raised {type(exc).__name__}: {exc}",
                    source=source,
                    failure_layer="contract",
                    suggested_fix_type="fix_node",
                    details={"example_index": index},
                )
            )
            continue
        if actual_outputs != expected_outputs:
            findings.append(
                _violation(
                    "example_failed",
                    f"CONTRACT.examples[{index}] expected outputs do not match run_pure outputs",
                    source=source,
                    failure_layer="contract",
                    suggested_fix_type="fix_node",
                    details={"example_index": index, "expected": expected_outputs, "actual": actual_outputs},
                )
            )
        try:
            json.dumps(actual_outputs, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            findings.append(
                _violation(
                    "example_failed",
                    f"CONTRACT.examples[{index}] output is not JSON snapshot serializable: {exc}",
                    source=source,
                    failure_layer="contract",
                    suggested_fix_type="fix_contract",
                    details={"example_index": index},
                )
            )
    if not covers_contract:
        findings.append(
            _violation(
                "example_contract_gap",
                "node examples exist but none covers all requires/provides",
                source=source,
                severity="warning",
                failure_layer="contract",
                suggested_fix_type="fix_contract",
            )
        )
    return findings


def _source_info(node_cls: type[Any]) -> _SourceInfo:
    path = inspect.getsourcefile(node_cls) or ""
    module_text = ""
    if path and Path(path).exists():
        module_text = Path(path).read_text(encoding="utf-8")
    try:
        lines, start_line = inspect.getsourcelines(node_cls)
        return _SourceInfo(path=path, class_text="".join(lines), class_start_line=start_line, module_text=module_text)
    except (OSError, TypeError):
        return _SourceInfo(path=path, class_text=None, class_start_line=1, module_text=module_text)


def _parse_source(source_text: str, *, source: _SourceInfo) -> ast.Module | PurityViolation:
    try:
        return ast.parse(source_text)
    except SyntaxError as exc:
        return _violation("syntax_error", str(exc), source=source, line=exc.lineno, column=exc.offset, suggested_fix_type="fix_node")


def _validate_key_tuple(value: object, field_name: str, *, source: _SourceInfo, violations: list[PurityViolation]) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not _non_empty_string(item) for item in value):
        violations.append(_violation("contract_key_list", f"{field_name} must be a tuple/list of non-empty strings", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
        return ()
    if len(set(value)) != len(value):
        violations.append(_violation("contract_duplicate_key", f"{field_name} must not contain duplicate keys", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    return value


def _validate_semantics(value: object, keys: tuple[str, ...], field_name: str, *, required: bool, source: _SourceInfo) -> list[PurityViolation]:
    if not isinstance(value, Mapping):
        return [_violation("contract_semantics", f"{field_name} must be a mapping", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    missing = set(keys) - set(value)
    if required and missing:
        return [_violation("contract_semantics_missing", f"{field_name} must cover keys: {sorted(missing)}", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    for key, item in value.items():
        if key not in keys:
            return [_violation("contract_semantics_extra", f"{field_name} contains undeclared key: {key}", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
        if not isinstance(item, tuple) or any(not _non_empty_string(part) for part in item):
            return [_violation("contract_semantics", f"{field_name}[{key!r}] must be a tuple of non-empty strings", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    return []


def _validate_schema_mapping(value: object, keys: tuple[str, ...], field_name: str, *, source: _SourceInfo, require_all: bool) -> list[PurityViolation]:
    if not isinstance(value, Mapping):
        return [_violation("contract_schema", f"{field_name} must be a mapping", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    missing = set(keys) - set(value)
    if require_all and missing:
        return [_violation("contract_schema_missing", f"{field_name} must cover keys: {sorted(missing)}", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    for key, schema in value.items():
        if keys and key not in keys:
            return [_violation("contract_schema_extra", f"{field_name} contains undeclared key: {key}", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
        if not isinstance(schema, Mapping) or ("type" not in schema and schema.get("snapshot") != "opaque"):
            return [_violation("contract_schema_shape", f"{field_name}[{key!r}] must be an object with 'type' or snapshot='opaque'", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    return []


def _dict_literal_keys(node: ast.Dict) -> tuple[set[str] | None, bool]:
    keys: set[str] = set()
    for key in node.keys:
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str) or not key.value:
            return None, True
        keys.add(key.value)
    return keys, False


def _literal_subscript_key(node: ast.Subscript) -> str:
    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return ""


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return ""


def _matches_prefix(name: str, patterns: set[str]) -> bool:
    return any(name.startswith(f"{pattern}.") for pattern in patterns)


def _is_inputs_subscript(node: ast.AST) -> bool:
    return isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "inputs"


def _assigns_resource_field(node: ast.AST) -> bool:
    targets: list[ast.AST] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    for target in targets:
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
            if target.attr.lower() in RESOURCE_FIELD_NAMES:
                return True
    return False


def _module_assignment_is_allowed(node: ast.Assign | ast.AnnAssign) -> bool:
    value = node.value
    if value is None:
        return True
    return _is_immutable_constant(value)


def _is_immutable_constant(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, IMMUTABLE_CONSTANT_TYPES)
    if isinstance(node, ast.Tuple):
        return all(_is_immutable_constant(item) for item in node.elts)
    return False


def _class_looks_like_node(node: ast.ClassDef) -> bool:
    names = set()
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
    return {"NODE_INFO", "CONTRACT"} <= names


def _is_node_module(module: str) -> bool:
    parts = tuple(part for part in module.split(".") if part)
    return "nodes" in parts


def _is_boundary_import(module: str) -> bool:
    parts = tuple(part for part in module.split(".") if part)
    return "boundary" in parts or "boundaries" in parts


def _is_base_lib_module(module: str) -> bool:
    parts = tuple(part for part in module.split(".") if part)
    return "base_lib" in parts


def _module_matches(module: str, patterns: tuple[str, ...]) -> bool:
    return any(module == pattern or module.startswith(f"{pattern}.") for pattern in patterns)


def _fingerprint_function(node: ast.FunctionDef) -> str:
    node = _FingerprintNormalizer().visit(deepcopy(node))  # type: ignore[assignment]
    ast.fix_missing_locations(node)
    normalized = ast.dump(node, annotate_fields=False, include_attributes=False)
    for name in ("run_pure", "inputs", "params", "self"):
        normalized = normalized.replace(name, "_")
    return normalized


class _FingerprintNormalizer(ast.NodeTransformer):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value="<str>"), node)
        if isinstance(node.value, (int, float, bool)):
            return ast.copy_location(ast.Constant(value=0), node)
        return node


def _tokens(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    stop = {"a", "an", "and", "in", "node", "out", "output", "input", "the", "to", "value"}
    return {part for part in normalized.split() if len(part) >= 3 and part not in stop}


def _looks_temporary_key(key: str) -> bool:
    parts = _tokens(key)
    return bool(parts & {"debug", "scratch", "temp", "temporary", "tmp", "intermediate"})


def _looks_structured_key(key: str) -> bool:
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._")
    return bool(key) and key == key.lower() and all(char in allowed for char in key) and ".." not in key


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _violation(
    code: str,
    message: str,
    *,
    source: _SourceInfo,
    line: int | None = None,
    column: int | None = None,
    severity: str = "error",
    failure_layer: str = "implementation",
    suggested_fix_type: str = "fix_node",
    details: Mapping[str, object] | None = None,
) -> PurityViolation:
    return PurityViolation(
        code=code,
        rule_id=_default_rule_id(code),
        severity=severity,
        source_location=source.location(line=line, column=column),
        failure_layer=failure_layer,
        message=message,
        suggested_fix_type=suggested_fix_type,
        details=details or {},
    )


def _default_rule_id(code: str) -> str:
    if code.startswith("node_") or code in {"type_mismatch"}:
        return f"NODE.METADATA.{code.upper()}"
    if code.startswith("contract") or code in {
        "async_run_pure",
        "context_run_forbidden",
        "init_signature",
        "missing_contract",
        "missing_node_info",
        "missing_run_pure",
        "public_callable",
        "run_pure_signature",
        "signature_unavailable",
    }:
        return f"NODE.CONTRACT.{code.upper()}"
    if code in {"node_direct_call", "node_import", "node_internal_read"}:
        return f"NODE.COUPLING.{code.upper()}"
    if code.startswith("base_lib_"):
        return f"NODE.BASE_LIB.{code.upper()}"
    if code.startswith("complexity_") or code in {
        "confusing_key_name",
        "example_contract_gap",
        "example_failed",
        "example_shape",
        "missing_examples",
        "responsibility_mismatch",
        "temporary_key",
        "wide_contract",
    }:
        return f"NODE.MAINTAINABILITY.{code.upper()}"
    return f"NODE.PURITY.{code.upper()}"


def _dedupe_violations(violations: list[PurityViolation]) -> list[PurityViolation]:
    seen: set[tuple[str, str, tuple[tuple[str, object], ...]]] = set()
    out: list[PurityViolation] = []
    for violation in violations:
        key = (violation.rule_id, violation.message, tuple(sorted(violation.source_location.items())))
        if key in seen:
            continue
        seen.add(key)
        out.append(violation)
    return out
