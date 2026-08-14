"""Executable JavaScript Plugin lifecycle and isolation tests."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest

from vibeflow.block_compiler import SourceRef
from vibeflow.targets.javascript.build.plugin_hooks import (
    JavascriptBuildPluginRunner,
)
from vibeflow.targets.javascript.frontend.bindings import (
    JavascriptPluginBinding,
)
from vibeflow.targets.javascript.frontend.errors import AotBuildError
from vibeflow.targets.javascript.frontend.plugin_descriptors import (
    JavascriptPluginBindingPlan,
    JavascriptPluginError,
)
from vibeflow.tooling.application.javascript.build import (
    ProjectBuildError,
    ProjectBuildRequest,
    build_project_aot,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SANDBOX_PROJECT = REPOSITORY_ROOT / "sandbox/javascript/integration/project"
DEFAULT_TOOLCHAIN_PROJECT = REPOSITORY_ROOT / "sandbox/javascript/minimal/project"


@dataclass(frozen=True)
class _Project:
    root: Path
    workspace: Path
    host_workspace: Path


@pytest.fixture
def javascript_toolchain_root() -> Path:
    configured = os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT")
    root = (
        Path(configured).expanduser().resolve()
        if configured
        else DEFAULT_TOOLCHAIN_PROJECT
    )
    if not (root / "node_modules").is_dir():
        pytest.skip(
            "JavaScript Plugin execution tests require a project-local "
            "TypeScript/esbuild toolchain; the full gate sets "
            "VIBEFLOW_TEST_TOOLCHAIN_ROOT"
        )
    return root


@pytest.fixture
def plugin_package(
    tmp_path: Path,
    javascript_toolchain_root: Path,
) -> Path:
    root = tmp_path / "package"
    root.mkdir()
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(javascript_toolchain_root / name, root / name)
    (root / "node_modules").symlink_to(
        javascript_toolchain_root / "node_modules",
        target_is_directory=True,
    )
    (root / "plugins").mkdir()
    return root


@pytest.fixture
def javascript_project(
    tmp_path: Path,
    javascript_toolchain_root: Path,
) -> _Project:
    root = tmp_path / "project"
    shutil.copytree(
        SANDBOX_PROJECT,
        root,
        ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc"),
    )
    (root / "node_modules").symlink_to(
        javascript_toolchain_root / "node_modules",
        target_is_directory=True,
    )
    workspace = tmp_path / "workspace.jsonc"
    workspace.write_text(
        json.dumps(
            {
                "roots": [
                    {
                        "id": "plugin-test",
                        "path": "project",
                        "config": "vibeflow_project.jsonc",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    host_workspace = tmp_path / "host-workspace.jsonc"
    host_workspace.write_text(
        json.dumps(
            {
                "roots": [
                    {
                        "id": "plugin-host-test",
                        "path": "project",
                        "config": "vibeflow_host_project.jsonc",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return _Project(
        root=root,
        workspace=workspace,
        host_workspace=host_workspace,
    )


def _binding(
    root: Path,
    plugin_id: str,
    plugin_type: str,
    source: str,
    *,
    completion: str = "immediate",
    priority: int = 100,
) -> JavascriptPluginBinding:
    path = root / "plugins" / f"{plugin_id}.ts"
    path.write_text(source, encoding="utf-8")
    return JavascriptPluginBinding(
        id=plugin_id,
        plugin_type=plugin_type,
        status="implemented",
        target="node",
        implementation=SourceRef(
            kind="file",
            ref=str(path),
            export="createPlugin",
        ),
        completion=completion,
        priority=priority,
        language="typescript",
    )


def _build_runner(
    root: Path,
    *,
    policy: tuple[JavascriptPluginBinding, ...] = (),
    compiler: tuple[JavascriptPluginBinding, ...] = (),
) -> JavascriptBuildPluginRunner:
    return JavascriptBuildPluginRunner(
        JavascriptPluginBindingPlan(
            policy_plugins=policy,
            compiler_plugins=compiler,
        ),
        package_root=root,
        target="node",
        workflow_id="plugin.test",
    )


@pytest.mark.parametrize(
    ("returned", "expected_code"),
    (
        (
            {"policy": {"disableCoreErrors": True}},
            "VF_PLUGIN_POLICY",
        ),
        (
            {
                "relaxations": [
                    {
                        "rule": "CORE.GRAPH.INVALID",
                        "scope": "workflow",
                        "reason": "test must not weaken Core",
                    }
                ]
            },
            "VF_PLUGIN_POLICY",
        ),
        (
            {
                "findings": [
                    {"severity": "error", "message": "policy rejected graph"}
                ]
            },
            "VF_PLUGIN_POLICY",
        ),
        (
            {"graph": {"nodes": []}},
            "VF_PLUGIN_HOOK_RESULT",
        ),
    ),
)
def test_policy_plugin_cannot_relax_or_mutate_core_contracts(
    plugin_package: Path,
    returned: dict[str, object],
    expected_code: str,
) -> None:
    binding = _binding(
        plugin_package,
        f"policy_{expected_code.lower()}",
        "policy",
        "export function createPlugin() {\n"
        "  return { extendPolicy() { return "
        + json.dumps(returned)
        + "; } };\n"
        "}\n",
    )

    with _build_runner(plugin_package, policy=(binding,)) as runner:
        with pytest.raises(JavascriptPluginError) as failure:
            runner.validate_policy({"nodes": [], "nodesets": {}})

    assert failure.value.code == expected_code


def test_policy_hook_exception_is_a_stable_plugin_failure(
    plugin_package: Path,
) -> None:
    binding = _binding(
        plugin_package,
        "policy_throw",
        "policy",
        "export function createPlugin() {\n"
        "  return { validateGraph() { throw new Error('policy exploded'); } };\n"
        "}\n",
    )

    with _build_runner(plugin_package, policy=(binding,)) as runner:
        with pytest.raises(JavascriptPluginError) as failure:
            runner.validate_policy({"nodes": [], "nodesets": {}})

    assert failure.value.code == "VF_PLUGIN_HOOK_RESULT"
    assert "validateGraph" in str(failure.value)


def test_compiler_plugin_hooks_keep_one_instance_and_order(
    plugin_package: Path,
) -> None:
    binding = _binding(
        plugin_package,
        "compiler_order",
        "compiler",
        """
