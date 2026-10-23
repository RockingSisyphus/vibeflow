"""Await owned Python cleanup through cancellation without Target dependencies."""
import asyncio


def cancel_once(task):
    """Request owned-task cancellation without interrupting its async finally again."""
    if not task.cancelling():
        task.cancel()


async def finish_cleanup(awaitable):
    task = asyncio.ensure_future(awaitable)
    cancelled = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            cancelled = cancelled or error
        except BaseException:
            break
    try:
        result = task.result()
    except BaseException as error:
        if cancelled is not None and not isinstance(error, asyncio.CancelledError):
            cancelled.cleanup_errors = [*getattr(cancelled, 'cleanup_errors', ()), error]
            raise cancelled
        raise
    if cancelled is not None:
        raise cancelled
    return result
