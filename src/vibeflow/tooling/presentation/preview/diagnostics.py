"""Best-effort ancillary preview failures remain visible without blocking execution."""
from pathlib import Path
from contextlib import contextmanager

def incidental_preview(function, *, error_path=None, **kwargs):
    """An optional display failure must not change a build/run's actual outcome."""
    try:
        return function(**kwargs)
    except Exception as exc:
        from vibeflow.tooling.project.diagnostic_sink import emit_core_diagnostic
        message = f"VibeFlow preview failed: {type(exc).__name__}: {exc}"
        emit_core_diagnostic(message)
        if error_path is not None:
            try:
                Path(error_path).write_text(message + "\n", encoding="utf-8")
            except OSError as write_error:
                emit_core_diagnostic(f"Cannot save preview error: {write_error}")
        return getattr(exc, "record", None)


@contextmanager
def preview_operation(record):
    """Finish an ancillary build record with the operation's actual outcome."""
    try:
        yield
    except BaseException as exc:
        if record is not None:
            incidental_preview(record.update, status="failed", error=str(exc))
        raise
    else:
        if record is not None:
            incidental_preview(record.update, status="succeeded")