export function createPlugin() {
  let phase = 0;
  return {
    beforeCompile() {
      if (phase !== 0) throw new Error("beforeCompile order");
      phase = 1;
      return { annotation: { phase: "before" } };
    },
    afterCompile() {
      if (phase !== 1) throw new Error("afterCompile order");
      phase = 2;
      return { annotation: { phase: "after" } };
    },
    validateCompiledGraph() {
      if (phase !== 2) throw new Error("validateCompiledGraph order");
      phase = 3;
      return { annotation: { phase: "validate" } };
    },
  };
}
""",
    )

    with _build_runner(plugin_package, compiler=(binding,)) as runner:
        runner.before_compile({"nodes": []})
        runner.after_compile({"nodes": []}, {"order": []})
        report = runner.report()

    assert [item["hook"] for item in report.annotations] == [
        "beforeCompile",
        "afterCompile",
        "validateCompiledGraph",
    ]
    assert [item["phase"] for item in report.annotations] == [
        "before",
        "after",
        "validate",
    ]


def test_compiler_plugin_failure_stops_later_compile_hooks(
    plugin_package: Path,
) -> None:
    binding = _binding(
        plugin_package,
        "compiler_failure",
        "compiler",
        """
export function createPlugin() {
  return {
    beforeCompile() { return { annotation: { phase: "before" } }; },
    afterCompile() { throw new Error("compiler exploded"); },
    validateCompiledGraph() {
      return { annotation: { phase: "must-not-run" } };
    },
  };
}
""",
    )

    with _build_runner(plugin_package, compiler=(binding,)) as runner:
        runner.before_compile({"nodes": []})
        with pytest.raises(JavascriptPluginError) as failure:
            runner.after_compile({"nodes": []}, {"order": []})
        report = runner.report()

    assert failure.value.code == "VF_PLUGIN_HOOK_RESULT"
    assert [item["phase"] for item in report.annotations] == ["before"]


def test_immediate_plugin_rejects_async_hook_at_static_validation(
    plugin_package: Path,
) -> None:
    binding = _binding(
        plugin_package,
        "immediate_async",
        "runtime",
        """
