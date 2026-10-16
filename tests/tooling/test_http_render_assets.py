"""Loopback asset registration must not expose neighboring files or symlinks."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_browser_asset_server_limits_access_and_closes(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "graph.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    secret = tmp_path / "neighbor.svg"
    secret.write_text("must not be served")
    try:
        (assets / "escape.svg").symlink_to(secret)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    module = Path(__file__).resolve().parents[2] / "src/vibeflow/tooling/presentation/http_assets.mjs"
    script = """
import assert from 'node:assert/strict';
import {serveAssets} from MODULE;
const server = await serveAssets({mounts:{assets:ROOT}, files:{'one.svg':FILE}});
const url = server.url('one.svg');
try {
  const response = await fetch(url);
  assert.equal(response.status,200);
  assert.equal(response.headers.get('content-type'),'image/svg+xml');
  assert.match(await response.text(), /<svg/);
  for (const path of ['assets/', 'assets/escape.svg', 'assets/%2e%2e%2fneighbor.svg',
                      'assets/%252e%252e%252fneighbor.svg', 'neighbor.svg']) {
    assert.equal((await fetch(server.url(path))).status,404,path);
  }
  assert.equal((await fetch(new URL('/one.svg',url))).status,404);
  assert.equal((await fetch(url,{method:'POST'})).status,405);
  assert.equal((await fetch(server.url('assets/graph.svg'))).status,200);
} finally {await server.close();}
await assert.rejects(fetch(url,{signal:AbortSignal.timeout(2000)}));
""".replace("MODULE", json.dumps(module.as_uri())).replace("ROOT", json.dumps(str(assets))).replace("FILE", json.dumps(str(assets / "graph.svg")))
    result = subprocess.run([node, "--input-type=module", "--eval", script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_invalid_mermaid_render_releases_browser_and_listener(tmp_path, monkeypatch):
    if not os.environ.get("VIBEFLOW_MERMAID_RENDERER_ROOT"):
        pytest.skip("real Mermaid renderer is not configured")
    from vibeflow.tooling.presentation import mermaid

    monkeypatch.setattr(mermaid, "_puppeteer_launch_options", lambda: [("configured browser", None)])
    # A caught render error must let Node exit naturally; an open listener would
    # keep the process alive and hit Python's hard subprocess timeout instead.
    with pytest.raises(mermaid.MermaidRenderError, match="UnknownDiagramError|No diagram type|Parse error"):
        mermaid.render_mermaid_svg("not a Mermaid diagram", tmp_path / "invalid.svg", timeout_seconds=10)
    assert not (tmp_path / "invalid.svg").exists()


def test_mermaid_failure_keeps_exit_status_and_full_stderr(tmp_path, monkeypatch):
    from vibeflow.tooling.presentation import mermaid

    monkeypatch.setattr(mermaid, "_find_mmdc", lambda: tmp_path / "mmdc")
    monkeypatch.setattr(mermaid, "_ensure_mermaid_cli_compat", lambda: None)
    monkeypatch.setattr(mermaid, "_puppeteer_launch_options", lambda: [("fixture browser", None)])
    message = "Failed to launch browser\npthread_create: Resource temporarily unavailable\nlast diagnostic line"
    monkeypatch.setattr(mermaid.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, -15, stdout="", stderr=message))
    with pytest.raises(mermaid.MermaidRenderError) as error:
        mermaid.render_mermaid_svg("flowchart TD;A-->B", tmp_path / "graph.svg")
    assert "returncode=-15" in str(error.value)
    assert message in str(error.value)
