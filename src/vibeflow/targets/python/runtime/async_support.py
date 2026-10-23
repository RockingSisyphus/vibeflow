"""Await actual owned work through cancellation, without a global executor."""
import asyncio
from contextvars import copy_context
from threading import Thread
from vibeflow.coordination.async_support import finish_cleanup

async def owned_thread(callback, signal, *, name="vibeflow-node"):
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    context = copy_context()

    def complete(value, error):
        if error is None:
            future.set_result(value)
        else:
            future.set_exception(error)

    def execute():
        try:
            value = context.run(callback)
        except BaseException as error:
            loop.call_soon_threadsafe(complete, None, error)
        else:
            loop.call_soon_threadsafe(complete, value, None)
    thread = Thread(target=execute, name=name)
    thread.start()
    primary = None
    try:
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError as cancelled:
            signal.request_stop('Node cancelled')
            try:
                await finish_cleanup(future)
            except BaseException as cleanup:
                if not isinstance(cleanup, asyncio.CancelledError) and getattr(cleanup, 'code', '') != 'VF_ABORTED':
                    raise cleanup from cancelled
                cancelled.cleanup_errors = [*getattr(cancelled, 'cleanup_errors', ()),
                                            *getattr(cleanup, 'cleanup_errors', ())]
            raise
    except BaseException as error:
        primary = error
        raise
    finally:
        async def join():
            # A worker's thread-local destructors can outlive its callback.
            # Keep the event loop responsive until the actual thread exits.
            while thread.is_alive():
                await asyncio.sleep(.001)
            thread.join(timeout=0)
        try:
            await finish_cleanup(join())
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.cleanup_errors = [*getattr(primary, 'cleanup_errors', ()), cleanup]