export function createPlugin() {
  return { async beforeRun() { await Promise.resolve(); } };
}
""",
    )

    from vibeflow.targets.javascript.build.plugin_session import (
        JavascriptPluginSession,
    )

    with JavascriptPluginSession() as session:
        with pytest.raises(JavascriptPluginError) as failure:
            session.open(
                "runtime:immediate",
                plugin=binding.to_dict(),
                package_root=plugin_package,
                target="node",
                workflow_id="plugin.test",
            )

    assert failure.value.code == "VF_PLUGIN_TYPECHECK"
    diagnostics = failure.value.details.get("diagnostics", [])
    assert any(
        item.get("code") == "VF_COMPLETION_IMMEDIATE_PROMISE"
        for item in diagnostics
        if isinstance(item, dict)
    )


@pytest.mark.parametrize(
    ("plugin_type", "source", "expected_diagnostic"),
    (
        (
            "policy",
            """
let sharedRuns = 0;
export function createPlugin() {
  return {
    validateGraph() { sharedRuns += 1; return {}; },
  };
}
""",
            "VF_MODULE_STATE",
        ),
        (
            "policy",
            """
const shared = { runs: 0 };
export function createPlugin() {
  return {
    validateGraph() { shared.runs += 1; return {}; },
  };
}
""",
            "VF_MODULE_STATE",
        ),
        (
            "compiler",
            """
type TestGlobal = typeof globalThis & { __vfCompilerLeak?: number };
export function createPlugin() {
  return {
    beforeCompile() {
      (globalThis as TestGlobal).__vfCompilerLeak = 1;
      return {};
    },
  };
}
""",
            "VF_PLUGIN_HOST_IO",
        ),
    ),
)
def test_build_time_plugin_rejects_shared_module_or_host_global_state(
    plugin_package: Path,
    plugin_type: str,
    source: str,
    expected_diagnostic: str,
) -> None:
    binding = _binding(
        plugin_package,
        f"{plugin_type}_shared_state",
        plugin_type,
        source,
    )
    runner = _build_runner(
        plugin_package,
        policy=(binding,) if plugin_type == "policy" else (),
        compiler=(binding,) if plugin_type == "compiler" else (),
    )

    with pytest.raises(JavascriptPluginError) as failure:
        with runner:
            if plugin_type == "policy":
                runner.validate_policy({"nodes": [], "nodesets": {}})
            else:
                runner.before_compile({"nodes": []})

    assert failure.value.code == "VF_PLUGIN_TYPECHECK"
    diagnostics = failure.value.details.get("diagnostics", [])
    assert expected_diagnostic in {
        item.get("code")
        for item in diagnostics
        if isinstance(item, dict)
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _install_project_plugin(
    project: _Project,
    plugin_id: str,
    source: str,
    *,
    plugin_type: str = "runtime",
    completion: str = "immediate",
) -> None:
    short_name = plugin_id.replace(".", "-")
    source_relative = f"plugins/{short_name}.ts"
    (project.root / source_relative).write_text(source, encoding="utf-8")
    _write_json(
        project.root / "manifests/plugins" / f"{short_name}.jsonc",
        {
            "kind": "plugin",
            "id": plugin_id,
            "type": plugin_type,
            "targets": ["browser", "node"],
            "priority": 50,
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "completion": completion,
                    "source": {
                        "kind": "file",
                        "ref": source_relative,
                        "export": "createPlugin",
                    },
                }
            ],
        },
    )


def _select_plugins(
    project: _Project,
    config_name: str,
    plugin_ids: list[object],
) -> Path:
    source = project.root / "configs" / config_name
    payload = _read_json(source)
    payload["plugins"] = plugin_ids
    target = project.root / "configs" / f"test-{config_name}"
    _write_json(target, payload)
    return target


def _build_project(
    project: _Project,
    config: Path,
    *,
    key: str,
    host: bool = False,
) -> object:
    return build_project_aot(
        ProjectBuildRequest(
            workspace=(
                project.host_workspace if host else project.workspace
            ),
            config=config,
            out_dir=project.root.parent / f"dist-{key}",
            target="node",
            profile="single-esm",
        )
    )


def _run_node(entry: Path, body: str, *, before_import: str = "") -> Any:
    script = f"""
