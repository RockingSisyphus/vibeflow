from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from vibeflow.purity.ast_rules import import_aliases, is_banned_import, path_effect_call_name, qualified_call_name
from vibeflow.health.types import HealthFinding
from vibeflow.config.path_utils import is_relative_to
from vibeflow.purity.types import BANNED_ATTR_CALLS, BANNED_CALL_NAMES, BANNED_IMPORT_ROOTS

PLANNED_BEHAVIOR_BLOCKING = "blocking"
PLANNED_BEHAVIOR_TRANSPARENT = "transparent"
PLANNED_BEHAVIOR_PYTHON_STUB = "python_stub"
PLANNED_BEHAVIOR_KINDS = frozenset(
    {
        PLANNED_BEHAVIOR_BLOCKING,
        PLANNED_BEHAVIOR_TRANSPARENT,
        PLANNED_BEHAVIOR_PYTHON_STUB,
    }
)


@dataclass(frozen=True)
class PlannedBehavior:
    kind: str = PLANNED_BEHAVIOR_BLOCKING
    stub_module: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"kind": self.kind}
        if self.stub_module:
            payload["stub_module"] = self.stub_module
        return payload


def blocking_planned_behavior() -> PlannedBehavior:
    return PlannedBehavior()


def parse_planned_behavior(value: Any, *, field: str) -> PlannedBehavior:
    if value in (None, ""):
        return blocking_planned_behavior()
    if isinstance(value, str):
        kind = value.strip()
        if kind in {PLANNED_BEHAVIOR_BLOCKING, PLANNED_BEHAVIOR_TRANSPARENT}:
            return PlannedBehavior(kind=kind)
        raise ValueError(f"{field} must be 'blocking', 'transparent', or a python_stub object")
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a string or object")
    kind = str(value.get("kind", "")).strip()
    if kind != PLANNED_BEHAVIOR_PYTHON_STUB:
        raise ValueError(f"{field}.kind must be 'python_stub'")
    stub_module = str(value.get("stub_module", "")).strip()
    if not stub_module:
        raise ValueError(f"{field}.stub_module is required for python_stub")
    path_error = validate_stub_module_ref(stub_module)
    if path_error:
        raise ValueError(f"{field}.stub_module {path_error}")
    return PlannedBehavior(kind=kind, stub_module=stub_module)


def validate_stub_module_ref(value: str) -> str:
    text = str(value).strip().replace("\\", "/")
    if not text:
        return "must be a non-empty project-relative path"
    if ":" in PurePosixPath(text).parts[0]:
        return "must not use a drive-qualified path"
    path = PurePosixPath(text)
    if path.is_absolute():
        return "must not be an absolute path"
    if any(part in {"", ".", ".."} for part in path.parts):
        return "must not contain '.', '..', or empty path segments"
    if any(part.startswith(".") for part in path.parts):
        return "must not contain hidden path segments"
    if not (
        len(path.parts) >= 2
        and path.parts[0] == "stubs"
        or len(path.parts) >= 3
        and path.parts[0] == "project"
        and path.parts[1] == "stubs"
    ):
        return "must be under stubs/ or project/stubs/"
    if path.suffix != ".py":
        return "must point to a .py file"
    return ""


def planned_behavior_label(behavior: PlannedBehavior) -> str:
    return f"planned {behavior.kind}"


def planned_participates_in_flow(item: object) -> bool:
    return _status(item) != "planned" or _behavior(item).kind in {
        PLANNED_BEHAVIOR_TRANSPARENT,
        PLANNED_BEHAVIOR_PYTHON_STUB,
    }


def effective_planned_behavior(node: object, nodeset: object | None = None) -> PlannedBehavior:
    node_behavior = _behavior(node)
    nodeset_behavior = _behavior(nodeset)
    if _status(node) == "planned" and node_behavior.kind != PLANNED_BEHAVIOR_BLOCKING:
        return node_behavior
    if nodeset is not None and _status(nodeset) == "planned" and nodeset_behavior.kind != PLANNED_BEHAVIOR_BLOCKING:
        return nodeset_behavior
    if _status(node) == "planned":
        return node_behavior
    if nodeset is not None and _status(nodeset) == "planned":
        return nodeset_behavior
    return blocking_planned_behavior()


def project_root_for_config(path: Path) -> Path:
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name == "project":
            return parent.parent.resolve()
    return resolved.parent.resolve()


def resolve_stub_module_path(stub_module: str, project_root: str | Path | None) -> Path:
    root = Path(project_root or Path.cwd()).resolve()
    path_error = validate_stub_module_ref(stub_module)
    if path_error:
        raise ValueError(f"stub_module {path_error}: {stub_module}")
    candidate = (root / stub_module.replace("\\", "/")).resolve()
    parts = PurePosixPath(stub_module.replace("\\", "/")).parts
    allowed_root = (root / "project" / "stubs").resolve() if parts[:2] == ("project", "stubs") else (root / "stubs").resolve()
    if not is_relative_to(candidate, allowed_root):
        raise ValueError(f"stub_module must resolve under {allowed_root}: {stub_module}")
    return candidate


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_stub_callable(path: Path) -> Callable[[Mapping[str, object], Mapping[str, object]], Mapping[str, object]]:
    module_name = f"_vibeflow_planned_stub_{hash_file(path)[:16]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load planned stub module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_stub = getattr(module, "run_stub", None)
    if not callable(run_stub):
        raise AttributeError(f"planned stub module must define run_stub(inputs, params): {path}")
    return run_stub


