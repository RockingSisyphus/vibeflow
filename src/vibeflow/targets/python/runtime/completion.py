"""Completion boundaries used by nodes, capabilities and lifecycle hooks."""
import inspect
from concurrent.futures import Future

from .lifecycle import NodeContractError


def immediate(value):
    if inspect.isawaitable(value) or isinstance(value, Future):
        if inspect.iscoroutine(value):
            value.close()
        raise NodeContractError("VF_COMPLETION_MISMATCH", "immediate operation returned pending work")
    return value


async def suspended(value):
    if isinstance(value, Future):
        import asyncio
        return await asyncio.wrap_future(value)
    return await value if inspect.isawaitable(value) else value
