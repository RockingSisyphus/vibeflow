"""Immutable source loader facts, independent of review policy."""
import ast
from dataclasses import dataclass, field

@dataclass(frozen=True)
class PythonSourceFact:
    source_id: str
    path: str
    source: str
    module_name: str = ""
    import_time_dependencies: tuple[str, ...] = ()
    runtime_dependencies: tuple[str, ...] = ()
    load_error: str = ""
    _tree: ast.Module | None = field(default=None, compare=False, repr=False)
    parse_error: str = ""
    root_path: str = ""
    parse_line: int = 1
    parse_column: int = 1

__all__ = ["PythonSourceFact"]
