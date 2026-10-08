from __future__ import annotations

import ast
import inspect
from typing import Any

from vibeflow.targets.python.quality.source_analysis.helpers import _violation
from vibeflow.targets.python.quality.source_analysis.types import PurityViolation, _SourceInfo


def _source_info(node_cls: type[Any]) -> _SourceInfo:
    path = inspect.getsourcefile(node_cls) or ""
    try:
        module = inspect.getmodule(node_cls)
        module_text = inspect.getsource(module) if module is not None else ""
    except (OSError, TypeError):
        module_text = ""
    try:
        lines, start_line = inspect.getsourcelines(node_cls)
        return _SourceInfo(path=path, class_text="".join(lines), class_start_line=start_line, module_text=module_text)
    except (OSError, TypeError):
        return _SourceInfo(path=path, class_text=None, class_start_line=1, module_text=module_text)
