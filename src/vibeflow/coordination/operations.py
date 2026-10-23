"""Bind Node cancellation and dispatch immediate operations to their host loop."""
import asyncio
from concurrent.futures import Future


def immediate_dispatch():
    """Capture the host loop before ordinary async-graph nodes enter workers."""
    try:
        owner_loop = asyncio.get_running_loop()
    except RuntimeError:
        owner_loop = None

    def dispatch(callback):
        if owner_loop is None:
            return callback()
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is owner_loop:
            return callback()
        outcome = Future()

        def execute():
            try:
                outcome.set_result(callback())
            except BaseException as error:
                outcome.set_exception(error)

        owner_loop.call_soon_threadsafe(execute)
        return outcome.result()

    return dispatch


class Operation:
    def __init__(self, callback, signal=None):
        self.callback, self.signal = callback, signal

    def with_signal(self, signal):
        return type(self)(self.callback, signal)

    def __call__(self, request=None):
        return self.callback(request or {}, self.signal)
