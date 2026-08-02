"""Persistent Node JSONL session for JavaScript build-time plugins."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import as_file
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from vibeflow.targets.javascript.resources import resource
from vibeflow.targets.javascript.frontend.plugin_descriptors import (
    JavascriptPluginError,
)


@dataclass(frozen=True)
class PluginHookResult:
    implemented: bool
    result: object = None


class JavascriptPluginSession:
    """Own one plugin worker process for a deterministic build session."""

    def __init__(self, *, node_command: str = "node") -> None:
        self.node_command = str(node_command)
        self._resource_context = None
        self._process: subprocess.Popen[str] | None = None
        self._opened: list[str] = []

    def __enter__(self) -> JavascriptPluginSession:
        context = as_file(resource("plugin_worker.mjs"))
        worker_path = context.__enter__()
        self._resource_context = context
        try:
            self._process = subprocess.Popen(
                [self.node_command, str(worker_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except Exception:
            context.__exit__(None, None, None)
            self._resource_context = None
            raise
        return self

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
        self._request({"command": "close", "sessionId": normalized})
        self._opened.remove(normalized)

    def __exit__(self, exc_type, exc, traceback) -> None:
        for session_id in reversed(tuple(self._opened)):
            try:
                self.close(session_id)
            except Exception:
                if exc is None:
                    raise
        process = self._process
        self._process = None
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        context = self._resource_context
        self._resource_context = None
        if context is not None:
            context.__exit__(exc_type, exc, traceback)

    def _request(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
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
        line = process.stdout.readline()
        if not line:
            stderr = process.stderr.read() if process.stderr is not None else ""
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
