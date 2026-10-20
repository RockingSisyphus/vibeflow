"""Real browser host uses the same instance protocol as Python and Node."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
from threading import Thread
from time import monotonic, sleep

import pytest

from tests.coordination.test_hosts import node_module
from vibeflow.coordination import WorkflowClient, WorkflowServer
from vibeflow.tooling.presentation.mermaid import _find_mmdc, is_mermaid_svg_renderer_available


def test_browser_generated_workflow_messages_completion_and_cooperative_stop(tmp_path):
    if not is_mermaid_svg_renderer_available():
        pytest.skip("browser dependencies are supplied by the full gate")
    resources = Path(__file__).resolve().parents[2] / "src/vibeflow/targets/javascript/resources"
    for name in ("workflow_client.mjs", "workflow_host.mjs"):
        shutil.copyfile(resources / "coordination" / name, tmp_path / name)
    node_module(tmp_path)
    (tmp_path / "index.html").write_text("<!doctype html><title>Workflow host acceptance</title>")
    script = Path(__file__).resolve().parents[1] / "fixtures/preview/coordination.cjs"
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    http = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(tmp_path)))
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with WorkflowServer() as server:
            client = WorkflowClient(server.url)
            process = subprocess.Popen(["node", str(script), str(_find_mmdc().resolve()),
                f"http://127.0.0.1:{http.server_port}", server.url], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                for index in range(2):
                    deadline = monotonic() + 20
                    while True:
                        instances = [item for item in client.request("instances", {}) if item["workflow"] == f"browser-{index}"]
                        if instances:
                            identity = instances[0]["id"]
                            break
                        if monotonic() > deadline or process.poll() is not None:
                            raise AssertionError(f"browser did not register {index}: {process.poll()}")
                        sleep(.02)
                    if index == 0:
                        client.send(identity, "request", {"value": 14})
                        message = client.receive("reply", timeout=10)
                        assert message["payload"] == {"value": 42, "self": identity}
                        assert client.wait(identity, timeout=10)["outputs"] == {"result": 42}
                    else:
                        assert client.kill(identity, timeout=10)["state"] == "cancelled"
                stdout, stderr = process.communicate(timeout=15)
                assert process.returncode == 0, stdout + stderr
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                client.finish()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
