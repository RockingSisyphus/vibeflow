"""Native Python client with a node-nonblocking outbox and cancellable waits."""
import json
import os
from queue import Queue
from threading import Event, Lock, Thread, current_thread
from time import monotonic
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .protocol import CoordinationError, json_value


class _Operation:
    def __init__(self, callback, signal=None):
        self.callback, self.signal = callback, signal

    def with_signal(self, signal):
        return type(self)(self.callback, signal)

    def __call__(self, request=None):
        return self.callback(request or {}, self.signal)


class WorkflowClient:
    def __init__(self, url, *, identifier=None, workflow=None, stop=None):
        self.url = url.rstrip("/")
        self.stop = stop
        registered = self.request("register", {"id": identifier, "workflow": workflow,
            "pid": os.getpid(), "stop_supported": stop is not None})
        self.id = registered["id"]
        self.inputs, self.entry = registered["inputs"], registered["entry"]
        self._outbox, self._errors = Queue(), []
        self._closed = Event()
        self._finish_lock = Lock()
        self._sender = Thread(target=self._send_loop, daemon=True, name="vibeflow-outbox")
        self._sender.start()
        self._watcher = None
        if stop is not None:
            self._watcher = Thread(target=self._watch_stop, daemon=True, name="vibeflow-stop")
            self._watcher.start()

    @classmethod
    def from_environment(cls, **options):
        return cls(os.environ["VIBEFLOW_COORDINATION_URL"],
                   identifier=os.environ.get("VIBEFLOW_INSTANCE_ID"), **options)

    def request(self, operation, value):
        body = json.dumps(json_value(value), ensure_ascii=False, allow_nan=False).encode()
        request = Request(self.url + "/" + operation, data=body, headers={"Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=5 if operation != "call" else None)
        except HTTPError as error:
            response = error
        with response:
            result = json.load(response)
        if "error" in result:
            raise CoordinationError(result["error"]["code"], result["error"]["message"])
        return result["value"]

    def _send_loop(self):
        while True:
            request = self._outbox.get()
            try:
                if request is None:
                    return
                self.request("send", request)
            except Exception as error:
                self._errors.append(error)
            finally:
                self._outbox.task_done()

    def _watch_stop(self):
        try:
            while not self._closed.is_set():
                state = self.request("control", {"id": self.id})
                if state.get("stop"):
                    self.stop()
                    return
                if state.get("ended"):
                    return
        except Exception as error:
            if not self._closed.is_set():
                self._errors.append(error)

    def flush(self):
        self._outbox.join()
        if self._errors:
            raise self._errors[0]

    def send(self, identifier, port, payload):
        with self._finish_lock:
            if self._closed.is_set():
                raise CoordinationError("VF_INSTANCE_ENDED", self.id)
            self._outbox.put(json_value({"id": identifier, "sender": self.id, "port": port, "payload": payload}))

    def _wait(self, operation, identifier, *, port=None, timeout=None, signal=None):
        deadline = None if timeout is None else monotonic() + timeout
        while True:
            if signal is not None:
                signal.throw_if_aborted()
            if self._closed.is_set():
                raise CoordinationError("VF_INSTANCE_ENDED", self.id)
            if deadline is not None and monotonic() >= deadline:
                raise CoordinationError("VF_WAIT_TIMEOUT", identifier)
            request = {"id": identifier}
            if port is not None:
                request["port"] = port
            result = self.request(operation, request)
            if not result.get("pending"):
                return result

    def wait(self, identifier, *, timeout=None, signal=None):
        return self._wait("wait", identifier, timeout=timeout, signal=signal)

    def receive(self, port="default", *, timeout=None, signal=None):
        return self._wait("receive", self.id, port=port, timeout=timeout, signal=signal)

    def kill(self, identifier, *, timeout=None, signal=None):
        self.request("kill", {"id": identifier})
        return self.wait(identifier, timeout=timeout, signal=signal)

    def call(self, target, *, entry=None, inputs=None, timeout=None, signal=None):
        launched = self.request("call", {"target": target, "entry": entry, "inputs": inputs or {}})
        return self._wait("ready", launched["id"], timeout=timeout, signal=signal)

    def operations(self):
        return {"self": _Operation(lambda request, signal: {"id": self.id}),
            "call": _Operation(lambda request, signal: self.call(request["target"], entry=request.get("entry"),
                inputs=request.get("inputs"), timeout=request.get("timeout"), signal=signal)),
            "wait": _Operation(lambda request, signal: self.wait(request["id"], timeout=request.get("timeout"), signal=signal)),
            "send": _Operation(lambda request, signal: self.send(request["id"], request.get("port", "default"), request.get("payload"))),
            "receive": _Operation(lambda request, signal: self.receive(request.get("port", "default"), timeout=request.get("timeout"), signal=signal)),
            "kill": _Operation(lambda request, signal: self.kill(request["id"], timeout=request.get("timeout"), signal=signal))}

    def finish(self, *, state="succeeded", outputs=None, error=None):
        with self._finish_lock:
            result = self._finish(state=state, outputs=outputs, error=error)
        if self._watcher is not None and self._watcher is not current_thread():
            self._watcher.join()
        return result

    def _finish(self, *, state, outputs, error):
        if self._closed.is_set():
            return
        try:
            delivery_error = None
            try:
                self.flush()
            except Exception as failure:
                delivery_error = failure
                state, error = "failed", {"code": getattr(failure, "code", "VF_DELIVERY_FAILED"), "message": str(failure)}
            payload = {"id": self.id, "state": state, "outputs": outputs, "error": error}
            try:
                payload = json_value(payload)
            except Exception as failure:
                delivery_error = delivery_error or failure
                payload = {"id": self.id, "state": "failed", "outputs": None,
                    "error": {"code": "VF_RESULT_NOT_JSON", "message": str(failure)}}
            result = self.request("complete", payload)
            if delivery_error is not None:
                raise delivery_error
            return result
        finally:
            self._closed.set()
            self._outbox.put(None)
            self._sender.join()
