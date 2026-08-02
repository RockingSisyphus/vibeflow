from __future__ import annotations

import json
from typing import Any

from sandbox_support import (
    BuildCache,
    CONFIG_ROOT,
    PROJECT_ROOT,
    assert_equal,
    run_node,
)
from vibeflow.tooling.application.javascript_build import (
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

_PERMANENT_PORT_SCRIPT = """
const state = globalThis.__vibeflowSandboxPortState;
const afterImport = [...state.calls];
const host = workflow.createWorkflowHost();
const afterCreate = [...state.calls];
await host.start();
const invocation = host.runWorkflowAsync({});
let failureCode = null;
const observedInvocation = invocation.then(
  () => { failureCode = "completed"; },
  error => { failureCode = error.code; },
);
await Promise.race([
  Promise.all([state.firstOutputReady, state.waitingReady]),
  new Promise((_, reject) => setTimeout(
    () => reject(new Error("permanent Port workflow did not reach its wait state")),
    2000,
  )),
]);
await host.stop();
await observedInvocation;
await host.stop();
assert(invocation instanceof Promise, "async host invocation is not a Promise");
assert(failureCode === "VF_ABORTED", String(failureCode));
assert(JSON.stringify(afterImport) === "[]", JSON.stringify(afterImport));
assert(JSON.stringify(afterCreate) === '["create"]', JSON.stringify(afterCreate));
assert(
  JSON.stringify(state.received) ===
    '[{"port":"sandbox.permanent.in"},{"port":"sandbox.permanent.in"}]',
  JSON.stringify(state.received),
);
assert(
  JSON.stringify(state.sent) ===
    '[{"port":"sandbox.permanent.out","value":14}]',
  JSON.stringify(state.sent),
);
assert(
  JSON.stringify(state.calls) === '["create","start","stop"]',
  JSON.stringify(state.calls),
);
assert(host.started === false, "stopped host still reports started");
process.stdout.write(JSON.stringify({
  afterImport,
  afterCreate,
  calls: state.calls,
  received: state.received,
  sent: state.sent,
  failureCode,
  invocationWasPromise: invocation instanceof Promise,
  browserFiles: browserResultFiles,
}));
"""


def _build(
    cache: BuildCache,
    *,
    key: str,
    config: str,
    target: str,
    profile: str,
):
    return build_project_aot(
        ProjectBuildRequest(
            workspace=_HOST_WORKSPACE,
            config=CONFIG_ROOT / config,
            out_dir=cache.root / key,
            target=target,
            profile=profile,
        )
    )


def _port_setup(browser_files: tuple[str, ...]) -> str:
    return f"""
let resolveFirstOutput;
let resolveWaiting;
globalThis.__vibeflowSandboxPortState = {{
  inputs: [4],
  received: [],
  sent: [],
  calls: [],
  firstOutputReady: new Promise(resolve => {{ resolveFirstOutput = resolve; }}),
  waitingReady: new Promise(resolve => {{ resolveWaiting = resolve; }}),
  resolveFirstOutput: () => resolveFirstOutput(),
  resolveWaiting: () => resolveWaiting(),
}};
const browserResultFiles = {json.dumps(list(browser_files))};
"""


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
        manifest["host_extensions"],
        ["sandbox.math_host"],
        label="host extension manifest",
    )
    return payload


def permanent_port_host_case(cache: BuildCache) -> dict[str, Any]:
    node_result = _build(
        cache,
        key="permanent_port_host_node",
        config="permanent_port_host.jsonc",
        target="node",
        profile="single-esm",
    )
    browser_result = _build(
        cache,
        key="permanent_port_host_browser",
        config="permanent_port_host.jsonc",
        target="browser",
        profile="esm-module",
    )
    payload = run_node(
        node_result.entry,
        _PERMANENT_PORT_SCRIPT,
        before_import=_port_setup(browser_result.files),
    )
    manifest = json.loads(node_result.manifest.read_text(encoding="utf-8"))
    assert_equal(
        manifest["host_extensions"],
        ["sandbox.port_host"],
        label="permanent Port host extension manifest",
    )
    return payload
