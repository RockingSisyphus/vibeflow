"""Persistent Node JSONL session for JavaScript lifecycle plugins and Rules."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import tempfile
from queue import Queue, Empty
from threading import Thread
from typing import Any, Mapping

from vibeflow.targets.javascript.resources import materialized_resources
from vibeflow.targets.javascript.frontend.plugin_descriptors import (
    JavascriptPluginError,
)


@dataclass(frozen=True)
class PluginHookResult:
    implemented: bool
    result: object = None


class JavascriptPluginSession:
    """Own one worker process for a lifecycle or formal Rule check session."""

    def __init__(self, *, node_command: str = "node") -> None:
        self.node_command = str(node_command)
        self._resource_context = None
        self._process: subprocess.Popen[str] | None = None
        self._opened: list[str] = []
        self._stderr = None
        self._responses = None
        self._reader = None

    def __enter__(self) -> JavascriptPluginSession:
        context = materialized_resources()
        worker_path = context.__enter__() / "plugin_worker.mjs"
        self._resource_context = context
        self._stderr = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
        try:
            self._process = subprocess.Popen(
                [self.node_command, str(worker_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            responses = Queue()
            self._responses = responses
            output = self._process.stdout
            def read_responses():
                try:
                    for line in output:
                        responses.put(line)
                except (OSError, ValueError):
                    pass
                finally:
                    responses.put("")
            self._reader = Thread(target=read_responses, daemon=True)
            self._reader.start()
        except Exception:
            context.__exit__(None, None, None)
            self._resource_context = None
            self._stderr.close()
            self._stderr = None
            raise
        return self

    def declarations(self, *, module, package_root, export="plugin"):
        return self._request({"command": "declarations", "module": str(module),
                              "packageRoot": str(package_root), "export": export})

    def resource_declarations(self, *, module, package_root):
        return self._request({"command": "declarations", "resourcesOnly": True,
                              "module": str(module), "packageRoot": str(package_root)})

    def open(
        self,
        session_id: str,
        *,
        plugin: Mapping[str, Any],
        package_root: str | Path,
        target: str,
        workflow_id: str,
    ) -> None:
        self._request(
            {
                "command": "open",
                "sessionId": str(session_id),
                "plugin": dict(plugin),
                "packageRoot": str(Path(package_root).resolve()),
                "target": str(target),
                "workflowId": str(workflow_id),
            }
        )
        self._opened.append(str(session_id))

    def open_rule(
        self, session_id: str, *, rule: Mapping[str, Any],
        package_root: str | Path, target: str = "javascript",
    ) -> None:
        self._request({
            "command": "openRule", "sessionId": session_id, "rule": dict(rule),
            "packageRoot": str(Path(package_root).resolve()), "target": target,
        })
        self._opened.append(session_id)

    def evaluate_rule(
        self, session_id: str, *, context: Mapping[str, Any],
        params: Mapping[str, Any], inputs: Mapping[str, Any],
    ) -> object:
        response = self._request({
            "command": "evaluateRule", "sessionId": session_id,
            "context": dict(context), "params": dict(params), "inputs": dict(inputs),
        })
        return response.get("result")

    def invoke(
        self,
        session_id: str,
        hook: str,
        payload: Mapping[str, Any],
    ) -> PluginHookResult:
        result = self._request(
            {
                "command": "invoke",
                "sessionId": str(session_id),
                "hook": str(hook),
                "payload": dict(payload),
            }
        )
        return PluginHookResult(
            implemented=bool(result.get("implemented", False)),
            result=result.get("result"),
        )

    def close(self, session_id: str) -> None:
        normalized = str(session_id)
        if normalized not in self._opened:
            return
        try:
            self._request({"command": "close", "sessionId": normalized}, timeout=10)
        finally:
            self._opened.remove(normalized)

    def __exit__(self, exc_type, exc, traceback) -> None:
        errors = []
        def release(action):
            try:
                action()
            except Exception as error:
                errors.append(error)
        for session_id in reversed(tuple(self._opened)):
            release(lambda session_id=session_id: self.close(session_id))
        process = self._process
        self._process = None
        if process is not None:
            if process.stdin is not None:
                release(process.stdin.close)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                release(process.terminate)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    release(process.kill)
                    release(lambda: process.wait(timeout=5))
            except Exception as error:
                errors.append(error)
            for stream in (process.stdout, process.stdin):
                if stream is not None:
                    release(stream.close)
        context = self._resource_context
        self._resource_context = None
        if context is not None:
            release(lambda: context.__exit__(exc_type, exc, traceback))
        if self._stderr is not None:
            release(self._stderr.close)
            self._stderr = None
        if self._reader is not None:
            release(lambda: self._reader.join(timeout=1))
        self._reader = self._responses = None
        self._opened.clear()
        from vibeflow.targets.javascript.build.cleanup import finish_cleanup
        finish_cleanup(exc, errors)

    def _request(self, payload: Mapping[str, Any], *, timeout=180) -> Mapping[str, Any]:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise JavascriptPluginError(
                "VF_PLUGIN_PROCESS",
                "JavaScript plugin session is not running",
            )
        process.stdin.write(
            json.dumps(
                dict(payload),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )
        process.stdin.flush()
        try:
            line = self._responses.get(timeout=timeout)
        except Empty as error:
            raise JavascriptPluginError("VF_PLUGIN_TIMEOUT",
                f"JavaScript plugin worker timed out during {payload.get('command')}") from error
        if not line:
            stderr = ""
            if self._stderr is not None:
                self._stderr.seek(0)
                stderr = self._stderr.read()
            raise JavascriptPluginError(
                "VF_PLUGIN_PROCESS",
                f"JavaScript plugin worker exited unexpectedly: {stderr.strip()}",
            )
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JavascriptPluginError(
                "VF_PLUGIN_PROCESS",
                "JavaScript plugin worker returned invalid JSON",
            ) from exc
        if not isinstance(response, Mapping):
            raise JavascriptPluginError(
                "VF_PLUGIN_PROCESS",
                "JavaScript plugin worker returned a non-object response",
            )
        if not response.get("ok"):
            error = response.get("error")
            details = dict(error) if isinstance(error, Mapping) else {}
            raise JavascriptPluginError(
                str(details.get("code", "VF_PLUGIN_PROCESS")),
                str(details.get("message", "JavaScript plugin worker failed")),
                details=(
                    details.get("details")
                    if isinstance(details.get("details"), Mapping)
                    else {}
                ),
            )
        result = response.get("result")
        if not isinstance(result, Mapping):
            raise JavascriptPluginError(
                "VF_PLUGIN_PROCESS",
                "JavaScript plugin worker omitted its result object",
            )
        return result


__all__ = [
    "JavascriptPluginError",
    "JavascriptPluginSession",
    "PluginHookResult",
]