def validate_python_stub_file(
    behavior: PlannedBehavior,
    *,
    project_root: str | Path | None,
    object_type: str,
    object_id: str,
) -> tuple[HealthFinding, ...]:
    if behavior.kind != PLANNED_BEHAVIOR_PYTHON_STUB:
        return ()
    try:
        path = resolve_stub_module_path(behavior.stub_module, project_root)
    except ValueError as exc:
        return (_stub_finding("GRAPH.PLANNED.STUB_PATH", str(exc), object_type, object_id),)
    if not path.is_file():
        return (_stub_finding("GRAPH.PLANNED.STUB_MISSING", f"planned python_stub file does not exist: {path}", object_type, object_id),)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return (_stub_finding("GRAPH.PLANNED.STUB_READ", f"planned python_stub file cannot be read: {exc}", object_type, object_id),)
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return (_stub_finding("GRAPH.PLANNED.STUB_SYNTAX", f"planned python_stub syntax error: {exc}", object_type, object_id),)
    findings: list[HealthFinding] = []
    findings.extend(_validate_stub_entry(tree, object_type=object_type, object_id=object_id))
    findings.extend(_validate_stub_ast(tree, object_type=object_type, object_id=object_id, path=path))
    return tuple(findings)


def _validate_stub_entry(tree: ast.Module, *, object_type: str, object_id: str) -> list[HealthFinding]:
    matches = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run_stub"]
    if not matches:
        return [_stub_finding("GRAPH.PLANNED.STUB_ENTRY", "planned python_stub must define run_stub(inputs, params)", object_type, object_id)]
    function = matches[0]
    findings: list[HealthFinding] = []
    if isinstance(function, ast.AsyncFunctionDef):
        findings.append(_stub_finding("GRAPH.PLANNED.STUB_ENTRY", "planned python_stub run_stub must not be async", object_type, object_id))
    args = function.args
    positional = [*args.posonlyargs, *args.args]
    names = tuple(arg.arg for arg in positional)
    if names != ("inputs", "params") or args.vararg or args.kwarg or args.kwonlyargs or args.defaults or args.kw_defaults:
        findings.append(_stub_finding("GRAPH.PLANNED.STUB_ENTRY", "planned python_stub entry must have signature run_stub(inputs, params)", object_type, object_id))
    return findings


def _validate_stub_ast(tree: ast.Module, *, object_type: str, object_id: str, path: Path) -> list[HealthFinding]:
    visitor = _StubSafetyVisitor(object_type=object_type, object_id=object_id, path=path)
    visitor.visit(tree)
    return visitor.findings


class _StubSafetyVisitor(ast.NodeVisitor):
    def __init__(self, *, object_type: str, object_id: str, path: Path) -> None:
        self.object_type = object_type
        self.object_id = object_id
        self.path = path
        self.aliases: dict[str, str] = {}
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
            self._check_import(node.module, node)

    def visit_Call(self, node: ast.Call) -> None:
        name = qualified_call_name(node.func, self.aliases)
        root = name.split(".", 1)[0]
        if name in BANNED_CALL_NAMES or root in BANNED_CALL_NAMES or name in BANNED_ATTR_CALLS or _matches_prefix(name, BANNED_ATTR_CALLS):
            self._add("GRAPH.PLANNED.STUB_UNSAFE_CALL", f"planned python_stub uses banned call: {name}", node)
        path_effect = path_effect_call_name(node, self.aliases)
        if path_effect:
            self._add("GRAPH.PLANNED.STUB_UNSAFE_CALL", f"planned python_stub uses file/path side-effect call: {path_effect}", node)
        self.generic_visit(node)

    def _check_import(self, module: str, node: ast.AST) -> None:
        if is_banned_import(
            module,
            allowed_roots=(),
            banned_roots=tuple(sorted(BANNED_IMPORT_ROOTS)),
            allowed_modules=("typing",),
            banned_modules=("urllib.request",),
        ):
            self._add("GRAPH.PLANNED.STUB_UNSAFE_IMPORT", f"planned python_stub imports high-risk module: {module}", node)

    def _check_top_level(self, stmt: ast.stmt) -> None:
        if isinstance(stmt, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            return
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and _immutable_assignment(stmt):
            return
        self._add("GRAPH.PLANNED.STUB_TOP_LEVEL", "planned python_stub module top level may only contain imports, functions, immutable constants, and docstrings", stmt)

    def _add(self, rule_id: str, message: str, node: ast.AST) -> None:
        self.findings.append(
            _stub_finding(
                rule_id,
                message,
                self.object_type,
                self.object_id,
                source_location={"path": str(self.path), "line": getattr(node, "lineno", 1), "column": getattr(node, "col_offset", 0) + 1},
            )
        )


def _immutable_assignment(stmt: ast.Assign | ast.AnnAssign) -> bool:
    value = stmt.value
    if value is None:
        return True
    return _is_immutable(value)


def _is_immutable(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, int, float, bool, type(None)))
    if isinstance(node, ast.Tuple):
        return all(_is_immutable(item) for item in node.elts)
    return False


def _matches_prefix(value: str, patterns: set[str] | frozenset[str]) -> bool:
    return any(value == pattern or value.startswith(f"{pattern}.") for pattern in patterns)


def _stub_finding(
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


def _status(item: object | None) -> str:
    return str(getattr(item, "status", "implemented"))


def _behavior(item: object | None) -> PlannedBehavior:
    behavior = getattr(item, "planned_behavior", None)
    return behavior if isinstance(behavior, PlannedBehavior) else blocking_planned_behavior()


def signature_is_run_stub(func: object) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    params = tuple(signature.parameters.values())
    valid_kinds = {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    return (
        len(params) == 2
        and tuple(param.name for param in params) == ("inputs", "params")
        and all(param.kind in valid_kinds for param in params)
        and all(param.default is inspect.Parameter.empty for param in params)
    )