import {{ pathToFileURL }} from "node:url";
{before_import}
const workflow = await import(pathToFileURL({json.dumps(str(entry))}).href);
const assert = (condition, message) => {{
  if (!condition) throw new Error(message);
}};
{body}
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _successful_runtime_audit_plugin(
    *,
    expected_nodes: tuple[str, ...],
    expected_blocks: tuple[str, ...] = ("/",),
    expected_nodesets: tuple[str, ...] = (),
) -> str:
    """Return a Runtime Plugin that audits hooks inside its call-local closure."""

    return f"""
type Summary = Readonly<{{ nodePath?: string; blockPath?: string }}>;

export function createPlugin() {{
  const expectedNodes: readonly string[] = {json.dumps(expected_nodes)};
  const expectedBlocks: readonly string[] = {json.dumps(expected_blocks)};
  const expectedNodesets: readonly string[] = {json.dumps(expected_nodesets)};
  const nodeStack: string[] = [];
  const blockStack: string[] = [];
  const nodesetStack: string[] = [];
  let nodeCursor = 0;
  let blockCursor = 0;
  let nodesetCursor = 0;
  let phase = "created";

  const check = (condition: boolean, message: string): void => {{
    if (!condition) throw new Error(message);
  }};
  const enter = (
    path: string,
    expected: readonly string[],
    cursor: number,
    stack: string[],
    kind: string,
  ): void => {{
    check(path === expected[cursor], `${{kind}} #${{cursor}} was '${{path}}'`);
    stack.push(path);
  }};
  const leave = (path: string, stack: string[], kind: string): void => {{
    check(stack.pop() === path, `${{kind}} '${{path}}' was not paired`);
  }};

  return {{
    beforeRun() {{
      check(phase === "created", "beforeRun must be first and call-local");
      phase = "running";
    }},
    beforeBlock(summary: Summary) {{
      const path = summary.blockPath ?? "";
      enter(path, expectedBlocks, blockCursor, blockStack, "block");
      blockCursor += 1;
    }},
    afterBlock(summary: Summary) {{
      leave(summary.blockPath ?? "", blockStack, "block");
    }},
    beforeNode(summary: Summary) {{
      const path = summary.nodePath ?? "";
      enter(path, expectedNodes, nodeCursor, nodeStack, "node");
      nodeCursor += 1;
    }},
    afterNode(summary: Summary) {{
      leave(summary.nodePath ?? "", nodeStack, "node");
    }},
    beforeNodeset(summary: Summary) {{
      const path = summary.nodePath ?? "";
      enter(path, expectedNodesets, nodesetCursor, nodesetStack, "nodeset");
      nodesetCursor += 1;
    }},
    afterNodeset(summary: Summary) {{
      leave(summary.nodePath ?? "", nodesetStack, "nodeset");
    }},
    afterRun() {{
      check(phase === "running", "afterRun order");
      check(nodeCursor === expectedNodes.length, "missing node hooks");
      check(blockCursor === expectedBlocks.length, "missing block hooks");
      check(nodesetCursor === expectedNodesets.length, "missing nodeset hooks");
      check(nodeStack.length === 0, "unclosed node hook");
      check(blockStack.length === 0, "unclosed block hook");
      check(nodesetStack.length === 0, "unclosed nodeset hook");
      phase = "completed";
    }},
    dispose() {{
      check(phase === "completed", "dispose ran before successful afterRun");
      phase = "disposed";
    }},
  }};
}}
"""


def test_real_build_packages_only_runtime_plugins_and_omits_planned_source(
    javascript_project: _Project,
) -> None:
    result = _build_project(
        javascript_project,
        javascript_project.root / "configs/plugins.jsonc",
        key="plugin-packaging",
    )
    manifest = _read_json(result.manifest)
    source = result.entry.read_text(encoding="utf-8")

    assert manifest["plugins"]["planned"] == ["sandbox.future_runtime"]
    assert [
        item["id"] for item in manifest["plugins"]["active"]
    ] == [
        "sandbox.policy_audit",
        "sandbox.compiler_audit",
        "sandbox.runtime_audit",
    ]
    for item in manifest["plugins"]["active"]:
        assert not Path(item["module"]).is_absolute()
        assert item["module"].startswith("plugins/")
        assert str(javascript_project.root) not in item["module"]
    assert "policy_audit" not in source
    assert "compiler_audit" not in source
    assert "sandbox.future_runtime" not in source
    assert "runtime_audit" in source


