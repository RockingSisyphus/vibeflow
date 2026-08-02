from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

from vibeflow.targets.javascript.build.builder import BuildResult
from vibeflow.targets.javascript.frontend.model import normalize_workflow_plan
from vibeflow.tooling.application.javascript.build import (
    ProjectBuildError,
    ProjectBuildRequest,
    build_project_aot,
    prepare_project_build,
)
from vibeflow.targets.javascript.build.toolchain import ToolchainInfo


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _requirement(type_key: str, cardinality: str = "exactly_one") -> dict[str, str]:
    return {
        "type": type_key,
        "cardinality": cardinality,
        "display_name": type_key,
    }


def _provider(key: str, type_key: str | None = None) -> dict[str, str]:
    return {
        "key": key,
        "type": type_key or key,
        "display_name": key,
    }


def _project(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    (project / "src").mkdir()
    (project / "src/add.ts").write_text(
        "export function run(inputs, params) { return {'value.out': params.delta}; }\n",
        encoding="utf-8",
    )
    (project / "src/start.ts").write_text(
        "export function run(inputs) { return {'start.value': inputs['value.in'].value}; }\n",
        encoding="utf-8",
    )
    (project / "src/math.ts").write_text(
        "export const add = (a, b) => a + b;\n",
        encoding="utf-8",
    )
    (project / "src/core.ts").write_text(
        "export const identity = value => value;\n",
        encoding="utf-8",
    )
    _write(
        project / "manifests/nodes/add.jsonc",
        {
            "kind": "node",
            "type_key": "demo.add",
            "display_name": "Add",
            "category": "demo",
            "description": "Adds a configured value.",
            "version": "1.0.0",
            "flow_kind": "terminal",
            "contract": {
                "requires": [_requirement("value.in")],
                "provides": [_provider("value.out")],
                "params_schema": {"delta": {"type": "number"}},
                "params_defaults": {"delta": 1},
                "output_schema": {"value.out": {"type": "number"}},
            },
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "source": {
                        "kind": "file",
                        "ref": "src/add.ts",
                        "export": "run",
                    },
                }
            ],
            "base_libs": ["demo.math"],
            "capabilities": [
                {"id": "demo.storage", "operations": ["read"]}
            ],
        },
    )
    _write(
        project / "manifests/nodes/start.jsonc",
        {
            "kind": "node",
            "type_key": "demo.start",
            "display_name": "Start",
            "category": "demo",
            "description": "Starts the nested workflow.",
            "version": "1.0.0",
            "flow_kind": "terminal",
            "contract": {
                "requires": [_requirement("value.in")],
                "provides": [_provider("start.value", "value.in")],
                "params_schema": {},
                "params_defaults": {},
                "output_schema": {"start.value": {"type": "number"}},
            },
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "source": {
                        "kind": "file",
                        "ref": "src/start.ts",
                        "export": "run",
                    },
                }
            ],
            "base_libs": [],
            "capabilities": [],
        },
    )
    _write(
        project / "manifests/base_lib/math.jsonc",
        {
            "kind": "base_lib",
            "id": "demo.math",
            "display_name": "Math",
            "description": "Math helpers.",
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "source": {"kind": "file", "ref": "src/math.ts"},
                }
            ],
            "dependencies": ["demo.core"],
            "external_packages": ["pure-package"],
        },
    )
    _write(
        project / "manifests/base_lib/core.jsonc",
        {
            "kind": "base_lib",
            "id": "demo.core",
            "display_name": "Core",
            "description": "Core helpers.",
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "source": {"kind": "file", "ref": "src/core.ts"},
                }
            ],
            "dependencies": [],
            "external_packages": [],
        },
    )
    for type_key, schema in (
        ("value.in", {"type": "number"}),
        ("value.out", {"type": "number"}),
        ("storage.read.request", {"type": "object"}),
        ("storage.read.result", {"type": "object"}),
    ):
        _write(
            project / f"manifests/data/{type_key}.jsonc",
            {
                "kind": "data_schema",
                "type_key": type_key,
                "representation": "json",
                "schema": schema,
            },
        )
    _write(
        project / "manifests/capabilities/storage.jsonc",
        {
            "kind": "capability",
            "id": "demo.storage",
            "targets": ["browser", "node"],
            "operations": {
                "read": {
                    "input_type": "storage.read.request",
                    "output_type": "storage.read.result",
                }
            },
        },
    )
    _write(
        project / "nodesets/group.jsonc",
        {
            "type_key": "demo.group",
            "display_name": "Group",
            "description": "Nested group.",
            "flow_kind": "terminal",
            "requires": [_requirement("value.in")],
            "provides": [_provider("value.out")],
            "global_config": {"delta": 2},
            "pipeline": {
                "inputs": [
                    {
                        **_provider("value.in"),
                        "required": True,
                    }
                ],
                "outputs": [_requirement("value.out")],
                "nodes": [
                    {
                        "id": "add",
                        "type_used": "demo.add",
                        "display_name": "Add",
                        "description": "Nested add.",
                        "requires": [_requirement("value.in")],
                        "provides": [_provider("value.out")],
                        "config": {"delta": 2},
                    }
                ],
            },
        },
    )
    config = project / "workflow.jsonc"
    _write(
        config,
        {
            "global_config": {"delta": 3},
            "nodeset_imports": ["nodesets/group.jsonc"],
            "pipeline": {
                "inputs": [
                    {
                        **_provider("value.in"),
                        "required": True,
                    }
                ],
                "outputs": [
                    {
                        **_requirement("value.out"),
                        "as": "answer",
                    }
                ],
                "nodes": [
                    {
                        "id": "start",
                        "type_used": "demo.start",
                        "display_name": "Start",
                        "description": "Starts the nested workflow.",
                        "requires": [_requirement("value.in")],
                        "provides": [_provider("start.value", "value.in")],
                    },
                    {
                        "id": "group",
                        "type_used": "demo.group",
                        "display_name": "Group",
                        "description": "Calls the group.",
                        "requires": [_requirement("value.in")],
                        "provides": [_provider("value.out")],
                        "config": {"delta": 4},
                        "allow_config_override": True,
                        "node_configs": {"add": {"delta": 7}},
                    }
                ],
                "edges": [{"from": "start", "to": "group"}],
            },
        },
    )
    _write(
        project / "vibeflow_project.jsonc",
        {
            "descriptors": {
                "nodes": ["manifests/nodes"],
                "base_lib": ["manifests/base_lib"],
                "data_schemas": ["manifests/data"],
                "capabilities": ["manifests/capabilities"],
            },
            "javascript": {
                "package_root": ".",
                "external_packages": ["host-package"],
            },
        },
    )
    workspace = tmp_path / "vibeflow_config.jsonc"
    _write(workspace, {"roots": [{"id": "demo", "path": "project"}]})
    return workspace, config, project


