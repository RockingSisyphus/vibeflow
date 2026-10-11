"""Python source Rule policy values and import restrictions."""
from __future__ import annotations

from dataclasses import dataclass, field


BANNED_IMPORT_ROOTS = {
    "_thread",
    "boto3",
    "concurrent",
    "dotenv",
    "httpx",
    "asyncio",
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


BANNED_ATTR_CALLS = {
    "Path.read_bytes",
    "Path.read_text",
    "Path.rename",
    "Path.unlink",
    "Path.write_bytes",
    "Path.write_text",
    "httpx.get",
    "httpx.post",
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
    banned_import_roots: tuple[str, ...] = ()
    allowed_import_modules: tuple[str, ...] = ("urllib.parse", "vibeflow")
    banned_import_modules: tuple[str, ...] = ()
    configured_import_fields: frozenset[str] | None = field(default=None, compare=False, repr=False)
    max_functions: int | None = None
    max_branches: int | None = None
    max_nesting_depth: int | None = None
    max_params: int | None = None
    max_contract_keys: int | None = None
    warn_call_chain_length: int = 4
    max_call_chain_length: int = 4
    warn_dependency_chain_length: int = 4
    max_dependency_chain_length: int = 6
