"""Portable protocol values; application message matching is deliberately absent."""
import json
from uuid import uuid4

from vibeflow.core.workflows.coordination import TERMINAL
from vibeflow.core.workflows.interfaces import WORKFLOW_OPERATIONS as OPERATIONS


class CoordinationError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def json_value(value):
    """Copy ordinary JSON without converting objects or non-finite numbers."""
    def check(item):
        if isinstance(item, (int, float)) and not isinstance(item, bool) and abs(item) > 9007199254740991 and (isinstance(item, int) or item.is_integer()):
            raise ValueError("integers outside the cross-language safe range must use strings")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("message object keys must be strings")
            for child in item.values():
                check(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check(child)
    check(value)
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def instance_id():
    return uuid4().hex


def error_record(error, _ancestors=frozenset()):
    """Keep execution and cleanup failures as finite, portable error data."""
    result = {'code':getattr(error,'code',type(error).__name__),'message':str(error)}
    if id(error) in _ancestors:
        return {**result, 'recursive':True}
    ancestors = _ancestors | {id(error)}
    if getattr(error, 'workflow_calls', None):
        result['workflow_calls'] = error.workflow_calls
    if error.__cause__ is not None:
        result['cause'] = error_record(error.__cause__, ancestors)
    if isinstance(error, BaseExceptionGroup):
        result['errors'] = [error_record(item, ancestors) for item in error.exceptions]
    if getattr(error, 'cleanup_errors', None):
        result['cleanup_errors'] = [error_record(item, ancestors) for item in error.cleanup_errors]
    return result


def merge_cleanup_error(primary, cleanup):
    if primary is None:
        return cleanup
    record = primary if isinstance(primary, dict) else {'cause':primary}
    return {**record, 'cleanup_errors':[*record.get('cleanup_errors', ()), cleanup]}
