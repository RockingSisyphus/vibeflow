from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager


def is_cancellation(error):
    import asyncio
    return isinstance(error, asyncio.CancelledError) or getattr(error, 'code', '') == 'VF_ABORTED'


def attach_error(primary, error, *, cleanup=True):
    """Keep the original exception object; control cancellation is not a new failure."""
    if primary is error:
        return
    if is_cancellation(error):
        for secondary in getattr(error, 'cleanup_errors', ()):
            attach_error(primary, secondary)
        for secondary in getattr(error, 'execution_errors', ()):
            attach_error(primary, secondary, cleanup=False)
        return
    attribute = 'cleanup_errors' if cleanup else 'execution_errors'
    errors = list(getattr(primary, attribute, ()))
    if not any(item is error for name in ('cleanup_errors', 'execution_errors')
               for item in getattr(primary, name, ())):
        errors.append(error)
        setattr(primary, attribute, errors)


@contextmanager
def preserve_failure(primary):
    """Run a failure observer or cleanup without replacing an existing failure."""
    try:
        yield
    except BaseException as error:
        if primary is None:
            raise
        attach_error(primary, error)


def finish_actions(actions, *, primary=None):
    """Run every synchronous finalizer; a successful body cannot hide cleanup failure."""
    initial = primary
    for action in actions:
        try:
            action()
        except BaseException as error:
            if primary is None:
                primary = error
            else:
                attach_error(primary, error)
    if initial is None and primary is not None:
        raise primary


@dataclass
class PipelineRuntimeError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return f"Pipeline runtime error: {self.detail}"


@dataclass
class BoundaryRuntimeError(PipelineRuntimeError):
    pass


class DelegateCliExit(BaseException):
    """Internal control flow for an authorized business CLI exit."""

    def __init__(self, exit_code: int, *, source: str) -> None:
        super().__init__(exit_code)
        self.exit_code = exit_code
        self.source = source


def merge_execution_error(primary, error, *, cleanup=False):
    """Choose a causal outcome without treating a normal CLI exit as failure."""
    if primary is error or isinstance(error, SystemExit):
        return primary
    if primary is None:
        return error
    if is_cancellation(error):
        for secondary in getattr(error, 'cleanup_errors', ()):
            primary = merge_execution_error(primary, secondary, cleanup=True)
        for secondary in getattr(error, 'execution_errors', ()):
            primary = merge_execution_error(primary, secondary)
        return primary
    if isinstance(primary, DelegateCliExit):
        if isinstance(error, DelegateCliExit):
            failure = PipelineRuntimeError('multiple business exits in concurrent graph branches')
            failure.execution_errors = [primary, error]
            return failure
        error.business_exit = {'exit_code': primary.exit_code, 'source': primary.source}
        return error
    if isinstance(error, DelegateCliExit):
        primary.business_exit = {'exit_code': error.exit_code, 'source': error.source}
        return primary
    attach_error(primary, error, cleanup=cleanup or is_cancellation(primary))
    return primary


def normalize_delegate_cli_system_exit(
    exc: SystemExit, *, source: str, effect_scope: str = "unconstrained"
) -> DelegateCliExit:
    if effect_scope not in {"terminal", "python_io", "unconstrained"}:
        raise PipelineRuntimeError(
            f"node '{source}' with effect_scope '{effect_scope}' cannot control delegate CLI exit"
        )
    value = exc.code
    if value is None:
        value = 0
    if type(value) is not int or not 0 <= value <= 255:
        raise PipelineRuntimeError(f"delegate CLI SystemExit from '{source}' must use an integer code from 0 to 255")
    result = DelegateCliExit(value, source=source)
    errors = getattr(exc, 'cleanup_errors', ())
    if errors:
        failure = result
        for error in errors:
            failure = merge_execution_error(failure, error, cleanup=True)
        raise failure
    return result


__all__ = [
    "BoundaryRuntimeError",
    "DelegateCliExit",
    "PipelineRuntimeError",
    "normalize_delegate_cli_system_exit",
    "attach_error",
    "preserve_failure",
    "is_cancellation",
    "finish_actions",
    "merge_execution_error",
]