def test_real_sync_build_rejects_suspending_runtime_plugin_before_packaging(
    javascript_project: _Project,
) -> None:
    _install_project_plugin(
        javascript_project,
        "test.suspending_runtime",
        """
export function createPlugin() {
  return { async beforeRun() { await Promise.resolve(); } };
}
""",
        completion="suspend",
    )
    config = _select_plugins(
        javascript_project,
        "linear.jsonc",
        ["test.suspending_runtime"],
    )

    with pytest.raises(ProjectBuildError) as failure:
        _build_project(
            javascript_project,
            config,
            key="sync-suspend-rejected",
        )

    assert getattr(failure.value, "code", "") == (
        "VF_ENTRY_MODE_PLUGIN_SUSPEND_IN_SYNC"
    )


@pytest.mark.parametrize(
    ("source", "diagnostic_code"),
    (
        (
            """
let sharedRuns = 0;
export function createPlugin() {
  return { beforeRun() { sharedRuns += 1; } };
}
""",
            "VF_MODULE_STATE",
        ),
        (
            """
type TestGlobal = typeof globalThis & { __vfPluginLeak?: number };
export function createPlugin() {
  return {
    beforeRun() {
      (globalThis as TestGlobal).__vfPluginLeak = 1;
    },
  };
}
""",
            "VF_PLUGIN_HOST_IO",
        ),
    ),
)
def test_real_runtime_plugin_rejects_shared_module_or_host_global_state(
    javascript_project: _Project,
    source: str,
    diagnostic_code: str,
) -> None:
    _install_project_plugin(
        javascript_project,
        "test.shared_state",
        source,
    )
    config = _select_plugins(
        javascript_project,
        "linear.jsonc",
        ["test.shared_state"],
    )

    with pytest.raises(AotBuildError) as failure:
        _build_project(
            javascript_project,
            config,
            key=f"plugin-shared-state-{diagnostic_code.lower()}",
        )

    assert failure.value.code == "VF_IMPORT_POLICY"
    assert diagnostic_code in {
        item.get("code")
        for item in failure.value.diagnostics
        if isinstance(item, dict)
    }


def test_runtime_plugin_observes_run_block_node_and_nodeset_hooks(
    javascript_project: _Project,
) -> None:
    _install_project_plugin(
        javascript_project,
        "test.events",
        _successful_runtime_audit_plugin(
            expected_nodes=(
                "start",
                "arithmetic",
                "arithmetic.start",
                "arithmetic.add",
                "arithmetic.subtract",
                "arithmetic.end",
                "end",
            ),
            expected_blocks=("/", "/arithmetic"),
            expected_nodesets=("arithmetic",),
        ),
    )
    config = _select_plugins(
        javascript_project,
        "nodeset.jsonc",
        ["test.events"],
    )
    result = _build_project(
        javascript_project,
        config,
        key="runtime-hook-success",
    )

    payload = _run_node(
        result.entry,
        """
const value = workflow.runWorkflow({ x: 12, a: 5, b: 4 });
assert(value.result === 13, JSON.stringify(value));
process.stdout.write(JSON.stringify(value));
""",
    )
    assert payload == {"result": 13}


