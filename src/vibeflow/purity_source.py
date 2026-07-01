from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

from .purity_helpers import _violation
from .purity_types import PurityViolation, _SourceInfo


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

