from __future__ import annotations

from typing import Any, Mapping, Protocol

from vibeflow.core.constants import (
    EFFECT_SCOPE_GLOBAL_STATE,
    EFFECT_SCOPE_NONE,
    EFFECT_SCOPE_TRUSTED,
    FLOW_KINDS,
    FLOW_KIND_DATA_STORE,
    FLOW_KIND_DECISION,
    FLOW_KIND_DOCUMENT,
    FLOW_KIND_GLOBAL_STATE,
    FLOW_KIND_IO,
    FLOW_KIND_PREDEFINED,
    FLOW_KIND_PREPARATION,
    FLOW_KIND_PROCESS,
    FLOW_KIND_TERMINAL,
)

EFFECT_SCOPE_TERMINAL = "terminal"
EFFECT_SCOPE_PYTHON_IO = "python_io"





class PureNode(Protocol):
    def run_pure(self, inputs: Mapping[str, Any], params: Mapping[str, Any]) -> Mapping[str, Any]:
        ...