def _write_failing_nodeset_config(
    project: _Project,
    plugin_id: str,
) -> Path:
    nodeset_path = project.root / "configs/nodesets/plugin_failure.jsonc"
    _write_json(
        nodeset_path,
        {
            "type_key": "test.plugin_failure_nodeset",
            "display_name": "Plugin failure nodeset",
            "description": "Raises inside a nested block.",
            "requires": [
                {
                    "type": "sandbox.number",
                    "cardinality": "exactly_one",
                    "display_name": "Number",
                }
            ],
            "provides": [
                {
                    "key": "result",
                    "type": "sandbox.math.result",
                    "display_name": "Result",
                }
            ],
            "pipeline": {
                "inputs": [
                    {
                        "key": "x",
                        "type": "sandbox.number",
                        "display_name": "Number",
                        "required": True,
                    }
                ],
                "nodes": [
                    {"id": "start", "type_used": "sandbox.terminal", "display_name": "Nested start", "description": "Starts the failing nested block."},
                    {
                        "id": "fail",
                        "type_used": "sandbox.runtime_failure",
                        "display_name": "Raise nested failure",
                        "description": "Raises the controlled failure observed by runtime hooks.",
                        "config": {"mode": "throw"},
                    },
                    {"id": "end", "type_used": "sandbox.terminal", "display_name": "Nested end", "description": "Would end the nested block if the failure node completed."},
                ],
                "edges": [
                    {"from": "start", "to": "fail"},
                    {"from": "fail", "to": "end"},
                ],
                "outputs": [
                    {
                        "type": "sandbox.math.result",
                        "cardinality": "exactly_one",
                        "display_name": "Result",
                        "as": "result",
                    }
                ],
            },
        },
    )
    config = project.root / "configs/test-plugin-failure.jsonc"
    _write_json(
        config,
        {
            "nodeset_imports": [{"path": "nodesets/plugin_failure.jsonc"}],
            "plugins": [plugin_id],
            "pipeline": {
                "inputs": [
                    {
                        "key": "x",
                        "type": "sandbox.number",
                        "display_name": "Number",
                        "required": True,
                    }
                ],
                "nodes": [
                    {"id": "start", "type_used": "sandbox.terminal", "display_name": "Workflow start", "description": "Starts the plugin failure workflow."},
                    {
                        "id": "broken",
                        "type_used": "test.plugin_failure_nodeset",
                        "display_name": "Run failing nodeset",
                        "description": "Invokes the nested block whose controlled failure is observed.",
                    },
                    {"id": "after", "type_used": "sandbox.terminal", "display_name": "After failure", "description": "Must remain unreachable after the nested failure."},
                ],
                "edges": [
                    {"from": "start", "to": "broken"},
                    {"from": "broken", "to": "after"},
                ],
                "outputs": [
                    {
                        "type": "sandbox.math.result",
                        "cardinality": "exactly_one",
                        "display_name": "Result",
                        "as": "result",
                    }
                ],
            },
        },
    )
    return config


_FAILING_RUNTIME_AUDIT_PLUGIN = """
type Summary = Readonly<{
  nodePath?: string;
  blockPath?: string;
  code?: string;
}>;

export function createPlugin() {
  const events: string[] = [];
  let phase = "created";
  const record = (name: string, value = ""): void => {
    events.push(value ? `${name}:${value}` : name);
  };
  const check = (condition: boolean, message: string): void => {
    if (!condition) throw new Error(message);
  };
  return {
    beforeRun() { phase = "running"; record("beforeRun"); },
    beforeBlock(summary: Summary) {
      record("beforeBlock", summary.blockPath ?? "");
    },
    beforeNode(summary: Summary) {
      record("beforeNode", summary.nodePath ?? "");
    },
    afterNode(summary: Summary) {
      record("afterNode", summary.nodePath ?? "");
    },
    nodeFailed(summary: Summary) {
      record("nodeFailed", summary.nodePath ?? "");
    },
    beforeNodeset(summary: Summary) {
      record("beforeNodeset", summary.nodePath ?? "");
    },
    nodesetFailed(summary: Summary) {
      record("nodesetFailed", summary.nodePath ?? "");
    },
    blockFailed(summary: Summary) {
      record("blockFailed", summary.blockPath ?? "");
    },
    runFailed(summary: Summary) {
      record("runFailed", summary.code ?? "");
      const expected = [
        "beforeRun",
        "beforeBlock:/",
        "beforeNode:start",
        "afterNode:start",
        "beforeNode:broken",
        "beforeNodeset:broken",
        "beforeBlock:/broken",
        "beforeNode:broken.start",
        "afterNode:broken.start",
        "beforeNode:broken.fail",
        "nodeFailed:broken.fail",
        "blockFailed:/broken",
        "nodesetFailed:broken",
        "nodeFailed:broken",
        "blockFailed:/",
        "runFailed:VF_NODE_FAILED",
      ];
      check(events.length === expected.length, "failure hook count");
      check(events.every((item, index) => item === expected[index]), "failure hook order");
      phase = "failed";
    },
    dispose() {
      check(phase === "failed", "failure callbacks were incomplete");
      phase = "disposed";
    },
  };
}
"""