def _request(tmp_path: Path, **changes: object) -> ProjectBuildRequest:
    workspace, config, _project_root = _project(tmp_path)
    values: dict[str, object] = {
        "workspace": workspace,
        "config": config,
        "out_dir": tmp_path / "dist",
        "target": "browser",
        "profile": "esm-module",
    }
    values.update(changes)
    return ProjectBuildRequest(**values)


def _add_host_extension(
    project: Path,
    extension_id: str,
    *,
    dependencies: list[str] | None = None,
    provides: list[str] | None = None,
) -> None:
    safe_name = extension_id.replace(".", "-")
    source = project / f"src/{safe_name}.ts"
    source.write_text(
        """
export function createHostExtension(context) {
  globalThis.__hostConfig = context.config;
  return { start() {}, stop() {} };
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _write(
        project / f"manifests/host_extensions/{safe_name}.jsonc",
        {
            "kind": "host_extension",
            "id": extension_id,
            "targets": ["browser", "node"],
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "source": {
                        "kind": "file",
                        "ref": f"src/{safe_name}.ts",
                        "export": "createHostExtension",
                    },
                }
            ],
            "provides": provides or [],
            "dependencies": dependencies or [],
        },
    )
    project_config = project / "vibeflow_project.jsonc"
    raw = json.loads(project_config.read_text(encoding="utf-8"))
    raw["descriptors"]["host_extensions"] = [
        "manifests/host_extensions"
    ]
    _write(project_config, raw)


def test_prepare_project_build_loads_static_js_only_nested_project(
    tmp_path: Path,
) -> None:
    prepared = prepare_project_build(_request(tmp_path))

    assert prepared.used_node_types == ("demo.add", "demo.start")
    assert prepared.used_base_libs == ("demo.core", "demo.math")
    assert prepared.used_capabilities == ("demo.storage",)
    assert len(prepared.plan.blocks) == 2
    nested = next(block for block in prepared.plan.blocks if block.path == ("group",))
    assert nested.node("add").params.to_value() == {
        "_global": {"delta": 3},
        "delta": 7,
    }
    assert prepared.payload["inputs"][0]["required"] is True
    assert prepared.payload["outputs"][0]["as"] == "answer"
    assert set(prepared.payload["schemas"]) == {
        "storage.read.request",
        "storage.read.result",
        "value.in",
        "value.out",
    }
    nested_payload = next(
        block for block in prepared.payload["blocks"] if block["path"] == ["group"]
    )
    assert nested_payload["nodes"][0]["capabilities"] == [
        {"id": "demo.storage", "operations": ["read"]}
    ]
    assert prepared.import_policy["node_base_libs"] == {
        "demo.add": ["demo.math"],
        "demo.start": [],
    }
    assert prepared.import_policy["base_lib_dependencies"] == {
        "demo.core": [],
        "demo.math": ["demo.core"],
    }
    assert prepared.import_policy["allowed_external_packages"] == [
        "host-package",
        "pure-package",
    ]
    assert Path(
        prepared.implementation_by_type["demo.add"]["module"]
    ).is_absolute()
    bindings = prepared.javascript_bindings
    assert bindings is not None
    assert tuple(call.path for call in bindings.calls) == (
        ("start",),
        ("group",),
        ("group", "add"),
    )
    assert bindings.binding(("group",)).implementation.to_dict() == {
        "kind": "catalog",
        "ref": "demo.group",
        "export": "",
    }
    nested_binding = bindings.binding(("group", "add"))
    assert nested_binding.base_libs == ("demo.math",)
    assert [item.to_dict() for item in nested_binding.capabilities] == [
        {"id": "demo.storage", "operations": ["read"]}
    ]
    assert set(bindings.schemas.to_value()) == {
        "storage.read.request",
        "storage.read.result",
        "value.in",
        "value.out",
    }
    assert set(bindings.base_libs.to_value()) == {
        "demo.core",
        "demo.math",
    }
    assert set(bindings.capabilities.to_value()) == {"demo.storage"}
    assert bindings.import_policy.to_value() == prepared.import_policy
    assert "javascript_bindings" not in prepared.plan.to_dict()
    emitted_plan = normalize_workflow_plan(prepared.payload)
    composite = next(node for node in emitted_plan.nodes if node.id == "group")
    assert composite.subplan is not None
    assert composite.subplan.nodes[0].params["delta"] == 7


def test_prepare_project_build_exposes_target_owned_compile_hook_seam(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    observed: list[tuple[str, ...]] = []

    def before_compile(graph, catalogs):
        observed.append(catalogs.nodes.available())
        return graph

    prepared = prepare_project_build(
        request,
        before_compile_hooks=(before_compile,),
    )

    assert observed == [("demo.add", "demo.start")]
    assert prepared.declared_plugins == ()
    assert prepared.planned_plugins == ()
    assert prepared.plugin_bindings == ()


def test_prepare_project_build_never_imports_python_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path)
    original_import = builtins.__import__

    def guarded_import(name: str, *args, **kwargs):
        if name == "vibeflow.targets.python" or name.startswith(
            "vibeflow.targets.python."
        ):
            raise AssertionError(f"unexpected Python Target import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    prepared = prepare_project_build(request)

    assert prepared.used_node_types == ("demo.add", "demo.start")


def test_workflow_host_extensions_support_planned_and_instance_config(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    project = Path(request.config).parent
    _add_host_extension(
        project,
        "demo.browser_host",
        provides=["demo.storage"],
    )
    _add_host_extension(
        project,
        "demo.future_host",
        provides=["demo.storage"],
    )
    raw = json.loads(Path(request.config).read_text(encoding="utf-8"))
    raw["host_extensions"] = [
        {
            "id": "demo.browser_host",
            "status": "implemented",
            "config": {"channel": "primary"},
        },
        {
            "id": "demo.future_host",
            "status": "planned",
            "display_name": "Future Host",
            "description": "Planned host connection.",
        },
    ]
    _write(Path(request.config), raw)

    prepared = prepare_project_build(request)

    assert prepared.used_host_extensions == ("demo.browser_host",)
    assert prepared.planned_host_extensions == ("demo.future_host",)
    assert [item["status"] for item in prepared.declared_host_extensions] == [
        "implemented",
        "planned",
    ]
    assert prepared.host_extensions[0]["config"] == {
        "channel": "primary"
    }
    assert all(
        item["id"] != "demo.future_host"
        for item in prepared.host_extensions
    )
    host_owner = next(
        owner
        for owner in prepared.import_policy["owners"]
        if owner["kind"] == "host_extension"
    )
    assert host_owner["id"] == "demo.browser_host"
    assert host_owner["export"] == "createHostExtension"
    assert host_owner["completion"] == "immediate"
    assert prepared.javascript_bindings is not None
    assert [
        item.to_value()
        for item in prepared.javascript_bindings.host_extensions
    ] == list(prepared.host_extensions)


def test_workflow_host_extensions_override_legacy_project_selection(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    project = Path(request.config).parent
    _add_host_extension(project, "demo.legacy_host")
    project_config = project / "vibeflow_project.jsonc"
    project_raw = json.loads(project_config.read_text(encoding="utf-8"))
    project_raw["javascript"]["host_extensions"] = ["demo.legacy_host"]
    _write(project_config, project_raw)

    legacy = prepare_project_build(request)
    assert legacy.used_host_extensions == ("demo.legacy_host",)
    assert legacy.warnings[0]["code"] == (
        "VF_AOT_HOST_EXTENSION_LEGACY_SELECTION"
    )

    workflow_raw = json.loads(
        Path(request.config).read_text(encoding="utf-8")
    )
    workflow_raw["host_extensions"] = []
    _write(Path(request.config), workflow_raw)

    workflow_override = prepare_project_build(request)
    assert workflow_override.used_host_extensions == ()
    assert workflow_override.warnings == ()


def test_implemented_host_extension_cannot_depend_on_planned_extension(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    project = Path(request.config).parent
    _add_host_extension(
        project,
        "demo.active_host",
        dependencies=["demo.future_host"],
    )
    _add_host_extension(project, "demo.future_host")
    raw = json.loads(Path(request.config).read_text(encoding="utf-8"))
    raw["host_extensions"] = [
        {"id": "demo.active_host"},
        {"id": "demo.future_host", "status": "planned"},
    ]
    _write(Path(request.config), raw)

    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(request)

    assert (
        captured.value.code
        == "VF_AOT_HOST_EXTENSION_PLANNED_DEPENDENCY"
    )


def test_host_extension_explicit_empty_contract_must_match_descriptor(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    project = Path(request.config).parent
    _add_host_extension(
        project,
        "demo.browser_host",
        provides=["demo.storage"],
    )
    raw = json.loads(Path(request.config).read_text(encoding="utf-8"))
    raw["host_extensions"] = [
        {
            "id": "demo.browser_host",
            "provides": [],
        }
    ]
    _write(Path(request.config), raw)

    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(request)

    assert captured.value.code == "VF_AOT_HOST_EXTENSION_CONFIG"
    assert "provides must match" in captured.value.message


def test_host_extension_null_selection_is_not_an_empty_override(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    raw = json.loads(Path(request.config).read_text(encoding="utf-8"))
    raw["host_extensions"] = None
    _write(Path(request.config), raw)

    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(request)

    assert captured.value.code == "VF_AOT_HOST_EXTENSION_CONFIG"
    assert "must be a list" in captured.value.message


def test_prepare_project_build_ignores_python_registry_metadata(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    project = Path(request.config).parent
    (project / "registry.py").write_text(
        "\n".join(
            (
                "raise AssertionError('JS AOT must not import Python registry.py')",
                "def build_registry():",
                "    raise AssertionError('JS AOT must not build a Python registry')",
            )
        ),
        encoding="utf-8",
    )
    project_config = project / "vibeflow_project.jsonc"
    raw = json.loads(project_config.read_text(encoding="utf-8"))
    raw["registry"] = "registry.py:build_registry"
    _write(project_config, raw)

    prepared = prepare_project_build(request)

    assert {
        item.language
        for item in prepared.catalogs.nodes.require(
            "demo.add"
        ).implementations
    } == {"typescript"}
    assert prepared.implementation_by_type["demo.add"]["language"] == "typescript"


def test_prepare_project_build_rejects_ambiguous_input_requiredness(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    raw = json.loads(Path(request.config).read_text(encoding="utf-8"))
    raw["pipeline"]["inputs"][0].pop("required")
    _write(Path(request.config), raw)

    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(request)

    assert captured.value.code == "VF_AOT_INPUT_REQUIRED"


def test_prepare_project_build_checks_graph_call_contract(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    nodeset = Path(request.config).parent / "nodesets/group.jsonc"
    raw = json.loads(nodeset.read_text(encoding="utf-8"))
    raw["pipeline"]["nodes"][0]["requires"][0]["cardinality"] = "optional_one"
    _write(nodeset, raw)

    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(request)

    assert captured.value.code == "VF_AOT_CONTRACT"
    assert captured.value.node_path == ("group", "add")


def test_prepare_project_build_requires_schema_and_target_implementation(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    missing_schema = (
        Path(request.config).parent
        / "manifests/data/storage.read.result.jsonc"
    )
    missing_schema.unlink()
    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(request)
    assert captured.value.code == "VF_AOT_SCHEMA_MISSING"

    request = _request(tmp_path / "target")
    node_manifest = (
        Path(request.config).parent / "manifests/nodes/add.jsonc"
    )
    raw = json.loads(node_manifest.read_text(encoding="utf-8"))
    raw["implementations"][0]["targets"] = ["browser"]
    _write(node_manifest, raw)
    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(
            ProjectBuildRequest(
                **{
                    **request.__dict__,
                    "target": "node",
                }
            )
        )
    assert captured.value.code == "VF_AOT_IMPLEMENTATION_TARGET"


@pytest.mark.parametrize(
    ("manifest", "schema_path"),
    [
        ("manifests/data/value.in.jsonc", ("schema",)),
        (
            "manifests/nodes/add.jsonc",
            ("contract", "output_schema", "value.out"),
        ),
    ],
)
def test_prepare_project_build_rejects_schema_keywords_runtime_cannot_enforce(
    tmp_path: Path,
    manifest: str,
    schema_path: tuple[str, ...],
) -> None:
    request = _request(tmp_path)
    descriptor_path = Path(request.config).parent / manifest
    raw = json.loads(descriptor_path.read_text(encoding="utf-8"))
    target = raw
    for key in schema_path:
        target = target[key]
    target["not"] = {"const": 3}
    _write(descriptor_path, raw)

    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(request)

    assert captured.value.code == "VF_AOT_SCHEMA_UNSUPPORTED"
    assert "not" in captured.value.message


@pytest.mark.parametrize("source_kind", ["module", "package", "generated"])
def test_prepare_project_build_rejects_unaudited_source_kinds(
    tmp_path: Path,
    source_kind: str,
) -> None:
    request = _request(tmp_path)
    node_manifest = (
        Path(request.config).parent / "manifests/nodes/add.jsonc"
    )
    raw = json.loads(node_manifest.read_text(encoding="utf-8"))
    raw["implementations"][0]["source"] = {
        "kind": source_kind,
        "ref": "unsafe-node",
        "export": "run",
    }
    _write(node_manifest, raw)

    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(request)

    assert captured.value.code == "VF_AOT_IMPLEMENTATION_SOURCE"
    assert "only accepts audited project files" in captured.value.message


def test_prepare_project_build_does_not_load_python_plugins(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    project = Path(request.config).parent
    (project / "python_plugin.py").write_text(
        "raise AssertionError('JS AOT must not import Python plugins')\n",
        encoding="utf-8",
    )
    project_config = project / "vibeflow_project.jsonc"
    raw = json.loads(project_config.read_text(encoding="utf-8"))
    raw["plugins"] = [
        {
            "module": "python_plugin.py",
            "type": "runtime",
        }
    ]
    _write(project_config, raw)

    prepared = prepare_project_build(request)

    assert prepared.implementation_by_type["demo.add"]["language"] == "typescript"


def test_build_project_aot_forwards_prepared_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(
        tmp_path,
        profile="web-app",
        html_template="index.template.html",
        app_entry="src/app.ts",
        replace=True,
        sourcemap="inline",
    )
    captured: list[object] = []
    fake = BuildResult(
        out_dir=Path(request.out_dir),
        entry=Path(request.out_dir) / "index.html",
        manifest=Path(request.out_dir) / "vibeflow-build.json",
        toolchain=ToolchainInfo(
            node="22.12.0",
            typescript="7.0.0",
            esbuild="0.28.0",
            lock_sha256="lock",
            lock_files=("package-lock.json",),
        ),
        files=("index.html",),
    )

    def fake_build(build_request):
        captured.append(build_request)
        return fake

    monkeypatch.setattr("vibeflow.tooling.application.javascript.build.build_aot", fake_build)
    result = build_project_aot(request)

    assert result.entry == fake.entry
    forwarded = captured[0]
    assert forwarded.profile == "web-app"
    assert forwarded.html_template == "index.template.html"
    assert forwarded.app_entry == "src/app.ts"
    assert forwarded.replace is True
    assert forwarded.sourcemap == "inline"
    assert forwarded.implementation_by_type == {}
    assert forwarded.import_policy == {}
    assert forwarded.host_extensions == ()
    assert forwarded.javascript_bindings is result.prepared.javascript_bindings
    assert (
        forwarded.javascript_bindings.import_policy.to_value()[
            "node_base_libs"
        ]
    ) == {
        "demo.add": ["demo.math"],
        "demo.start": [],
    }
