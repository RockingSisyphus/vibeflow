"""Node-local access to one fixed workflow session."""
from vibeflow.coordination.protocol import CoordinationError
from .completion import immediate, suspended


class NodeWorkflow:
    def __init__(self, identity, session, signal):
        self._identity, self._session, self._signal = identity, session, signal

    def self(self):
        return self._identity.self()

    def _operation(self, name):
        operation = getattr(self._session, name, None)
        if not callable(operation):
            raise CoordinationError("VF_WORKFLOW_UNCONNECTED" if self._session is None else "VF_WORKFLOW_UNSUPPORTED",
                f"workflow session does not provide {name}")
        return operation

    def invoke_sync(self, request):
        return immediate(self._operation("invoke_sync")(request, signal=self._signal))

    def send(self, request):
        return immediate(self._operation("send")(request, signal=self._signal))

    async def call(self, request):
        return await suspended(self._operation("call")(request, signal=self._signal))

    async def wait(self, request):
        return await suspended(self._operation("wait")(request, signal=self._signal))

    async def receive(self, request=None):
        return await suspended(self._operation("receive")(request or {}, signal=self._signal))

    async def kill(self, request):
        return await suspended(self._operation("kill")(request, signal=self._signal))
