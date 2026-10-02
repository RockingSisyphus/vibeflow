"""Optional ordinary-source effect review, implemented by the selected Rule."""
from __future__ import annotations
import ast
from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.quality.source_analysis.ast_rules import import_aliases, import_roots, path_effect_call_name, qualified_call_name

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
SIDE_EFFECT_CALLS = frozenset(
    {"__import__", "compile", "eval", "exec", "input", "open"}
)
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


def source_effect_findings(
    source: object,
    tree: ast.AST,
) -> list[HealthFinding]:
    findings: list[HealthFinding] = []
    aliases = import_aliases(tree, defaults={"Path": "pathlib.Path"})
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for root in import_roots(node):
                if root in SIDE_EFFECT_IMPORT_ROOTS:
                    findings.append(
                        _effect_finding(
                            source,
                            node,
                            "QUALITY.SIDE_EFFECT.IMPORT",
                            f"imports side-effect capable module {root}",
                        )
                    )
            continue
        if not isinstance(node, ast.Call):
            continue
        call_name = qualified_call_name(node.func, aliases) or "<dynamic>"
        path_effect = path_effect_call_name(node, aliases)
        if (
            call_name in SIDE_EFFECT_CALLS
            or any(
                call_name == banned or call_name.startswith(f"{banned}.")
                for banned in SIDE_EFFECT_ATTR_CALLS
            )
            or path_effect
        ):
            findings.append(
                _effect_finding(
                    source,
                    node,
                    "QUALITY.SIDE_EFFECT.CALL",
                    f"calls side-effect capable API {path_effect or call_name}",
                )
            )
    return findings


def _effect_finding(
    source: object,
    node: ast.AST,
    rule_id: str,
    message: str,
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="warning",
        object_type="file",
        object_id=source.relative_path,
        source_location={
            "path": source.source_path,
            "line": getattr(node, "lineno", 1),
        },
        message=message,
        suggested_fix_type="isolate_side_effect",
    )
