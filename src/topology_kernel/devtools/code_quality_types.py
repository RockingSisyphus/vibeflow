from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from typing import Mapping, Sequence


DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "integration_sandbox",
        "node_modules",
        "references",
        "venv",
    }
)

SIDE_EFFECT_IMPORT_ROOTS = frozenset(
    {
        "boto3",
        "dotenv",
        "httpx",
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
    }
)

SIDE_EFFECT_CALLS = frozenset({"__import__", "compile", "eval", "exec", "input", "open"})
SIDE_EFFECT_ATTR_CALLS = frozenset(
    {
        "httpx.get",
        "httpx.post",
        "importlib.import_module",
        "os.getenv",
        "os.system",
        "pathlib.Path.read_text",
        "pathlib.Path.write_text",
        "requests.get",
        "requests.post",
        "shutil.copy",
        "shutil.copytree",
        "shutil.move",
        "socket.socket",
        "sqlite3.connect",
        "sqlalchemy.create_engine",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.run",
    }
)

BRANCH_NODES = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.BoolOp,
    ast.Match,
)


@dataclass(frozen=True)
class QualityThresholds:
    max_file_lines: int = 500
    warn_file_lines: int = 450
    max_file_bytes: int = 60000
    max_functions_per_file: int = 40
    max_classes_per_file: int = 20
    max_public_api_per_file: int = 30
    max_function_lines: int = 80
    max_function_branches: int = 12
    max_function_nesting: int = 4
    warn_dependency_chain: int = 6
    max_dependency_chain: int = 10

    def to_dict(self) -> dict[str, int]:
        return {
            "max_file_lines": self.max_file_lines,
            "warn_file_lines": self.warn_file_lines,
            "max_file_bytes": self.max_file_bytes,
            "max_functions_per_file": self.max_functions_per_file,
            "max_classes_per_file": self.max_classes_per_file,
            "max_public_api_per_file": self.max_public_api_per_file,
            "max_function_lines": self.max_function_lines,
            "max_function_branches": self.max_function_branches,
            "max_function_nesting": self.max_function_nesting,
            "warn_dependency_chain": self.warn_dependency_chain,
            "max_dependency_chain": self.max_dependency_chain,
        }


@dataclass(frozen=True)
class QualityFinding:
    rule_id: str
    severity: str
    object_type: str
    object_id: str
    message: str
    source_location: Mapping[str, object] = field(default_factory=dict)
    suggested_fix_type: str = "refactor"
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "source_location": dict(self.source_location),
            "message": self.message,
            "suggested_fix_type": self.suggested_fix_type,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class FunctionQuality:
    qualname: str
    line_start: int
    line_end: int
    lines: int
    branches: int
    max_nesting_depth: int
    ast_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        return {
            "qualname": self.qualname,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "lines": self.lines,
            "branches": self.branches,
            "max_nesting_depth": self.max_nesting_depth,
            "ast_fingerprint": self.ast_fingerprint,
        }


@dataclass(frozen=True)
class FileQuality:
    path: str
    module: str
    lines: int
    bytes: int
    function_count: int
    class_count: int
    public_api_count: int
    branch_count: int
    max_nesting_depth: int
    imports: tuple[str, ...]
    functions: tuple[FunctionQuality, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "module": self.module,
            "lines": self.lines,
            "bytes": self.bytes,
            "function_count": self.function_count,
            "class_count": self.class_count,
            "public_api_count": self.public_api_count,
            "branch_count": self.branch_count,
            "max_nesting_depth": self.max_nesting_depth,
            "imports": list(self.imports),
            "functions": [function.to_dict() for function in self.functions],
        }


@dataclass(frozen=True)
class QualityReport:
    status: str
    root: str
    thresholds: QualityThresholds
    files: tuple[FileQuality, ...]
    dependency_graph: Mapping[str, Sequence[str]]
    longest_dependency_chain: tuple[str, ...]
    findings: tuple[QualityFinding, ...]

    def to_dict(self) -> dict[str, object]:
        errors = [finding.to_dict() for finding in self.findings if finding.severity == "error"]
        warnings = [finding.to_dict() for finding in self.findings if finding.severity == "warning"]
        return {
            "status": self.status,
            "root": self.root,
            "summary": {
                "files": len(self.files),
                "errors": len(errors),
                "warnings": len(warnings),
                "longest_dependency_chain_length": len(self.longest_dependency_chain),
            },
            "scope_summary": _scope_summary(self.files, self.findings),
            "thresholds": self.thresholds.to_dict(),
            "files": [file.to_dict() for file in self.files],
            "dependency_graph": {key: list(value) for key, value in sorted(self.dependency_graph.items())},
            "longest_dependency_chain": list(self.longest_dependency_chain),
            "errors": errors,
            "warnings": warnings,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=False)


def _scope_summary(files: tuple[FileQuality, ...], findings: tuple[QualityFinding, ...]) -> dict[str, dict[str, int]]:
    summary = {
        "src": {"files": 0, "errors": 0, "warnings": 0},
        "tests": {"files": 0, "errors": 0, "warnings": 0},
        "devtools": {"files": 0, "errors": 0, "warnings": 0},
        "other": {"files": 0, "errors": 0, "warnings": 0},
    }
    for file in files:
        summary[_scope_for_text(file.path)]["files"] += 1
    for finding in findings:
        scope = _scope_for_finding(finding)
        if finding.severity == "error":
            summary[scope]["errors"] += 1
        elif finding.severity == "warning":
            summary[scope]["warnings"] += 1
    return summary


def _scope_for_finding(finding: QualityFinding) -> str:
    path = str(finding.source_location.get("path", ""))
    if path:
        return _scope_for_text(path)
    return _scope_for_text(finding.object_id)


def _scope_for_text(value: str) -> str:
    normalized = value.replace("\\", "/")
    if "src/topology_kernel/devtools/" in normalized:
        return "devtools"
    if normalized.startswith("tests/") or "/tests/" in normalized:
        return "tests"
    if normalized.startswith("src/") or "/src/" in normalized:
        return "src"
    return "other"
