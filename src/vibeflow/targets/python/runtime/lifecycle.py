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

    def __init__(self):
        self._event = Event()
        self._lock = Lock()
        self._listeners = set()
        self._callback_errors = []
        self.reason = None

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
                listener(reason)
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
                listener(self.reason)
            except Exception as error:
                with self._lock:
                    self._callback_errors.append(error)

        def remove():
            with self._lock:
                self._listeners.discard(listener)

        return remove


class NodeRunContext:
    def __init__(self, runtime, frame):
        allowed = {}
        descriptor = runtime.registry.descriptor(frame.type_used)
        for requirement in descriptor.capabilities:
            supplied = runtime._capabilities.get(requirement.id)
            if not isinstance(supplied, Mapping):
                raise NodeContractError(
                    "VF_CAPABILITY_MISSING",
                    f"capability '{requirement.id}' was not supplied",
                )
            operations = requirement.operations or tuple(supplied)
            if any(not callable(supplied.get(operation)) for operation in operations):
                raise NodeContractError(
                    "VF_CAPABILITY_MISSING",
                    f"capability '{requirement.id}' is missing a declared operation",
                )
            allowed[requirement.id] = MappingProxyType(
                {operation: supplied[operation] for operation in operations}
            )
        self.capabilities = MappingProxyType(allowed)
        self._runtime, self._frame = runtime, frame
        self.signal = CancellationSignal()
        self._unsubscribe = runtime._signal.subscribe(self.signal.request_stop)

    def close(self):
        try:
            self.signal.request_stop("Node exiting")
            if self.signal._callback_errors:
                raise ExceptionGroup(
                    "Node cancellation cleanup failed", self.signal._callback_errors
                )
        finally:
            self._unsubscribe()

    def trace(self, kind, details=None):
        self._runtime._record_runtime_event(
            kind, self._frame.id, self._frame.type_used, details=details
        )
