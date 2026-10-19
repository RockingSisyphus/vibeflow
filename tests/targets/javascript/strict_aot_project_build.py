from __future__ import annotations

from tests.fixtures.support.plugins import Resource, resource as sdk_resource, write_plugin

import builtins
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from vibeflow.targets.javascript.build.builder import BuildResult
from vibeflow.targets.javascript.frontend.emission_view import bound_workflow_view
from vibeflow.tooling.application.javascript.build import (
    ProjectBuildError,
    ProjectBuildRequest,
    build_project_aot,
    prepare_project_build,
)
from vibeflow.tooling.application.javascript.audit import JavascriptAuditRequest, audit_javascript_project
from vibeflow.tooling.application.javascript.presentation.diagrams import render_mermaid
from vibeflow.tooling.application.javascript.presentation.architecture import render_architecture
from vibeflow.tooling.application.javascript.presentation.diagrams import write_review_svg
from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.flow import (
    GraphConfig,
    GraphConfigError,
    NodeMetadata,
    NodeSpec,
    NodeStyle,
    STATUS_PLANNED,
)
from vibeflow.tooling.presentation.mermaid import is_mermaid_svg_renderer_available
from vibeflow.targets.javascript.build.toolchain import ToolchainInfo
from vibeflow.tooling.project.architecture_types import WorkspaceConfigError


