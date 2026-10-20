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
        "abi_version": "vibeflow.workflow.v9",
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
        params={"port":"baseline.in"},
    )
    send = _node(
        "send",
        "send",
        requires=[_requirement("port.value")],
        capabilities=[{"id": "vibeflow.port", "operations": ["send"]}],
        params={"port":"baseline.out"},
    )
    return {
        "abi_version": "vibeflow.workflow.v9",
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
# Workflow ABI v9 stores named entry membership and ordinary SDK port calls.
EMISSION_GOLDENS = {'async': ('54cc5732d8bf38f9baf7f780e3669e43ffa77c77e759728da20c042c8f06d4bb',
           '3609d1048dbf04250b39adf6e71c4ed720902e07cf8d4227ef1afbf5cc38268a',
           '3fc195eba930b4218d5526c1079b151afd7303197cc8036a0e712173a359d163'),
 'bounded_loop': ('d61b91831d9d186814ea147c6e1a9a6a45a23d21488e2ba2a4afe3b26b62c6d9',
                  'fafd35d8aaad20a6b93f60cc07b56733dcd9c2b97d82705bbb09e911257ac0b6',
                  '16f884b5cb019390c2edb6cf40d1e6a512fd8493ea2d83bd90090771ef6460aa'),
 'deferred': ('54cc5732d8bf38f9baf7f780e3669e43ffa77c77e759728da20c042c8f06d4bb',
              '3609d1048dbf04250b39adf6e71c4ed720902e07cf8d4227ef1afbf5cc38268a',
              '3fc195eba930b4218d5526c1079b151afd7303197cc8036a0e712173a359d163'),
 'detached': ('19f4d9311031ad54f06f622e5806c4963f4062bab68b17f741459cfd4ad02df2',
              '041a9e90a3276e23b8198e37d2ceb17920af9d8b637068dd94b17fe28d5b2c6f',
              'a262f296fbdb835048695a98dcfae53965c371365ea24f916f93985dffea035b'),
 'host_extension': ('bcc72aec7d0f44ca0c7c3ceea8f7d3279d833ba737373d502b7e77b782aa2e5c',
                    '032947fd4dc0da9b3c90e312b2792fe5902b1207ce525ae9d01a10d7d4427b9b',
                    'c8d97ac6cb6e78904e1aeeb1a1c72b0021a2f544321b3b0d7ba72a3591169710'),
 'nested_nodeset': ('4df1bd2377bbf7ac00968efe77387fe3c5ac71c351f92b3985a8c34d71ce43b6',
                    'fafd35d8aaad20a6b93f60cc07b56733dcd9c2b97d82705bbb09e911257ac0b6',
                    '3dda71b257e630d2bf56649c26835c946c3983de527f5436612249d889d98006'),
 'port': ('b07a8a57f0569edc0939d6352b912beae3d19cdecf0073de781b8202431d47ed',
          '8a3aab72be9d49f43d54f10e4c5dacc92496b12315fdd9ddfb3cf8c8b2c59da4',
          '792f0e3605dc72a7e848938a6456f73444a8b10f3e0f4d50a06c5747929e1f88'),
 'sync': ('0986c967595dd9e266da64fcf3ee35513fa8802f7e80012a73a2c5642da1ce4b',
          'fafd35d8aaad20a6b93f60cc07b56733dcd9c2b97d82705bbb09e911257ac0b6',
          'c8d97ac6cb6e78904e1aeeb1a1c72b0021a2f544321b3b0d7ba72a3591169710'),
 'unbounded_loop': ('7d07d8fd3c49b2a506ce6751d38157814467788aec854134a7776d29cf936c5c',
                    'fafd35d8aaad20a6b93f60cc07b56733dcd9c2b97d82705bbb09e911257ac0b6',
                    'fb9903f3a699c4ad071dcccb014ccae13e21d5586a0e99180a2f2539413fac73')}

NORMALIZED_WORKFLOW_SHA256 = '9f750f8031aaae4d9d9564e6575617f5fd56a7f64ff65e9b474e723b38b4aaa1'

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
    ],
)
def test_sync_completion_diagnostics_are_frozen(
    case_name: str,
    mutate,
    code: str,
    message: str,
) -> None:
    source = {
        "sync_suspend": _async_plan,
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
        "abi_version": "vibeflow.workflow.v9",
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
