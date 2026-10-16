from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from sandbox_support import (
    BuildCache,
    CONFIG_ROOT,
    PROJECT_ROOT,
    assert_equal,
    run_browser_long_host,
    run_node,
)
from vibeflow.tooling.application.javascript.build import (
    ProjectBuildRequest,
    build_project_aot,
)


_HOST_WORKSPACE = PROJECT_ROOT.parent / "vibeflow_host_config.jsonc"

_LIFECYCLE_SCRIPT = """
const afterImport = [...globalThis.__vibeflowSandboxHostCalls];
const host = workflow.createWorkflowHost();
const afterCreate = [...globalThis.__vibeflowSandboxHostCalls];
await host.start();
const answer = host.runWorkflow({ x: 8 });
await host.stop();
await host.stop();
assert(answer.result === 16, JSON.stringify(answer));
assert(JSON.stringify(afterImport) === "[]", JSON.stringify(afterImport));
assert(
  JSON.stringify(globalThis.__vibeflowSandboxHostCalls) ===
    '["create","start","stop"]',
  JSON.stringify(globalThis.__vibeflowSandboxHostCalls),
);
process.stdout.write(JSON.stringify({
  answer,
  afterImport,
  afterCreate,
  calls: globalThis.__vibeflowSandboxHostCalls,
}));
"""



def _build(
    cache: BuildCache,
    *,
    key: str,
    config: str,
    target: str,
    profile: str,
    html_template: Path | None = None,
    app_entry: Path | None = None,
):
    return build_project_aot(
        ProjectBuildRequest(
            workspace=_HOST_WORKSPACE,
            config=CONFIG_ROOT / config,
            out_dir=cache.root / key,
            target=target,
            profile=profile,
            html_template=html_template,
            app_entry=app_entry,
        )
    )




def host_extension_case(cache: BuildCache) -> dict[str, Any]:
    result = _build(
        cache,
        key="host_extension",
        config="host_extension.jsonc",
        target="node",
        profile="single-esm",
    )
    payload = run_node(
        result.entry,
        _LIFECYCLE_SCRIPT,
        before_import="globalThis.__vibeflowSandboxHostCalls = [];",
    )
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert_equal(
        manifest["target_metadata"]["host_extensions"],
        ["sandbox.math_host"],
        label="host extension manifest",
    )
    return payload




def browser_permanent_port_host_case(
    cache: BuildCache,
    *,
    puppeteer_root: Path,
    profile: str,
) -> dict[str, Any]:
    if profile == "web-app":
        result = _build(
            cache,
            key="browser_permanent_port_host_web",
            config="browser_permanent_port_host.jsonc",
            target="browser",
            profile="web-app",
            html_template=PROJECT_ROOT / "web/browser_host.template.html",
            app_entry=PROJECT_ROOT / "web/browser_host_app.ts",
        )
        module_entry = None
    elif profile == "esm-module":
        result = _build(
            cache,
            key="browser_permanent_port_host_esm",
            config="browser_permanent_port_host.jsonc",
            target="browser",
            profile="esm-module",
        )
        shutil.copy2(
            PROJECT_ROOT / "web/browser_host.template.html",
            result.out_dir / "index.html",
        )
        module_entry = result.entry.name
    else:
        raise AssertionError(f"unsupported browser Host profile: {profile}")

    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert_equal(
        manifest["target_metadata"]["host_extensions"],
        ["sandbox.browser_port_host"],
        label=f"{profile} browser Port host extension manifest",
    )
    payload = run_browser_long_host(
        result.out_dir,
        puppeteer_root=puppeteer_root,
        module_entry=module_entry,
    )
    payload["profile"] = profile
    payload["files"] = list(result.files)
    return payload


__all__ = [
    "browser_permanent_port_host_case",
    "host_extension_case",
]