def test_runtime_plugin_observes_nested_failure_hooks_and_no_late_nodes(
    javascript_project: _Project,
) -> None:
    _install_project_plugin(
        javascript_project,
        "test.failure_events",
        _FAILING_RUNTIME_AUDIT_PLUGIN,
    )
    config = _write_failing_nodeset_config(
        javascript_project,
        "test.failure_events",
    )
    result = _build_project(
        javascript_project,
        config,
        key="runtime-hook-failure",
    )

    payload = _run_node(
        result.entry,
        """
let failure;
try {
  workflow.runWorkflow({ x: 7 });
} catch (error) {
  failure = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
process.stdout.write(JSON.stringify(failure));
""",
    )
    assert payload == {
        "code": "VF_NODE_FAILED",
        "nodePath": "broken.fail",
        "blockPath": "/broken",
    }


_HOOK_FAILURE_PLUGIN = """
type Summary = Readonly<{ nodePath?: string; blockPath?: string }>;

export function createPlugin() {
  const events: string[] = [];
  let phase = "created";
  const record = (value: string): void => { events.push(value); };
  const check = (condition: boolean, message: string): void => {
    if (!condition) throw new Error(message);
  };
  return {
    beforeRun() { phase = "running"; record("beforeRun"); },
    beforeBlock(summary: Summary) {
      record(`beforeBlock:${summary.blockPath ?? ""}`);
    },
    beforeNode(summary: Summary) {
      const path = summary.nodePath ?? "";
      record(`beforeNode:${path}`);
      if (path === "add") throw new Error("runtime hook exploded");
    },
    afterNode(summary: Summary) {
      record(`afterNode:${summary.nodePath ?? ""}`);
    },
    blockFailed(summary: Summary) {
      record(`blockFailed:${summary.blockPath ?? ""}`);
      check(events.join("|") === [
        "beforeRun",
        "beforeBlock:/",
        "beforeNode:start",
        "afterNode:start",
        "beforeNode:add",
        "blockFailed:/",
      ].join("|"), "hook failure did not stop normal node scheduling");
    },
    runFailed() {
      record("runFailed");
      check(events[events.length - 2] === "blockFailed:/", "blockFailed order");
      phase = "failed";
    },
    dispose() {
      check(phase === "failed", "runFailed must precede dispose");
      phase = "disposed";
    },
  };
}
"""


def test_runtime_hook_failure_uses_stable_error_and_failure_callbacks(
    javascript_project: _Project,
) -> None:
    _install_project_plugin(
        javascript_project,
        "test.hook_failure",
        _HOOK_FAILURE_PLUGIN,
    )
    config = _select_plugins(
        javascript_project,
        "linear.jsonc",
        ["test.hook_failure"],
    )
    result = _build_project(
        javascript_project,
        config,
        key="runtime-hook-own-failure",
    )

    payload = _run_node(
        result.entry,
        """
let failure;
try {
  workflow.runWorkflow({ x: 1, a: 2, b: 3 });
} catch (error) {
  failure = { code: error.code, cause: error.cause?.message };
}
process.stdout.write(JSON.stringify({
  failure,
}));
""",
    )

    assert payload["failure"]["code"] == "VF_RUNTIME_PLUGIN_HOOK"
    assert payload["failure"]["cause"] == "runtime hook exploded"


def test_runtime_plugin_instances_are_recreated_for_repeated_calls(
    javascript_project: _Project,
) -> None:
    _install_project_plugin(
        javascript_project,
        "test.repeat_events",
        _successful_runtime_audit_plugin(
            expected_nodes=("start", "add", "subtract", "end"),
        ),
    )
    config = _select_plugins(
        javascript_project,
        "linear.jsonc",
        ["test.repeat_events"],
    )
    result = _build_project(
        javascript_project,
        config,
        key="runtime-repeat",
    )

    payload = _run_node(
        result.entry,
        """
const first = workflow.runWorkflow({ x: 10, a: 8, b: 3 });
const second = workflow.runWorkflow({ x: 7, a: 2, b: 4 });
process.stdout.write(JSON.stringify({
  values: [first.result, second.result],
}));
""",
    )

    assert payload["values"] == [15, 5]


