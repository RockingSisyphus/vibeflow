from __future__ import annotations

from typing import Any, Mapping, Protocol

from vibeflow.core.constants import (
    EFFECT_SCOPE_GLOBAL_STATE,
    EFFECT_SCOPE_NONE,
    EFFECT_SCOPE_TRUSTED,
)

EFFECT_SCOPE_TERMINAL = "terminal"
EFFECT_SCOPE_PYTHON_IO = "python_io"


class PureNode(Protocol):
    def run_pure(self, inputs: Mapping[str, Any], params: Mapping[str, Any]) -> Mapping[str, Any]:
        ...
