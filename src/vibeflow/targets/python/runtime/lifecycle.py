"""Cancellation and resource ownership for every ordinary Node invocation."""

from threading import Event, Lock
from types import MappingProxyType
from typing import Mapping

from .errors import PipelineRuntimeError


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
        self._loop = async_loop

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
        allowed = {}
        descriptor = runtime.registry.descriptor(frame.definition_id)
        from .contracts import capability_descriptors
        declarations = {item.id: item for item in capability_descriptors(runtime.registry)}
        for requirement in descriptor.capabilities:
            supplied = runtime._capabilities.get(requirement.id)
            if not isinstance(supplied, Mapping):
                raise NodeContractError(
                    "VF_CAPABILITY_MISSING",
                    f"capability '{requirement.id}' was not supplied",
                )
            operations = requirement.operations or tuple(supplied)
            policy = frame.capability_policy.get("capabilities", {})
            if requirement.id in policy:
                operations = tuple(name for name in operations if name in policy[requirement.id])
            if any(not callable(supplied.get(operation)) for operation in operations):
                raise NodeContractError(
                    "VF_CAPABILITY_MISSING",
                    f"capability '{requirement.id}' is missing a declared operation",
                )
            bound = {}
            for operation in operations:
                callback = supplied[operation]
                if callable(getattr(callback, 'with_signal', None)):
                    callback = callback.with_signal(self.signal)
                declaration = declarations.get(requirement.id)
                contract = declaration.operations.get(operation) if declaration else None
                bound[operation] = _operation(callback, contract.completion if contract else None)
            allowed[requirement.id] = MappingProxyType(bound)
        self.capabilities = MappingProxyType(allowed)
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
            if self.signal._callback_errors:
                raise ExceptionGroup(
                    "Node cancellation cleanup failed", self.signal._callback_errors
                )
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
            if self.signal._callback_errors:
                raise BaseExceptionGroup("Node cancellation cleanup failed", self.signal._callback_errors)
        finally:
            self._unsubscribe()

    def trace(self, kind, details=None):
        self._runtime._record_runtime_event(
            kind, self._frame.id, self._frame.definition_id, details=details
        )


def _operation(callback, completion):
    if completion == 'suspend':
        async def invoke(*args, **kwargs):
            from .completion import suspended
            return await suspended(callback(*args, **kwargs))
        return invoke
    if completion == 'immediate':
        def invoke(*args, **kwargs):
            from .completion import immediate
            return immediate(callback(*args, **kwargs))
        return invoke
    return callback