_SUSPENDING_ISOLATION_PLUGIN = """
type Summary = Readonly<{ nodePath?: string; blockPath?: string }>;

export function createPlugin() {
  const expectedNodes = ["start", "add", "subtract", "end"];
  const nodeStack: string[] = [];
  let nodeCursor = 0;
  let phase = "created";
  const check = (condition: boolean, message: string): void => {
    if (!condition) throw new Error(message);
  };
  return {
    async beforeRun() {
      check(phase === "created", "runtime plugin instance leaked across calls");
      phase = "running";
      await Promise.resolve();
    },
    async beforeBlock(summary: Summary) {
      await Promise.resolve();
      check(summary.blockPath === "/", "unexpected block path");
    },
    async beforeNode(summary: Summary) {
      await Promise.resolve();
      const path = summary.nodePath ?? "";
      check(path === expectedNodes[nodeCursor], `unexpected node #${nodeCursor}`);
      nodeCursor += 1;
      nodeStack.push(path);
    },
    async afterNode(summary: Summary) {
      await Promise.resolve();
      check(nodeStack.pop() === summary.nodePath, "node hooks were not paired");
    },
    async afterBlock(summary: Summary) {
      await Promise.resolve();
      check(summary.blockPath === "/", "unexpected block completion");
    },
    async afterRun() {
      await Promise.resolve();
      check(phase === "running", "afterRun order");
      check(nodeCursor === expectedNodes.length, "missing node hooks");
      check(nodeStack.length === 0, "unclosed node hooks");
      phase = "completed";
    },
    async dispose() {
      await Promise.resolve();
      check(phase === "completed", "dispose before successful completion");
      phase = "disposed";
    },
  };
}
"""


def test_suspending_runtime_plugins_are_isolated_across_concurrent_calls(
    javascript_project: _Project,
) -> None:
    _install_project_plugin(
        javascript_project,
        "test.concurrent_runtime",
        _SUSPENDING_ISOLATION_PLUGIN,
        completion="suspend",
    )
    config = _select_plugins(
        javascript_project,
        "linear.jsonc",
        ["test.concurrent_runtime"],
    )
    payload = _read_json(config)
    payload["pipeline"]["entry_mode"] = "async"
    _write_json(config, payload)
    result = _build_project(
        javascript_project,
        config,
        key="runtime-concurrent",
    )

    output = _run_node(
        result.entry,
        """
const values = await Promise.all([
  workflow.runWorkflowAsync({ x: 1, a: 2, b: 1 }),
  workflow.runWorkflowAsync({ x: 20, a: 4, b: 3 }),
  workflow.runWorkflowAsync({ x: -5, a: 9, b: 2 }),
]);
process.stdout.write(JSON.stringify({
  values: values.map(item => item.result),
}));
""",
    )

    assert output["values"] == [2, 21, 2]


def test_runtime_plugin_and_host_extension_share_lifecycle_without_coupling(
    javascript_project: _Project,
) -> None:
    _install_project_plugin(
        javascript_project,
        "test.host_runtime",
        _successful_runtime_audit_plugin(
            expected_nodes=("start", "double", "end"),
        ),
    )
    host_project = _read_json(
        javascript_project.root / "vibeflow_host_project.jsonc"
    )
    host_project["descriptors"]["plugins"] = ["manifests/plugins"]
    _write_json(
        javascript_project.root / "vibeflow_host_project.jsonc",
        host_project,
    )
    config = _select_plugins(
        javascript_project,
        "host_extension.jsonc",
        ["test.host_runtime"],
    )
    result = _build_project(
        javascript_project,
        config,
        key="host-and-runtime",
        host=True,
    )

    payload = _run_node(
        result.entry,
        """
const afterImport = {
  host: [...globalThis.__vibeflowSandboxHostCalls],
};
const host = workflow.createWorkflowHost();
await host.start();
const value = host.runWorkflow({ x: 5 });
await host.stop();
process.stdout.write(JSON.stringify({
  afterImport,
  value,
  hostCalls: globalThis.__vibeflowSandboxHostCalls,
}));
""",
        before_import="globalThis.__vibeflowSandboxHostCalls = [];",
    )

    assert payload["afterImport"] == {"host": []}
    assert payload["value"] == {"result": 10}
    assert payload["hostCalls"] == ["create", "start", "stop"]
