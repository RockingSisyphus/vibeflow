"""Threaded loopback router. Launchers and hosts retain lifecycle responsibility."""
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import subprocess
from threading import Condition, Thread
from time import monotonic

from .protocol import CoordinationError, TERMINAL, instance_id, json_value


class WorkflowServer:
    def __init__(self, *, targets=None, port=0):
        self.targets = dict(targets or {})
        self.instances = {}
        self.changed = Condition()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self):
                try:
                    request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                    result = {"value": owner.dispatch(self.path.removeprefix("/"), request)}
                    code = 200
                except Exception as error:
                    result = {"error": {"code": getattr(error, "code", "VF_COORDINATION_REQUEST"), "message": str(error)}}
                    code = 400
                body = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # The requester can cancel a wait without stopping its peer.

        self.http = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.http.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        self.thread = None

    def start(self):
        self.thread = Thread(target=self.http.serve_forever, daemon=True, name="vibeflow-router")
        self.thread.start()
        return self

    def close(self):
        # Closing routing never stops independently running workflow processes.
        if self.thread is not None:
            self.http.shutdown()
            self.thread.join()
        self.http.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *error):
        self.close()

    def _reserve(self, identifier=None, **values):
        key = identifier or instance_id()
        if key in self.instances:
            raise CoordinationError("VF_INSTANCE_EXISTS", key)
        self.instances[key] = dict(id=key, state="starting", registered=False,
            mailboxes={}, stop_requested=False, stop_supported=False, outputs=None, error=None, **values)
        return self.instances[key]

    def _instance(self, identifier):
        try:
            return self.instances[identifier]
        except KeyError as error:
            raise CoordinationError("VF_INSTANCE_UNKNOWN", str(identifier)) from error

    @staticmethod
    def _status(item):
        return {k: item.get(k) for k in ("id", "state", "outputs", "error", "pid", "workflow", "entry")}

    def dispatch(self, operation, request):
        if operation == "call":
            return self._launch(request)
        with self.changed:
            if operation == "instances":
                return [self._status(item) for item in self.instances.values()]
            if operation == "register":
                key = request.get("id")
                item = self._instance(key) if key in self.instances else self._reserve(key)
                if item["registered"]:
                    raise CoordinationError("VF_INSTANCE_EXISTS", item["id"])
                if item["state"] in TERMINAL:
                    raise CoordinationError("VF_INSTANCE_ENDED", item["id"])
                item.update(registered=True, state="running", pid=request.get("pid"),
                    workflow=request.get("workflow"), stop_supported=bool(request.get("stop_supported")))
                self.changed.notify_all()
                return {"id": item["id"], "inputs": item.get("inputs", {}), "entry": item.get("entry")}
            item = self._instance(request.get("id"))
            if operation == "status":
                return self._status(item)
            if operation == "complete":
                state = request["state"]
                if state not in TERMINAL:
                    raise ValueError("completion state must be succeeded, failed or cancelled")
                if item["state"] in TERMINAL:
                    raise CoordinationError("VF_INSTANCE_ENDED", item["id"])
                item.update(state=state, outputs=json_value(request.get("outputs")), error=request.get("error"))
                self.changed.notify_all()
                return self._status(item)
            if operation == "send":
                if item["state"] in TERMINAL:
                    raise CoordinationError("VF_INSTANCE_ENDED", item["id"])
                sender = self._instance(request["sender"])
                item["mailboxes"].setdefault(request.get("port", "default"), deque()).append(
                    {"sender": sender["id"], "port": request.get("port", "default"), "payload": json_value(request.get("payload"))})
                self.changed.notify_all()
                return {"accepted": True}
            if operation == "kill":
                if item["state"] not in TERMINAL:
                    if not item["stop_supported"]:
                        raise CoordinationError("VF_STOP_UNSUPPORTED", item["id"])
                    item.update(stop_requested=True, state="stopping")
                    self.changed.notify_all()
                return self._status(item)
            if operation in {"ready", "wait", "receive", "control"}:
                deadline = monotonic() + min(max(float(request.get("poll", .25)), 0), 1)
                while True:
                    if operation == "ready":
                        if item["registered"]:
                            return {"id": item["id"]}
                        if item["state"] in TERMINAL:
                            raise CoordinationError("VF_LAUNCH_FAILED", item["error"])
                    if operation == "wait" and item["state"] in TERMINAL:
                        return self._status(item)
                    if operation == "control" and (item["stop_requested"] or item["state"] in TERMINAL):
                        return {"stop": item["stop_requested"], "ended": item["state"] in TERMINAL}
                    if operation == "receive":
                        mailbox = item["mailboxes"].setdefault(request.get("port", "default"), deque())
                        if mailbox:
                            return mailbox.popleft()
                        if item["state"] in TERMINAL:
                            raise CoordinationError("VF_INSTANCE_ENDED", item["id"])
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        return {"pending": True}
                    self.changed.wait(remaining)
            raise ValueError("unknown coordination operation: " + operation)

    def _launch(self, request):
        target = self.targets.get(request.get("target"))
        if target is None:
            raise CoordinationError("VF_TARGET_UNKNOWN", str(request.get("target")))
        command = target.get("command")
        if not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command):
            raise ValueError("target.command must be a non-empty array of arguments")
        with self.changed:
            item = self._reserve(inputs=json_value(request.get("inputs", {})),
                entry=request.get("entry") if request.get("entry") is not None else target.get("entry") or None)
        environment = {**os.environ, **target.get("env", {}), "VIBEFLOW_COORDINATION_URL": self.url,
                       "VIBEFLOW_INSTANCE_ID": item["id"]}
        try:
            process = subprocess.Popen(command, cwd=target.get("cwd"), env=environment,
                start_new_session=os.name == "posix", close_fds=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        except Exception as error:
            with self.changed:
                item.update(state="failed", error=str(error))
                self.changed.notify_all()
            raise

        def reap_launcher():
            code = process.wait()
            with self.changed:
                if code and not item["registered"]:
                    item.update(state="failed", error=f"launcher exited with code {code}")
                    self.changed.notify_all()
        Thread(target=reap_launcher, daemon=True, name="vibeflow-launcher-reaper").start()
        return {"id": item["id"]}
