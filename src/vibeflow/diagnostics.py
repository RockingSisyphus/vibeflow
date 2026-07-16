from __future__ import annotations

import sys
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator


_DIAGNOSTIC_SINK: ContextVar[Callable[[str], None] | None] = ContextVar(
    "vibeflow_diagnostic_sink",
    default=None,
)


def emit_core_diagnostic(message: str) -> None:
    """Emit a VibeFlow-owned diagnostic without capturing business streams."""

    sink = _DIAGNOSTIC_SINK.get()
    if sink is None:
        print(str(message), file=sys.stderr)
        return
    sink(str(message))


@contextmanager
def core_diagnostic_sink(sink: Callable[[str], None]) -> Iterator[None]:
    token = _DIAGNOSTIC_SINK.set(sink)
    try:
        yield
    finally:
        _DIAGNOSTIC_SINK.reset(token)
