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
)
from vibeflow.targets.javascript.build import BuildRequest, build_aot
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
from vibeflow.targets.javascript.frontend.model import (
    AotPlanError,
    WorkflowSpec,
    normalize_workflow_plan,
)


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
    async_mode: str = "",
    result_key: str = "",
) -> dict[str, object]:
    return _node(
        "calculate",
        "calculate",
        requires=[_requirement("number")],
        provides=[_provider("out", "answer")],
        completion=completion,
        async_mode=async_mode,
        result_key=result_key,
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
        middle=_middle(
            completion="suspend",
            async_mode="result_key",
            result_key="out",
        ),
        entry_mode="async",
    )


def _detached_plan() -> dict[str, object]:
    return {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "baseline.detached",
        "entry_mode": "async",
        "inputs": [],
        "outputs": [],
        "nodes": [
            _node("start", "start", terminal=True),
            _node(
                "audit",
                "audit",
                completion="suspend",
                async_mode="detached",
            ),
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
        "abi_version": "vibeflow.workflow.v2",
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
EMISSION_GOLDENS = {
    "sync": (
        "db4efe92715e7487d0c43ed3c18fd751dabed1cebcd60946c1376c373ef3d859",
        "dd0f3dc4d13cf8c3d29cdbfca7fc91afb0110d0ca1427d85b1e7c72e2c67c83c",
        "647cc1392cf87d016ad27e19beff02d6d069ccda1e4c92aee20b29961c55d125",
    ),
    "async": (
        "5994b3ddeb92a687e7aae0c1006699b868bd69775434b722472f455d71467da7",
        "d0586ad8be6682d31a6db68ac9d6b0695b7642c1e3840feee6dc560e41840c77",
        "6c8130e53e36301ca4681efc508589012d2f1395605d4f68e979b45f4636bc0d",
    ),
    "nested_nodeset": (
        "0d2cedeeeeb2962c7e3d93677813c84f4e8e102106495b64feba49d300ad784e",
        "dd0f3dc4d13cf8c3d29cdbfca7fc91afb0110d0ca1427d85b1e7c72e2c67c83c",
        "1890c50bbdbe71dd80e2d4e955a272e291dd53a20fd770639104601c570d117f",
    ),
    "bounded_loop": (
        "f7038af61285d77f524692dfac611c7b2d5ba8ec4dd628a19ac337b33627ab0c",
        "dd0f3dc4d13cf8c3d29cdbfca7fc91afb0110d0ca1427d85b1e7c72e2c67c83c",
        "1edb9e76ca6269131b74403b50c0ab2cc2d39376ef31b20d95a4ac27705694b5",
    ),
    "unbounded_loop": (
        "2e757f2abb9c00a770319892172a973d0db62159eafa43b9d65af33e1edb07ec",
        "dd0f3dc4d13cf8c3d29cdbfca7fc91afb0110d0ca1427d85b1e7c72e2c67c83c",
        "8b57e73e80d4f7b8ef8e29db7150407805ae481b42591c28b5419b53cae19792",
    ),
    "deferred": (
        "16a8725269c2d74fccfa6e39be1a68c137116fa41c5159f30eab686415a5157e",
        "d0586ad8be6682d31a6db68ac9d6b0695b7642c1e3840feee6dc560e41840c77",
        "f20b53bd8a256a618467ec6b1afcbd02e391543b270740992b6eeb3a92e723a8",
    ),
    "detached": (
        "f42ec0bbab2f9b2e702eaebd8ed69a6480a3f9dc9bcad5c753f4f0142fc1ffc4",
        "34f0265fc5a4ba8a200b257332b4d7370c39712c2e62ebdbd07403444e0c59d7",
        "7c966aceb1938e165458a653735babad706a2f264715f79a8be389bf3bfe577e",
    ),
    "port": (
        "af59e5ee0f4bef6b3ba3285f7ae235302cd7963a05d607d9b77dcdef6cabd683",
        "09d1eeaa26188ad47fde7a222b5ecef7dfaf0ff05cf3c5a952e4a914defa3ca5",
        "b0e5cc9456776a74ac0de29b68c3fa92d4051326f745676fa29a919a3b36c815",
    ),
    "host_extension": (
        "9c7c09f0ae0b6d7f95629fdc7a6673a4dc7b397ae9042a39be730828976a8cf7",
        "9a007aa76be0f7b1b45216b8f479dac7ce383296b940071e3c99647695597e31",
        "647cc1392cf87d016ad27e19beff02d6d069ccda1e4c92aee20b29961c55d125",
    ),
}

NORMALIZED_WORKFLOW_SHA256 = (
    "b91f35ba85fd628128c3f1c8072fc8897f38084b3c175773ca46585b617f4587"
)


def test_workflow_spec_normalized_to_dict_is_frozen() -> None:
    workflow = WorkflowSpec.from_portable(_sync_plan())
    assert normalize_workflow_plan(workflow) is workflow
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
        "tasks",
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
    emitted = emit_workflow_module(
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
            "sync_deferred",
            lambda plan: (
                plan.update(entry_mode="sync"),
                plan["nodes"][1].update(completion="immediate"),
            ),
            "VF_ENTRY_MODE_TASK_IN_SYNC",
            "sync workflow contains deferred task 'calculate'",
        ),
        (
            "sync_detached",
            lambda plan: (
                plan.update(entry_mode="sync"),
                plan["nodes"][1].update(completion="immediate"),
            ),
            "VF_ENTRY_MODE_TASK_IN_SYNC",
            "sync workflow contains detached task 'audit'",
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
def test_sync_task_and_port_diagnostics_are_frozen(
    case_name: str,
    mutate,
    code: str,
    message: str,
) -> None:
    source = {
        "sync_suspend": _async_plan,
        "sync_deferred": _deferred_plan,
        "sync_detached": _detached_plan,
        "port_missing_name": _port_plan,
        "port_bad_send_contract": _port_plan,
    }[case_name]
    plan = deepcopy(source())
    mutate(plan)

    with pytest.raises(AotPlanError) as caught:
        WorkflowSpec.from_portable(plan)
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
        BuildRequest(
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
        "workflow_id": manifest["workflow_id"],
        "entry_mode": manifest["entry_mode"],
        "target": manifest["target"],
        "profile": manifest["profile"],
        "entry": manifest["entry"],
        "external_packages": manifest["external_packages"],
        "host_extensions": manifest["host_extensions"],
        "files": sorted(manifest["files"]),
    } == {
        "format": "vibeflow.aot-build.v1",
        "abi_version": "vibeflow.workflow.v2",
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
    emitted = emit_workflow_module(
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
