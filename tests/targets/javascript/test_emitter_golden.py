"""Frozen contracts for the canonical JavaScript target."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from tests.targets.javascript.test_aot_core import (
    _fake_driver,
    _linear_plan,
    _node,
    _provider,
    _requirement,
    _ordinary_worker,
)
from vibeflow.targets.javascript.build import BuildRequest, build_aot
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
from vibeflow.targets.javascript.frontend.errors import AotPlanError
from tests.targets.javascript.aot_fixtures import emit_fixture, fixture_build_request, view_fixture


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _middle(
    *,
    completion: str = "immediate",
) -> dict[str, object]:
    return _node(
        "calculate",
        "calculate",
        requires=[_requirement("number")],
        provides=[_provider("out", "answer")],
        completion=completion,
    )


def _sync_plan() -> dict[str, object]:
    return _linear_plan(middle=_middle())


def _async_plan() -> dict[str, object]:
    return _linear_plan(
        middle=_middle(completion="suspend"),
        entry_mode="async",
    )


def _nested_plan() -> dict[str, object]:
    child = _linear_plan(middle=_middle())
    child["workflow_id"] = "baseline.nested.child"
    return _linear_plan(
        middle={
            **_node(
                "composite",
                "composite",
                requires=[_requirement("number")],
                provides=[_provider("out", "answer")],
            ),
            "is_nodeset": True,
            "subplan": child,
        }
    )


def _loop_plan(max_iterations: int | None) -> dict[str, object]:
    body = _linear_plan(middle=_middle())
    body["workflow_id"] = "baseline.loop.body"
    return _linear_plan(
        middle={
            **_node(
                "repeat",
                "repeat",
                requires=[_requirement("number")],
                provides=[_provider("out", "answer")],
            ),
            "is_loop": True,
            "subplan": body,
            "loop": {
                "max_iterations": max_iterations,
                "stop_after": 2,
                "carry": [
                    {"from": "number", "as": "number", "update": "answer"}
                ],
                "outputs": [{"from": "number", "as": "out"}],
            },
        }
    )


def _deferred_plan() -> dict[str, object]:
    return _linear_plan(
        middle=_ordinary_worker("calculate", "calculate", requires=[_requirement("number")],
                             provides=[_provider("out", "answer")]),
        entry_mode="async",
    )


def _detached_plan() -> dict[str, object]:
    return {
        "abi_version": "vibeflow.workflow.v8",
        "workflow_id": "baseline.detached",
        "entry_mode": "async",
        "inputs": [],
        "outputs": [],
        "nodes": [
            _node("start", "start", terminal=True),
            _ordinary_worker("audit", "audit"),
            _node("end", "end", terminal=True),
        ],
        "routes": [
            {"source": "start", "target": "audit"},
            {"source": "audit", "target": "end"},
        ],
        "order": ["start", "audit", "end"],
        "max_steps": 10,
    }


def _port_plan() -> dict[str, object]:
    receive = _node(
        "receive",
        "receive",
        provides=[_provider("value", "port.value")],
        completion="suspend",
        capabilities=[{"id": "vibeflow.port", "operations": ["receive"]}],
        io_operation="receive",
        io_port="baseline.in",
        implementation=None,
    )
    receive["type_used"] = "vibeflow.io"
    send = _node(
        "send",
        "send",
        requires=[_requirement("port.value")],
        capabilities=[{"id": "vibeflow.port", "operations": ["send"]}],
        io_operation="send",
        io_port="baseline.out",
        implementation=None,
    )
    send["type_used"] = "vibeflow.io"
    return {
        "abi_version": "vibeflow.workflow.v8",
        "workflow_id": "baseline.port",
        "entry_mode": "async",
        "inputs": [],
        "outputs": [],
        "nodes": [_node("start", "start", terminal=True), receive, send],
        "routes": [
            {"source": "start", "target": "receive"},
            {"source": "receive", "target": "send"},
        ],
        "order": ["start", "receive", "send"],
        "max_steps": 10,
        "capabilities": [
            {
                "id": "vibeflow.port",
                "operations": {
                    "receive": {
                        "input_type": "vibeflow.port.receive.request",
                        "output_type": "vibeflow.port.receive.result",
                        "completion": "suspend",
                    },
                    "send": {
                        "input_type": "vibeflow.port.send.request",
                        "output_type": "vibeflow.port.send.result",
                        "completion": "immediate",
                    },
                },
            }
        ],
    }


HOST_EXTENSIONS = (
    {
        "id": "baseline.host",
        "module": "./host.mjs",
        "export": "createHostExtension",
        "dependencies": [],
        "provides": ["baseline.clock"],
        "config": {"mode": "frozen"},
    },
)


def _emission_cases() -> dict[str, tuple[dict[str, object], tuple[dict, ...]]]:
    return {
        "sync": (_sync_plan(), ()),
        "async": (_async_plan(), ()),
        "nested_nodeset": (_nested_plan(), ()),
        "bounded_loop": (_loop_plan(4), ()),
        "unbounded_loop": (_loop_plan(None), ()),
        "deferred": (_deferred_plan(), ()),
        "detached": (_detached_plan(), ()),
        "port": (_port_plan(), ()),
        "host_extension": (_sync_plan(), HOST_EXTENSIONS),
    }


# These hashes intentionally freeze generated source formatting as well as its
# semantic plan.  Update them only after reviewing an intentional ABI change.
# Workflow ABI v8 uses only ordinary graph calls and explicit routes.
EMISSION_GOLDENS = {'async': ('fe68b2431807b8637e62e52a8716491275f194ec212737c4d99500076b2a58e4',
           '742f4b399ddd9748b718454000b36adba1063c23733c72aef5b5cd13fd22f880',
           '472bcffb0d29d7605febd305b0ae52b293df6aa54ef24c63dcd39fb24eaf7c5e'),
 'bounded_loop': ('f8602c3fbe3090f8b1ecd42be1d0ea1d21b77e14af0bf3f786377da9030e2ee8',
                  '2873b3ce54254ebee51701947852fd5bf26ff3fd5d4cd8634baf0fe3515684fc',
                  '3448492c3a639921e0b9ec4114c68bf94189e883fce635ab5f9c18aaa938dd62'),
 'deferred': ('fe68b2431807b8637e62e52a8716491275f194ec212737c4d99500076b2a58e4',
              '742f4b399ddd9748b718454000b36adba1063c23733c72aef5b5cd13fd22f880',
              '472bcffb0d29d7605febd305b0ae52b293df6aa54ef24c63dcd39fb24eaf7c5e'),
 'detached': ('6765da5627fcd086b92ca50c6aa51b143fe1ff759217155a0bba82282571104f',
              '931f71c1a6f98d4c06ca1d11231f68fa8e780e24c080db6488f350ab5480ec40',
              '4244f051585190317d83f89203f61795300a4c22668370a4ae9631ed19b70c66'),
 'host_extension': ('dfef2309d3738c3b145f46993eca3662aff540d0d30627911ea904cb9d6580b1',
                    '7d42f7e7aa8acf3bab7e23816bd025e45f65c766352a4f9ea564c920c58f723f',
                    'e947c6f040dbcbf002e3853cc10341364e6c8e3b3999620b4e4cbe311bd258ba'),
 'nested_nodeset': ('fcc1bea37425dd14f5141bf36dc9b42f22f0beb4710eaadee6c00ddb77f55dd2',
                    '2873b3ce54254ebee51701947852fd5bf26ff3fd5d4cd8634baf0fe3515684fc',
                    '1471d70ea42dd53e17e6c6959a93d11448ad1838e8fa779efc31a197f8879c05'),
 'port': ('4927778d36fdb72101accaae193dc21576eb4f0a372262edd35e37f9137f0005',
          '3b7386483d8723d3fcac187b1ad052d370af5c763086fee71a3c47043a8f0666',
          'dfbd068bf9622c4aedeba46023ec1518bbc0d4b75e71ca4d443b60b47a68fa34'),
 'sync': ('2fd6c778488149cf3707eb6d7eb1ce3c8223953e90c7e8855c5008b11abdb1f9',
          '2873b3ce54254ebee51701947852fd5bf26ff3fd5d4cd8634baf0fe3515684fc',
          'e947c6f040dbcbf002e3853cc10341364e6c8e3b3999620b4e4cbe311bd258ba'),
 'unbounded_loop': ('11591c4a75bcf60e09526eb03659f3c4acf0dae9cfb60a494ee51abbff7d9715',
                    '2873b3ce54254ebee51701947852fd5bf26ff3fd5d4cd8634baf0fe3515684fc',
                    '8bddb96ae82e67c341c91d5391bb9794d6a9b74dc344ef2c4ce832be9da24d06')}

NORMALIZED_WORKFLOW_SHA256 = 'cec2288b59b9ff67c1d609564b1ea4215189700a6ceb526cc73233f4d3669972'

def test_canonical_bound_view_payload_is_frozen() -> None:
    workflow = view_fixture(_sync_plan())
    payload = workflow.to_dict()

    assert _sha256_text(_canonical_json(payload)) == NORMALIZED_WORKFLOW_SHA256
    assert tuple(payload) == (
        "abi_version",
        "workflow_id",
        "inputs",
        "outputs",
        "nodes",
        "routes",
        "order",
        "entries",
        "max_steps",
        "schemas",
        "capabilities",
        "entry_mode",
    )
    assert payload["entries"] == ["start"]
    assert payload["entry_mode"] == "sync"
    assert [node["id"] for node in payload["nodes"]] == [
        "start",
        "calculate",
        "end",
    ]
    assert [
        (
            node["completion"],
            node["schedule"],
            node["executor"],
        )
        for node in payload["nodes"]
    ] == [("immediate", "inline", "current")] * 3


@pytest.mark.parametrize("case_name", tuple(EMISSION_GOLDENS))
def test_representative_emission_source_declarations_and_plan_hash_are_frozen(
    case_name: str,
) -> None:
    plan, host_extensions = _emission_cases()[case_name]
    emitted = emit_fixture(
        plan,
        host_extensions=host_extensions,
    )
    actual = (
        _sha256_text(emitted.source),
        _sha256_text(emitted.declarations),
        emitted.plan_sha256,
    )
    assert actual == EMISSION_GOLDENS[case_name]
    if plan.get("entry_mode", "sync") == "async":
        assert "export async function runWorkflowAsync(" in emitted.source
        assert "runWorkflowAsync(" in emitted.declarations
        assert "export function runWorkflow(" not in emitted.source
    else:
        assert "export function runWorkflow(" in emitted.source
        assert "runWorkflow(" in emitted.declarations
        assert "export async function runWorkflowAsync(" not in emitted.source
    if case_name == "host_extension":
        assert emitted.host_extensions == ("baseline.host",)
        assert "export function createWorkflowHost(" in emitted.source
        assert "VF_HOST_EXTENSION_START" in emitted.source
        assert "createWorkflowHost(" in emitted.declarations


@pytest.mark.parametrize(
    ("case_name", "mutate", "code", "message"),
    [
        (
            "sync_suspend",
            lambda plan: plan.update(entry_mode="sync"),
            "VF_ENTRY_MODE_SUSPEND_IN_SYNC",
            "sync workflow contains suspending node 'calculate'",
        ),
        (
            "port_missing_name",
            lambda plan: plan["nodes"][1].update(io_port=""),
            "VF_IO_PORT",
            "vibeflow.io node 'receive' must declare a port",
        ),
        (
            "port_bad_send_contract",
            lambda plan: plan["nodes"][2].update(
                provides=[_provider("unexpected", "port.value")]
            ),
            "VF_IO_CONTRACT",
            "vibeflow.io send node 'send' requires one exactly_one input",
        ),
    ],
)
def test_sync_completion_and_port_diagnostics_are_frozen(
    case_name: str,
    mutate,
    code: str,
    message: str,
) -> None:
    source = {
        "sync_suspend": _async_plan,
        "port_missing_name": _port_plan,
        "port_bad_send_contract": _port_plan,
    }[case_name]
    plan = deepcopy(source())
    mutate(plan)

    with pytest.raises(AotPlanError) as caught:
        view_fixture(plan)
    assert caught.value.code == code
    assert message in str(caught.value)


def _write_build_project(project: Path) -> None:
    project.mkdir()
    (project / "nodes.mjs").write_text(
        "export function start() { return {}; }\n"
        "export function calculate(inputs) { "
        "return { out: inputs.number.value }; }\n"
        "export function end() { return {}; }\n",
        encoding="utf-8",
    )
    (project / "host.mjs").write_text(
        "export function createHostExtension() { "
        "return { start() {}, stop() {}, capabilities: { "
        "'baseline.clock': {} } }; }\n",
        encoding="utf-8",
    )
    (project / "app.ts").write_text(
        'import { runWorkflow } from "@vibeflow/workflow";\n'
        "void runWorkflow;\n",
        encoding="utf-8",
    )
    (project / "index.template.html").write_text(
        "<!doctype html><body><!-- VIBEFLOW_APP_ENTRY --></body>\n",
        encoding="utf-8",
    )


def _normalized_driver_request(value: dict[str, object]) -> dict[str, object]:
    policy = value["importPolicy"]
    assert isinstance(policy, dict)
    return {
        "target": value["target"],
        "profile": value["profile"],
        "workflowEntry": Path(str(value["workflowEntry"])).name,
        "outDir": Path(str(value["outDir"])).name,
        "entryName": value["entryName"],
        "sourcemap": value["sourcemap"],
        "external": value["external"],
        "typecheckFiles": [
            Path(str(item)).name for item in value["typecheckFiles"]
        ],
        "appEntry": (
            Path(str(value["appEntry"])).name
            if "appEntry" in value
            else None
        ),
        "importPolicy": {
            "owners": [
                {
                    **{key: item[key] for key in ("kind", "id")},
                    "path": Path(str(item["path"])).name,
                }
                for item in policy["owners"]
            ],
            "nodeBaseLibs": policy["nodeBaseLibs"],
            "baseLibDependencies": policy["baseLibDependencies"],
            "hostExtensionDependencies": policy[
                "hostExtensionDependencies"
            ],
            "allowedExternalPackages": policy[
                "allowedExternalPackages"
            ],
        },
    }


PROFILE_GOLDENS = {
    "esm-module": {
        "target": "node",
        "entry": "workflow.js",
        "files": ["workflow.d.ts", "workflow.js", "workflow.js.map"],
        "typecheckFiles": ["node-contract-check.ts"],
        "appEntry": None,
    },
    "single-esm": {
        "target": "node",
        "entry": "index.js",
        "files": ["index.d.ts", "index.js", "index.js.map"],
        "typecheckFiles": ["node-contract-check.ts"],
        "appEntry": None,
    },
    "web-app": {
        "target": "browser",
        "entry": "index.html",
        "files": ["index.html", "index.js", "index.js.map", "workflow.d.ts"],
        "typecheckFiles": [
            "node-contract-check.ts",
            "app.ts",
            "vibeflow-workflow.d.ts",
        ],
        "appEntry": "app.ts",
    },
}


@pytest.mark.parametrize("profile", tuple(PROFILE_GOLDENS))
def test_profile_manifest_and_driver_request_migration_fields_are_frozen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
) -> None:
    import vibeflow.targets.javascript.build.builder as builder_module

    project = tmp_path / "project"
    _write_build_project(project)
    captured: list[dict[str, object]] = []

    def capture_driver(request, *, package_root, node_command="node"):
        captured.append(deepcopy(request))
        return _fake_driver(
            request,
            package_root=package_root,
            node_command=node_command,
        )

    monkeypatch.setattr(builder_module, "run_build_driver", capture_driver)
    expected = PROFILE_GOLDENS[profile]
    result = build_aot(
        fixture_build_request(
            plan=_sync_plan(),
            project_root=project,
            package_root=project,
            out_dir=tmp_path / f"dist-{profile}",
            target=str(expected["target"]),
            profile=profile,
            external_packages=("z-package", "a-package", "z-package"),
            import_policy={
                "owners": [
                    {
                        "path": str(project / "nodes.mjs"),
                        "kind": "node",
                        "id": "baseline.nodes",
                    }
                ],
                "node_base_libs": {"baseline.nodes": ["baseline.math"]},
                "base_lib_dependencies": {"baseline.math": []},
                "host_extension_dependencies": {"baseline.host": []},
                "allowed_external_packages": ["policy-package"],
            },
            host_extensions=HOST_EXTENSIONS,
            html_template=(
                project / "index.template.html"
                if profile == "web-app"
                else None
            ),
            app_entry=project / "app.ts" if profile == "web-app" else None,
        )
    )
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    driver = _normalized_driver_request(captured[0])

    assert {
        "format": manifest["format"],
        "abi_version": manifest["abi_version"],
        "project_target": manifest["project_target"],
        "workflow_id": manifest["workflow_id"],
        "entry_mode": manifest["entry_mode"],
        "target": manifest["target_metadata"]["target"],
        "profile": manifest["target_metadata"]["profile"],
        "entry": manifest["entry"],
        "external_packages": manifest["target_metadata"]["external_packages"],
        "host_extensions": manifest["target_metadata"]["host_extensions"],
        "files": sorted(manifest["files"]),
    } == {
        "format": "vibeflow.aot-build.v3",
        "abi_version": "vibeflow.workflow.v8",
        "project_target": "javascript",
        "workflow_id": "test.workflow",
        "entry_mode": "sync",
        "target": expected["target"],
        "profile": profile,
        "entry": expected["entry"],
        "external_packages": ["a-package", "z-package"],
        "host_extensions": ["baseline.host"],
        "files": expected["files"],
    }
    assert driver == {
        "target": expected["target"],
        "profile": profile,
        "workflowEntry": "workflow-entry.mjs",
        "outDir": "dist",
        "entryName": "workflow.js" if profile == "esm-module" else "index.js",
        "sourcemap": "external",
        "external": ["a-package", "z-package"],
        "typecheckFiles": expected["typecheckFiles"],
        "appEntry": expected["appEntry"],
        "importPolicy": {
            "owners": [
                {
                    "kind": "node",
                    "id": "baseline.nodes",
                    "path": "nodes.mjs",
                },
                {
                    "kind": "generated",
                    "id": "vibeflow.aot.generated",
                    "path": "source",
                },
            ],
            "nodeBaseLibs": {"baseline.nodes": ["baseline.math"]},
            "baseLibDependencies": {"baseline.math": []},
            "hostExtensionDependencies": {"baseline.host": []},
            "allowedExternalPackages": [
                "a-package",
                "policy-package",
                "z-package",
            ],
        },
    }
    assert len(manifest["plan_sha256"]) == 64
    assert set(manifest["plan_sha256"]) <= set("0123456789abcdef")


def test_importing_emitted_module_does_not_run_workflow_or_host_extension(
    tmp_path: Path,
) -> None:
    emitted = emit_fixture(
        _sync_plan(),
        host_extensions=HOST_EXTENSIONS,
    )
    (tmp_path / "workflow.mjs").write_text(emitted.source, encoding="utf-8")
    (tmp_path / "nodes.mjs").write_text(
        "export function start() { globalThis.events.push('start'); return {}; }\n"
        "export function calculate() { "
        "globalThis.events.push('calculate'); return { out: 1 }; }\n"
        "export function end() { globalThis.events.push('end'); return {}; }\n",
        encoding="utf-8",
    )
    (tmp_path / "host.mjs").write_text(
        "export function createHostExtension() {\n"
        "  globalThis.events.push('create');\n"
        "  return {\n"
        "    capabilities: { 'baseline.clock': {} },\n"
        "    start() { globalThis.events.push('start-host'); },\n"
        "    stop() { globalThis.events.push('stop-host'); },\n"
        "  };\n"
        "}\n",
        encoding="utf-8",
    )
    script = (
        "import { pathToFileURL } from 'node:url';\n"
        "globalThis.events = [];\n"
        f"const module = await import(pathToFileURL({json.dumps(str(tmp_path / 'workflow.mjs'))}).href);\n"
        "process.stdout.write(JSON.stringify({\n"
        "  events: globalThis.events,\n"
        "  exports: Object.keys(module).sort(),\n"
        "}));\n"
    )

    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "events": [],
            "exports": [
                "VIBEFLOW_PLUGIN_ABI",
                "VIBEFLOW_WORKFLOW_ABI",
            "VibeFlowWorkflowError",
            "createWorkflowHost",
            "runWorkflow",
        ],
    }
