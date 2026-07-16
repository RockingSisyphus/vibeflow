from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


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
    allowed_import_modules: tuple[str, ...] = ("urllib.parse", "vibeflow")
    banned_import_modules: tuple[str, ...] = ("urllib.request",)
    max_functions: int | None = None
    max_branches: int | None = None
    max_nesting_depth: int | None = None
    max_params: int | None = None
    max_contract_keys: int | None = None
    allowed_base_lib_paths: tuple[str, ...] = ()
    allowed_base_lib_modules: tuple[str, ...] = ()
    banned_base_lib_modules: tuple[str, ...] = ()
    warn_call_chain_length: int = 4
    max_call_chain_length: int = 4
    warn_dependency_chain_length: int = 4
    max_dependency_chain_length: int = 6


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
    run_pure_shape: str = ""
    call_chain_length: int = 0
    call_chain_path: tuple[str, ...] = ()
    recursive_call_chains: tuple[tuple[str, ...], ...] = ()

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
            "run_pure_shape": self.run_pure_shape,
            "call_chain_length": self.call_chain_length,
            "call_chain_path": list(self.call_chain_path),
            "recursive_call_chains": [list(path) for path in self.recursive_call_chains],
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


@dataclass(frozen=True)
class _CallChainAnalysis:
    length: int = 0
    path: tuple[str, ...] = ()
    recursive_paths: tuple[tuple[str, ...], ...] = ()



def _default_rule_id(code: str) -> str:
    effect_rules = {
        "effect_call": "NODE.EFFECT.CALL_FORBIDDEN",
        "effect_import": "NODE.EFFECT.IMPORT_FORBIDDEN",
    }
    if code in effect_rules:
        return effect_rules[code]
    flow_rules = {
        "node_info_flow_kind": "NODE.FLOW_KIND.MISSING",
        "node_flow_kind_invalid": "NODE.FLOW_KIND.INVALID",
        "node_decision_missing_route_output": "NODE.DECISION.MISSING_ROUTE_OUTPUT",
        "node_external_invalid": "NODE.EXTERNAL.INVALID",
    }
    if code in flow_rules:
        return flow_rules[code]
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
        "call_chain_too_deep",
        "confusing_key_name",
        "example_contract_gap",
        "example_failed",
        "example_shape",
        "missing_examples",
        "recursive_call_chain",
        "responsibility_mismatch",
        "temporary_key",
        "wide_contract",
    }:
        return f"NODE.MAINTAINABILITY.{code.upper()}"
    return f"NODE.PURITY.{code.upper()}"

