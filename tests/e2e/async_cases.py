"""Top-level test adapter; production SDK never creates an event loop."""
import asyncio
from functools import wraps

def async_case(function):
    @wraps(function)
    def execute(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))
    return execute
