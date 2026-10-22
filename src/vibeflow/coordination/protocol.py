"""Portable protocol values; application message matching is deliberately absent."""
import json
from uuid import uuid4

OPERATIONS = frozenset({"call", "wait", "send", "receive", "kill"})
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


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
