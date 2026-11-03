"""Cancellation and resource ownership for every ordinary Node invocation."""

from threading import Event, Lock
from types import MappingProxyType
from typing import Mapping

from .errors import PipelineRuntimeError, merge_execution_error


class NodeContractError(PipelineRuntimeError):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code


class NodeCancelled(PipelineRuntimeError):
    code = "VF_ABORTED"


class CancellationSignal:
    """Cooperative signal; cancelling never means the execution has exited."""

    def __init__(self, *, async_loop=None):
        self._event = Event()
        self._lock = Lock()
        self._listeners = set()
        self._callback_errors = []
        self._pending = []
        self.reason = None
        self.error = None
        self._loop = async_loop

    def record_error(self, error, *, cleanup=False):
        """Keep one causal outcome per run, before observers/cleanup can suspend."""
        with self._lock:
            self.error = merge_execution_error(self.error, error, cleanup=cleanup)
            return self.error if self.error is not None else error

    def fail(self, error, *, cleanup=False):
        primary = self.record_error(error, cleanup=cleanup)
        if not isinstance(error, SystemExit):
            self.request_stop('workflow failed or cancelled')
        return primary

    def raise_callback_errors(self):
        with self._lock:
            errors, self._callback_errors = self._callback_errors, []
        if errors:
            raise BaseExceptionGroup('Node cancellation cleanup failed', errors)

    def _own(self, result):
        import asyncio
        import inspect
        if not inspect.isawaitable(result):
            return
        if self._loop is not None and self._loop.is_running():
            async def execute():
                return await result
            self._pending.append(asyncio.run_coroutine_threadsafe(execute(), self._loop))
        else:
            self._pending.append(result)

    @property
    def aborted(self):
        return self._event.is_set()

    def is_set(self):
        return self.aborted

    def wait(self, timeout=None):
        return self._event.wait(timeout)

    def throw_if_aborted(self):
        if self.aborted:
            raise NodeCancelled("VF_ABORTED: node cancellation requested")

    def request_stop(self, reason=None):
        with self._lock:
            if self.aborted:
                return
            self.reason = reason
            if self.error is None:
                self.error = NodeCancelled('VF_ABORTED: workflow stop requested')
            self._event.set()
            listeners = tuple(self._listeners)
            self._listeners.clear()
        for listener in listeners:
            try:
                self._own(listener(reason))
            except Exception as error:
                with self._lock:
                    self._callback_errors.append(error)

    def subscribe(self, listener):
        with self._lock:
            aborted = self.aborted
            if not aborted:
                self._listeners.add(listener)
        if aborted:
            try:
                self._own(listener(self.reason))
            except Exception as error:
                with self._lock:
                    self._callback_errors.append(error)

        def remove():
            with self._lock:
                self._listeners.discard(listener)

        return remove


class NodeRunContext:
    def __init__(self, runtime, frame):
        import asyncio
        loop = asyncio.get_running_loop() if runtime.graph.entry_mode == 'async' else None
        self.signal = CancellationSignal(async_loop=loop)
        self.workflow = runtime.workflow
        from .workflow_session import NodeWorkflow
        self.workflow = NodeWorkflow(runtime.workflow, runtime._workflow_session, self.signal)
        self._runtime, self._frame = runtime, frame
        self._unsubscribe = runtime._signal.subscribe(self.signal.request_stop)

    def close(self):
        try:
            self.signal.request_stop("Node exiting")
            from .completion import immediate
            pending, self.signal._pending = self.signal._pending, []
            for operation in pending:
                try:
                    immediate(operation)
                except BaseException as error:
                    self.signal._callback_errors.append(error)
            self.signal.raise_callback_errors()
        finally:
            self._unsubscribe()

    async def close_async(self):
        self.signal.request_stop("Node exiting")
        try:
            while self.signal._pending:
                pending, self.signal._pending = self.signal._pending, []
                for operation in pending:
                    try:
                        from concurrent.futures import Future
                        import asyncio
                        await asyncio.wrap_future(operation) if isinstance(operation, Future) else await operation
                    except BaseException as error:
                        self.signal._callback_errors.append(error)
            self.signal.raise_callback_errors()
        finally:
            self._unsubscribe()

    def trace(self, kind, details=None):
        self._runtime._record_runtime_event(
            kind, self._frame.id, self._frame.definition_id, details=details
        )
