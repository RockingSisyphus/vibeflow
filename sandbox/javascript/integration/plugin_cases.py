from __future__ import annotations

import json
from typing import Any

from sandbox_support import run_node


def plugin_manifest_case(result: object) -> dict[str, Any]:
    manifest_path = getattr(result, "manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    plugins = manifest["plugins"]
    active = plugins["active"]
    declared = plugins["declared"]
    assert manifest["plugin_abi_version"] == "vibeflow.plugin.v1"
    assert [item["id"] for item in active] == [
        "sandbox.policy_audit",
        "sandbox.compiler_audit",
        "sandbox.runtime_audit",
    ]
    assert len(declared) == 4
    assert plugins["planned"] == ["sandbox.future_runtime"]
    for item in active:
        assert len(item["source_hash"]) == 64
        assert len(item["config_hash"]) == 64
        assert item["completion"] == "immediate"
    return {
        "abi": manifest["plugin_abi_version"],
        "active": [item["id"] for item in active],
        "planned": plugins["planned"],
    }


def build_plugin_hook_case(result: object) -> dict[str, Any]:
    manifest = json.loads(
        getattr(result, "manifest").read_text(encoding="utf-8")
    )
    annotations = manifest["plugins"]["annotations"]
    hooks = [item["hook"] for item in annotations]
    assert hooks == [
        "extendPolicy",
        "validateGraph",
        "beforeCompile",
        "afterCompile",
        "validateCompiledGraph",
    ]
    source = getattr(result, "entry").read_text(encoding="utf-8")
    assert "policy_audit" not in source
    assert "compiler_audit" not in source
    assert "sandbox.future_runtime" not in source
    assert "sandbox.runtime_audit" in source
    return {"hooks": hooks, "runtimeOnly": True}


def runtime_plugin_repeat_case(result: object) -> Any:
    return run_node(
        getattr(result, "entry"),
        """
assert(typeof workflow.runWorkflow === "function", "sync entry is missing");
assert(workflow.runWorkflow.constructor.name !== "AsyncFunction", "plugin upgraded sync ABI");
const first = workflow.runWorkflow({ x: 10, a: 8, b: 3 });
const second = workflow.runWorkflow({ x: 7, a: 2, b: 4 });
assert(!(first instanceof Promise), "sync plugin workflow returned Promise");
assert(first.result === 15 && second.result === 5, "repeat result mismatch");
process.stdout.write(JSON.stringify({ first, second }));
""",
    )


def runtime_plugin_concurrent_isolation_case(result: object) -> Any:
    return run_node(
        getattr(result, "entry"),
        """
const values = [
  workflow.runWorkflow({ x: 1, a: 2, b: 1 }),
  workflow.runWorkflow({ x: 20, a: 4, b: 3 }),
  workflow.runWorkflow({ x: -5, a: 9, b: 2 }),
];
assert(
  JSON.stringify(values.map(item => item.result)) === "[2,21,2]",
  JSON.stringify(values),
);
process.stdout.write(JSON.stringify(values));
""",
    )