def _write(path: Path, payload: object) -> None:
    if not isinstance(path, Resource):
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
    write_plugin(project, [], target="javascript")
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    for filename in ("package.json", "package-lock.json"):
        shutil.copy2(toolchain / filename, project / filename)
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
        sdk_resource(project, "node", "demo.add"),
        {
            "kind": "node",
            "type_key": "demo.add",
            "rulesets": ["vibeflow.process"],
            "display_name": "Add",

            "description": "Adds a configured value.",
            "version": "1.0.0",
            "flow_kind": "terminal",
            "contract": {
                "requires": [_requirement("value.in")],
                "provides": [_provider("value.out")],
                "params_schema": {"delta": {"type": "number"}},
                "params_defaults": {"delta": 1},
                "input_semantics": {"value.in": ["input value"]},
                "output_semantics": {"value.out": ["result value"]},
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
        sdk_resource(project, "node", "demo.start"),
        {
            "kind": "node",
            "type_key": "demo.start",
            "rulesets": ["vibeflow.process"],
            "display_name": "Start",

            "description": "Starts the nested workflow.",
            "version": "1.0.0",
            "flow_kind": "terminal",
            "contract": {
                "requires": [_requirement("value.in")],
                "provides": [_provider("start.value", "value.in")],
                "params_schema": {},
                "params_defaults": {},
                "input_semantics": {"value.in": ["input value"]},
                "output_semantics": {"start.value": ["forwarded value"]},
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
        sdk_resource(project, "base_lib", "demo.math"),
        {
            "kind": "base_lib",
            "id": "demo.math",
            "rulesets": ["vibeflow.base_lib"],
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
        sdk_resource(project, "base_lib", "demo.core"),
        {
            "kind": "base_lib",
            "id": "demo.core",
            "rulesets": ["vibeflow.base_lib"],
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
            sdk_resource(project, "data_schema", type_key),
            {
                "kind": "data_schema",
                "type_key": type_key,
                "representation": "json",
                "schema": schema,
            },
        )
    _write(
        sdk_resource(project, "capability", "demo.storage"),
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
            "rulesets": [],
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
            "plugins": [{"source": {"kind": "file", "ref": "code_plugin.ts", "export": "plugin"}}],
            "rulesets": [],
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
                    },
                    {
                        "id": "group",
                        "type_used": "demo.group",
                        "display_name": "Group",
                        "description": "Calls the group.",
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
            "project_target": "javascript",
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


def test_build_compiles_uncalled_empty_rule_declarations(tmp_path):
    request = _request(tmp_path)
    data = json.loads(Path(request.config).read_text())
    data["rulesets"] = []
    declaration = Path(request.config).parent / "nodesets/unused.jsonc"
    _write(declaration,{"type_key":"demo.unused","display_name":"Unused","description":"Native error still applies.",
        "requires":[],"provides":[],"rulesets":[],"pipeline":{"nodes":[{"id":"unknown","display_name":"Unknown","description":"An unknown native Node type.","type_used":"unknown.node","rulesets":[]}]}})
    data.setdefault("nodeset_imports",[]).append("nodesets/unused.jsonc")
    _write(Path(request.config),data)
    with pytest.raises(Exception,match="unknown.node"):
        prepare_project_build(request)


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
        sdk_resource(project, "host_extension", extension_id),
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


def _add_unselected_plugin(project: Path) -> Path:
    source = project / "src/unused-plugin.ts"
    source.write_text(
        "export function createPlugin() { return {}; }\n",
        encoding="utf-8",
    )
    manifest = sdk_resource(project, 'plugin', 'demo.unused')
    _write(
        sdk_resource(project, "plugin", "demo.unused"),
        {
            "kind": "plugin",
            "id": "demo.unused",
            "type": "runtime",
            "targets": ["browser", "node"],
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "source": {
                        "kind": "file",
                        "ref": "src/unused-plugin.ts",
                        "export": "createPlugin",
                    },
                }
            ],
            "config": {"schema": {}, "defaults": {}},
        },
    )
    return manifest


@pytest.mark.parametrize(
    "resource_kind",
    ("node", "base_lib", "plugin"),
)
def test_javascript_root_rejects_foreign_implementation_languages_even_when_unused(
    tmp_path: Path,
    resource_kind: str,
) -> None:
    request = _request(tmp_path)
    project = Path(request.config).parent
    if resource_kind == "node":
        manifest = sdk_resource(project, 'node', 'demo.add')
    elif resource_kind == "base_lib":
        manifest = sdk_resource(project, 'base_lib', 'demo.core')
    elif resource_kind == "plugin":
        manifest = _add_unselected_plugin(project)
    else:
        raise AssertionError(resource_kind)

    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["implementations"][0]["language"] = "python"
    raw["implementations"][0]["targets"] = ["python"]
    if resource_kind == "plugin":
        raw["targets"] = ["python"]
    _write(manifest, raw)

    if resource_kind == "plugin":
        # Resource packages are enabled solely by workflow selection.
        document = json.loads(Path(request.config).read_text())
        document["plugins"] = [{"source": {"kind": "file", "ref": "code_plugin.ts", "export": "plugin"}}]
        _write(Path(request.config), document)

    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(request)

    assert captured.value.code == "VF_AOT_CONTRACT_INVALID"
    assert resource_kind in captured.value.message
    assert "foreign implementation languages: ['python']" in captured.value.message


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
    assert prepared.plan.inputs[0].required is True
    assert prepared.plan.outputs[0].as_key == "answer"
    assert set(prepared.javascript_bindings.schemas.to_value()) == {
        "storage.read.request",
        "storage.read.result",
        "value.in",
        "value.out",
    }
    assert [item.to_dict() for item in prepared.javascript_bindings.binding(("group", "add")).capabilities] == [
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
    assert Path(prepared.javascript_bindings.binding(("group", "add")).implementation.ref).is_absolute()
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
    emitted_plan = bound_workflow_view(prepared.plan, prepared.javascript_bindings)
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
    capsys: pytest.CaptureFixture[str],
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

    from vibeflow.tooling.application.cli import main
    arguments = ["--workspace", str(request.workspace), "--config", str(request.config), "--json"]
    assert main(["review-rules", *arguments]) == 0
    review = json.loads(capsys.readouterr().out)
    assert {item["id"] for item in review["resources"] if item["kind"] == "host_extension"} == {
        "demo.browser_host", "demo.future_host",
    }
    assert main(["validate", *arguments]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["status"] in {"PASS", "CONCERNS"}


@pytest.mark.parametrize("workflow_override", [False, True])
@pytest.mark.parametrize("old_hosts", [[], ["demo.legacy_host"]])
def test_project_host_selection_is_removed_even_with_workflow_override(tmp_path, workflow_override, old_hosts):
    request = _request(tmp_path)
    project = Path(request.config).parent
    project_config = project / "vibeflow_project.jsonc"
    raw = json.loads(project_config.read_text(encoding="utf-8"))
    raw["javascript"]["host_extensions"] = old_hosts
    _write(project_config, raw)
    if workflow_override:
        workflow = json.loads(Path(request.config).read_text(encoding="utf-8"))
        workflow["host_extensions"] = []
        _write(Path(request.config), workflow)
    with pytest.raises(WorkspaceConfigError, match="javascript.host_extensions was removed") as captured:
        prepare_project_build(request)
    assert captured.value.rule_id == "WORKSPACE.PROJECT_CONFIG.JAVASCRIPT"
    assert captured.value.source_location["field"] == "javascript.host_extensions"


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


def test_prepare_project_build_rejects_python_registry_metadata(
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

    with pytest.raises(WorkspaceConfigError) as invalid:
        prepare_project_build(request)

    assert invalid.value.rule_id == "PLUGIN.REGISTRATION.MIGRATION"
    assert "registry" in invalid.value.source_location["fields"]


def test_prepare_project_build_rejects_ambiguous_input_requiredness(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    raw = json.loads(Path(request.config).read_text(encoding="utf-8"))
    raw["pipeline"]["inputs"][0].pop("required")
    _write(Path(request.config), raw)

    with pytest.raises(GraphConfigError, match="required must be explicitly true or false"):
        prepare_project_build(request)


def test_prepare_project_build_rejects_graph_call_contract_duplicates(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    nodeset = Path(request.config).parent / "nodesets/group.jsonc"
    raw = json.loads(nodeset.read_text(encoding="utf-8"))
    raw["pipeline"]["nodes"][0]["requires"] = [_requirement("value.in", "optional_one")]
    _write(nodeset, raw)

    with pytest.raises(GraphConfigError) as captured:
        prepare_project_build(request)

    assert "derived from type_used" in str(captured.value)


def test_prepare_project_build_requires_schema_and_target_implementation(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    missing_schema = (
        sdk_resource(Path(request.config).parent, 'data_schema', 'storage.read.result')
    )
    missing_schema.unlink()
    with pytest.raises(ProjectBuildError) as captured:
        prepare_project_build(request)
    assert captured.value.code == "VF_AOT_SCHEMA_MISSING"

    request = _request(tmp_path / "target")
    node_manifest = (
        sdk_resource(Path(request.config).parent, 'node', 'demo.add')
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
    assert captured.value.code == "VF_AOT_TARGET_IMPLEMENTATION_MISSING"


def test_target_neutral_audit_does_not_require_a_shared_platform(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    project = Path(request.config).parent
    add_manifest = sdk_resource(project, 'node', 'demo.add')
    start_manifest = sdk_resource(project, 'node', 'demo.start')
    add = json.loads(add_manifest.read_text(encoding="utf-8"))
    start = json.loads(start_manifest.read_text(encoding="utf-8"))
    add["implementations"][0]["targets"] = ["node"]
    start["implementations"][0]["targets"] = ["browser"]
    _write(add_manifest, add)
    _write(start_manifest, start)

    audited = audit_javascript_project(
        JavascriptAuditRequest(
            workspace=request.workspace,
            config=request.config,
            audit_sources=False,
        )
    )

    implementations = audited.architecture["node_types"]
    assert implementations["demo.add"]["implementations"][0]["targets"] == [
        "node"
    ]
    assert implementations["demo.start"]["implementations"][0][
        "targets"
    ] == ["browser"]


def test_target_neutral_audit_never_loads_planned_plugin_or_host_source(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    project = Path(request.config).parent
    _add_host_extension(project, "demo.future_host")
    (project / "src/demo-future_host.ts").unlink()
    _write(
        sdk_resource(project, "plugin", "demo.future_plugin"),
        {
            "kind": "plugin",
            "id": "demo.future_plugin",
            "type": "runtime",
            "targets": ["browser", "node"],
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "source": {
                        "kind": "file",
                        "ref": "src/does-not-exist.ts",
                        "export": "createPlugin",
                    },
                }
            ],
            "dependencies": [],
            "external_packages": [],
            "config": {"schema": {}, "defaults": {}},
        },
    )
    workflow = json.loads(Path(request.config).read_text(encoding="utf-8"))
    sdk_resource(project, "plugin", "demo.future_plugin").unlink()
    workflow["plugins"] = [
        {"source": {"kind": "file", "ref": "code_plugin.ts", "export": "plugin"}},
        {"id": "demo.future_plugin", "status": "planned", "type": "runtime"}
    ]
    workflow["host_extensions"] = [
        {"id": "demo.future_host", "status": "planned"}
    ]
    _write(Path(request.config), workflow)

    audited = audit_javascript_project(
        JavascriptAuditRequest(
            workspace=request.workspace,
            config=request.config,
            audit_sources=False,
            audit_registered_resources=True,
        )
    )

    assert all("does-not-exist" not in item for item in audited.source_files)
    assert all("future_host" not in item for item in audited.source_files)


def test_target_neutral_architecture_is_location_independent(
    tmp_path: Path,
) -> None:
    left = _request(tmp_path / "left")
    right = _request(tmp_path / "right")
    left_result = audit_javascript_project(
        JavascriptAuditRequest(
            workspace=left.workspace,
            config=left.config,
            audit_sources=False,
        )
    )
    right_result = audit_javascript_project(
        JavascriptAuditRequest(
            workspace=right.workspace,
            config=right.config,
            audit_sources=False,
        )
    )

    assert render_architecture(left_result) == render_architecture(right_result)
    assert render_mermaid(left_result) == render_mermaid(right_result)
    assert left_result.architecture["workflow"]["source"] == {
        "root_id": "demo",
        "path": "workflow.jsonc",
    }
    assert left_result.architecture["workflow"]["nodes"][1]["invokes"] == {
        "kind": "nodeset",
        "target": "demo.group",
        "target_status": "implemented",
    }
    assert left_result.architecture["nodesets"]["demo.group"]["body"]["nodes"][0]["id"] == "add"
    assert left_result.architecture["nodesets"]["demo.group"]["reachable_from_workflow"] is True


def test_javascript_planned_global_state_renders_as_cloud_path() -> None:
    graph = GraphConfig(
        nodes=(
            NodeSpec(
                id="runtime_state",
                type_used="future.runtime_state",
                status=STATUS_PLANNED,
                flow_kind="global_state",
            ),
            NodeSpec(
                id="ordinary",
                type_used="future.ordinary",
                status=STATUS_PLANNED,
                flow_kind="process",
            ),
        )
    )
    compiled = CompiledGraph(
        order=("runtime_state", "ordinary"),
        explicit_edges=(),
        data_edges=(),
        effective_edges=(),
        providers={},
        consumers={},
        flow_kinds={
            "runtime_state": "global_state",
            "ordinary": "process",
        },
    )
    result = SimpleNamespace(graph=graph, compiled=compiled)

    mermaid = render_mermaid(result)
    assert 'runtime_state@{ shape: cloud, label: "runtime_state' in mermaid
    assert "class vf_runtime_state plannedNode;" in mermaid
    assert "class vf_ordinary plannedNode;" in mermaid
    assert "status: planned blocking" in mermaid
    assert "flow_kind: global_state" in mermaid
    assert "effect_scope: unavailable" in mermaid
    assert "runtime_dispatch" not in mermaid
    assert "execution_lock: none" in mermaid


def test_javascript_mermaid_composes_planned_custom_and_external_styles(
    tmp_path: Path,
) -> None:
    graph = GraphConfig(
        nodes=(
            NodeSpec(
                id="planned",
                type_used="future.planned",
                status=STATUS_PLANNED,
                flow_kind="process",
                metadata=NodeMetadata(
                    display_name="Planned",
                    description="Shows planned styling.",
                ),
            ),
            NodeSpec(
                id="custom",
                type_used="demo.custom",
                metadata=NodeMetadata(
                    display_name="Custom",
                    description="Shows custom colours.",
                ),
                style=NodeStyle(
                    fill="#dbeafe",
                    stroke="#1d4ed8",
                    text="#172554",
                ),
            ),
            NodeSpec(
                id="external",
                type_used="demo.external",
                metadata=NodeMetadata(
                    display_name="External",
                    description="Shows the external boundary.",
                ),
            ),
            NodeSpec(
                id="external_custom",
                type_used="demo.external_custom",
                metadata=NodeMetadata(
                    display_name="External Custom",
                    description="Combines custom colours and the external boundary.",
                ),
                style=NodeStyle(
                    fill="#fbc8e2",
                    stroke="#b81759",
                    text="#500724",
                ),
            ),
        )
    )
    compiled = CompiledGraph(
        order=tuple(node.id for node in graph.nodes),
        explicit_edges=(),
        data_edges=(),
        effective_edges=(),
        providers={},
        consumers={},
        flow_kinds={node.id: node.flow_kind or "process" for node in graph.nodes},
        effect_scopes={"external": "trusted", "external_custom": "trusted"},
    )
    descriptors = {
        "demo.custom": SimpleNamespace(
            rulesets=(),
            display_name="Custom",
            description="Shows custom colours.",
            external=False,
        ),
        "demo.external": SimpleNamespace(
            rulesets=(),
            display_name="External",
            description="Shows the external boundary.",
            external=True,
        ),
        "demo.external_custom": SimpleNamespace(
            rulesets=(),
            display_name="External Custom",
            description="Combines custom colours and the external boundary.",
            external=True,
        ),
    }
    result = SimpleNamespace(
        graph=graph,
        compiled=compiled,
        catalogs=SimpleNamespace(nodes=descriptors),
        architecture={"resources": {}},
        plugin_records=(),
        host_records=(),
        compiled_nodesets={},
        plan=SimpleNamespace(workflow_id="visual-test"),
        root=SimpleNamespace(id="visual-test"),
    )

    mermaid = render_mermaid(result)

    assert "classDef plannedNode fill:#fef08a,stroke:#ca8a04,stroke-width:3px,stroke-dasharray: 6 3,color:#713f12;" in mermaid
    assert "class vf_planned plannedNode;" in mermaid
    assert "status: planned blocking" in mermaid
    assert "class vf_custom defaultNode;" in mermaid
    assert "style vf_custom fill:#dbeafe,stroke:#1d4ed8,color:#172554;" in mermaid
    assert "[EXTERNAL] External" in mermaid
    assert mermaid.count("external: true") == 2
    for node_id in ("vf_external", "vf_external_custom"):
        assert f"class {node_id} externalDependency;" in mermaid
        assert f"class {node_id} externalBoundary;" in mermaid
    assert "style vf_external_custom fill:#fbc8e2,stroke:#b81759,color:#500724;" in mermaid

    if not is_mermaid_svg_renderer_available():
        pytest.skip("Mermaid SVG renderer is not installed")

    for expand_nodesets, filename in (
        (False, "default.svg"),
        (True, "review-columns.svg"),
    ):
        output = tmp_path / filename
        write_review_svg(
            result,
            output,
            expand_nodesets=expand_nodesets,
            mermaid_layout="review-columns" if expand_nodesets else "default",
        )
        svg = output.read_text(encoding="utf-8")
        assert "plannedNode" in svg
        assert "fill:#fef08a !important" in svg
        assert "stroke-dasharray:6 3 !important" in svg
        assert "externalDependency externalBoundary" in svg
        assert "fill:#fbc8e2 !important" in svg
        assert "stroke:#b81759 !important" in svg
        assert "stroke-width:7px !important" in svg


def test_javascript_audit_carries_descriptor_external_and_config_style_to_mermaid(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    project = Path(request.config).parent
    descriptor_path = sdk_resource(project, 'node', 'demo.start')
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["external"] = True
    _write(descriptor_path, descriptor)
    config = json.loads(Path(request.config).read_text(encoding="utf-8"))
    config["pipeline"]["nodes"][0]["style"] = {
        "fill": "#fbc8e2",
        "stroke": "#b81759",
        "text": "#500724",
    }
    _write(Path(request.config), config)

    result = audit_javascript_project(
        JavascriptAuditRequest(
            workspace=request.workspace,
            config=request.config,
            audit_sources=False,
        )
    )
    mermaid = render_mermaid(result)

    assert "[EXTERNAL] Start" in mermaid
    assert "external: true" in mermaid
    assert "class vf_start externalDependency;" in mermaid
    assert "class vf_start externalBoundary;" in mermaid
    assert "style vf_start fill:#fbc8e2,stroke:#b81759,color:#500724;" in mermaid


@pytest.mark.parametrize(
    ("manifest", "schema_path"),
    [
        ("value.in", ("schema",)),
    ],
)
def test_prepare_project_build_rejects_schema_keywords_runtime_cannot_enforce(
    tmp_path: Path,
    manifest: str,
    schema_path: tuple[str, ...],
) -> None:
    request = _request(tmp_path)
    descriptor_path = sdk_resource(Path(request.config).parent, "data_schema", manifest)
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
        sdk_resource(Path(request.config).parent, 'node', 'demo.add')
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


def test_prepare_project_build_rejects_python_plugin_fields(
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

    with pytest.raises(WorkspaceConfigError) as invalid:
        prepare_project_build(request)

    assert invalid.value.rule_id == "PLUGIN.REGISTRATION.MIGRATION"
    assert "plugins" in invalid.value.source_location["fields"]


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
    assert forwarded.javascript_bindings is result.prepared.javascript_bindings
    assert (
        forwarded.javascript_bindings.import_policy.to_value()[
            "node_base_libs"
        ]
    ) == {
        "demo.add": ["demo.math"],
        "demo.start": [],
    }


# Publish controlled case inputs as fixed SDK plugins before formal entrypoints.
