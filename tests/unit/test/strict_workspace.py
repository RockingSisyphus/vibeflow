from tests.unit.strict_support import *

from vibeflow.workspace import (
    _workspace_runtime_options,
    WorkspaceConfigError,
    build_workspace_environment,
    build_workspace_node_registry,
    load_workspace_config,
    load_workspace_graph_for_export,
    run_workspace_checked,
    scan_workspace_code_quality,
    validate_workspace_config_path,
)


def test_workspace_cross_root_nodeset_validate_run_and_export(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(framework_root, [("framework.add", "AddNode", {"delta": {"type": "number"}}, {"delta": 1})])
    _write_registry(
        project_root,
        [
            ("test.start", "StartNode", {}, {}),
            ("test.seed", "SeedNode", {"value": {"type": "number"}}, {"value": 1}),
            ("test.out_end", "OutEndNode", {}, {}),
        ],
    )
    _write_project_config(framework_root, quality_enabled=True)
    _write_project_config(project_root, quality_enabled=True)
    nodeset_path = framework_root / "configs" / "nodesets" / "add_one.jsonc"
    nodeset_path.parent.mkdir(parents=True)
    nodeset_path.write_text(
        json.dumps(
            _nodeset_config(
                "framework.add_one",
                requires=["value.in"],
                provides=["value.out"],
                pipeline=_input_add_pipeline(add={"type": "framework.add"}),
            )
        ),
        encoding="utf-8",
    )
    config_path = project_root / "configs" / "main.jsonc"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "nodeset_imports": [{"root": "vibetrain", "path": "configs/nodesets/add_one.jsonc"}],
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts workspace flow."),
                        _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")], value=4),
                        _node_call("flow", "framework.add_one", "Calls framework nodeset.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                        _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                    ],
                    "edges": _edge_chain("start", "seed", "flow", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
            }
        ),
        encoding="utf-8",
    )

    workspace = load_workspace_config(workspace_path)
    report = validate_workspace_config_path(config_path, workspace=workspace)

    assert report.status in {"PASS", "CONCERNS"}
    assert report.info["workspace"]["roots"][0]["id"] == "vibetrain"
    assert report.info["nodeset_imports"][0]["root_id"] == "vibetrain"
    assert report.info["nodeset_imports"][0]["source_path"] == str(nodeset_path.resolve())

    result = run_workspace_checked(config_path, workspace=workspace, run_root=tmp_path / "runs", run_id="workspace-run")
    assert result.context.get("value.out")["value"] == 5

    graph, compiled, registry, resources, error = load_workspace_graph_for_export(config_path, workspace=workspace)
    assert error is None
    assert graph.nodesets["framework.add_one"].root_id == "vibetrain"
    assert tuple(registry.available()) == ("framework.add", "test.out_end", "test.seed", "test.start")
    mermaid = export_mermaid(graph, compiled=compiled, resources=resources, expand_nodesets=False)
    assert "framework.add_one" in mermaid
    assert "root: vibetrain" in mermaid
    assert "add_one.jsonc" in mermaid


def test_workspace_rejects_duplicate_root_ids_and_unknown_top_level_fields(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(project_root)
    _write_project_config(framework_root)
    workspace_path.write_text(
        json.dumps(
            {
                "roots": [
                    {"id": "dup", "path": "vibetrain"},
                    {"id": "dup", "path": "project"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(WorkspaceConfigError) as duplicate:
        load_workspace_config(workspace_path)
    assert duplicate.value.rule_id == "WORKSPACE.ROOT.DUPLICATE"

    workspace_path.write_text(json.dumps({"version": 1, "roots": [{"id": "project", "path": "project"}]}), encoding="utf-8")
    with pytest.raises(WorkspaceConfigError) as unknown:
        load_workspace_config(workspace_path)
    assert unknown.value.rule_id == "WORKSPACE.UNKNOWN_FIELD"


def test_workspace_project_config_override_and_missing_project_config(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(framework_root)
    (project_root / "custom_project_config.jsonc").write_text(
        json.dumps({"registry": "registry.py:build_node_registry", "quality_enabled": False}),
        encoding="utf-8",
    )
    workspace_path.write_text(
        json.dumps(
            {
                "roots": [
                    {"id": "vibetrain", "path": "vibetrain"},
                    {"id": "project", "path": "project", "config": "custom_project_config.jsonc"},
                ]
            }
        ),
        encoding="utf-8",
    )
    workspace = load_workspace_config(workspace_path)
    assert workspace.root_by_id("project").quality_enabled is False
    assert workspace.root_by_id("project").config_path.name == "custom_project_config.jsonc"

    (framework_root / "vibeflow_project.jsonc").unlink()
    with pytest.raises(WorkspaceConfigError) as missing:
        load_workspace_config(workspace_path)
    assert missing.value.rule_id == "WORKSPACE.PROJECT_CONFIG.MISSING"


def test_workspace_project_runtime_config_and_override_precedence(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root, runtime={"async_max_workers": 2, "async_flush_timeout": 5})
    _write_project_config(project_root, runtime={"async_max_workers": 8, "async_flush_timeout": 30})
    framework_config = framework_root / "configs" / "main.jsonc"
    project_config = project_root / "configs" / "main.jsonc"
    framework_config.parent.mkdir(parents=True)
    project_config.parent.mkdir(parents=True)
    framework_config.write_text("{}", encoding="utf-8")
    project_config.write_text("{}", encoding="utf-8")

    workspace = load_workspace_config(workspace_path)

    framework_options = _workspace_runtime_options(framework_config, workspace=workspace)
    project_options = _workspace_runtime_options(project_config, workspace=workspace)
    sparse_override = _workspace_runtime_options(
        project_config,
        workspace=workspace,
        overrides={"trace": "boundary", "async_flush_timeout": 1.5},
    )
    full_override = _workspace_runtime_options(
        project_config,
        workspace=workspace,
        overrides=RuntimeOptions(async_max_workers=3),
    )

    assert framework_options.async_max_workers == 2
    assert framework_options.async_flush_timeout == 5
    assert project_options.async_max_workers == 8
    assert project_options.async_flush_timeout == 30
    assert sparse_override.async_max_workers == 8
    assert sparse_override.async_flush_timeout == 1.5
    assert sparse_override.trace == "boundary"
    assert full_override.async_max_workers == 3
    assert full_override.async_flush_timeout is None


def test_run_workspace_checked_uses_one_effective_root_runtime_options_object(tmp_path, monkeypatch) -> None:
    import vibeflow.runner as runner_module

    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root, runtime={"async_max_workers": 2})
    _write_registry(
        project_root,
        [
            ("test.start", "StartNode", {}, {}),
            ("test.seed", "SeedNode", {"value": {"type": "number"}}, {"value": 1}),
            ("test.in_end", "InEndNode", {}, {}),
        ],
    )
    _write_project_config(project_root, runtime={"async_max_workers": 7, "async_flush_timeout": 20})
    config_path = project_root / "configs" / "main.jsonc"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts root runtime options fixture."),
                        _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                        _node_call("end", "test.in_end", "Consumes value.in.", requires=[REQ_SPEC("value.in")]),
                    ],
                    "edges": _edge_chain("start", "seed", "end"),
                    "outputs": [REQ_SPEC("value.in")],
                }
            }
        ),
        encoding="utf-8",
    )
    seen: dict[str, object] = {}
    original_refuse = runner_module._refuse_on_planned_run
    original_execute = runner_module._execute_runtime

    def record_refuse(*args, **kwargs):
        seen["refuse"] = kwargs["runtime_options"]
        return original_refuse(*args, **kwargs)

    def record_execute(graph, registry, plugin_registry, initial, run_dir, runtime_options, resources):
        seen["execute"] = runtime_options
        return original_execute(graph, registry, plugin_registry, initial, run_dir, runtime_options, resources)

    monkeypatch.setattr(runner_module, "_refuse_on_planned_run", record_refuse)
    monkeypatch.setattr(runner_module, "_execute_runtime", record_execute)

    result = run_workspace_checked(
        config_path,
        workspace=load_workspace_config(workspace_path),
        run_root=tmp_path / "runs",
        runtime_options={"trace": "boundary", "async_flush_timeout": 1.25},
    )

    assert result.context.get("value.in")["value"] == 1
    assert seen["refuse"] is seen["execute"]
    assert seen["execute"].async_max_workers == 7
    assert seen["execute"].async_flush_timeout == 1.25
    assert seen["execute"].trace == "boundary"


@pytest.mark.parametrize(
    "runtime",
    [
        [],
        {"unknown": 1},
        {"async_max_workers": 0},
        {"async_max_workers": True},
        {"async_max_workers": 1.5},
        {"async_flush_timeout": -1},
        {"async_flush_timeout": True},
        {"async_flush_timeout": "30"},
    ],
)
def test_workspace_project_runtime_config_validation(tmp_path, runtime) -> None:
    workspace_path, project_root, _ = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(project_root)
    payload = json.loads((project_root / "vibeflow_project.jsonc").read_text(encoding="utf-8"))
    payload["runtime"] = runtime
    (project_root / "vibeflow_project.jsonc").write_text(json.dumps(payload), encoding="utf-8")
    workspace_path.write_text(json.dumps({"roots": [{"id": "project", "path": "project"}]}), encoding="utf-8")

    with pytest.raises(WorkspaceConfigError) as invalid:
        load_workspace_config(workspace_path)

    assert invalid.value.rule_id == "WORKSPACE.PROJECT_CONFIG.RUNTIME"


def test_workspace_project_quality_structure_config_validation(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(framework_root)
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "registry": "registry.py:build_node_registry",
                "quality_enabled": True,
                "quality": {"structure": {"warn_code_files_per_dir": 2, "max_code_files_per_dir": 3}},
                "base_lib": {"paths": [], "modules": []},
                "plugins": [],
            }
        ),
        encoding="utf-8",
    )
    _write_registry(project_root, [])
    workspace_path.write_text(json.dumps({"roots": [{"id": "project", "path": "project"}]}), encoding="utf-8")

    workspace = load_workspace_config(workspace_path)

    assert workspace.root_by_id("project").quality_structure.warn_code_files_per_dir == 2
    assert workspace.root_by_id("project").quality_structure.max_code_files_per_dir == 3

    (project_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "registry": "registry.py:build_node_registry",
                "quality": {"structure": {"warn_code_files_per_dir": 5, "max_code_files_per_dir": 3}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(WorkspaceConfigError) as invalid:
        load_workspace_config(workspace_path)
    assert invalid.value.rule_id == "WORKSPACE.PROJECT_CONFIG.QUALITY"


def test_workspace_registry_conflicts_report_roots(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(framework_root, [("shared.node", "SeedNode", {"value": {"type": "number"}}, {"value": 1})])
    _write_registry(project_root, [("shared.node", "SeedNode", {"value": {"type": "number"}}, {"value": 2})])
    _write_project_config(framework_root)
    _write_project_config(project_root)

    workspace = load_workspace_config(workspace_path)
    with pytest.raises(WorkspaceConfigError) as conflict:
        build_workspace_node_registry(workspace)

    assert conflict.value.rule_id == "WORKSPACE.REGISTRY.DUPLICATE_TYPE_KEY"
    assert "vibetrain" in conflict.value.message
    assert "project" in conflict.value.message


def test_workspace_registry_import_and_factory_errors_are_explicit(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(framework_root)
    (project_root / "vibeflow_project.jsonc").write_text(
        json.dumps({"registry": "missing_registry.py:build_node_registry", "quality_enabled": True}),
        encoding="utf-8",
    )
    workspace_path.write_text(json.dumps({"roots": [{"id": "project", "path": "project"}]}), encoding="utf-8")

    with pytest.raises(WorkspaceConfigError) as missing_module:
        build_workspace_node_registry(load_workspace_config(workspace_path))
    assert missing_module.value.rule_id == "WORKSPACE.REGISTRY.IMPORT"

    (project_root / "registry.py").write_text("def not_registry():\n    return None\n", encoding="utf-8")
    (project_root / "vibeflow_project.jsonc").write_text(
        json.dumps({"registry": "registry.py:build_node_registry", "quality_enabled": True}),
        encoding="utf-8",
    )
    with pytest.raises(WorkspaceConfigError) as missing_factory:
        build_workspace_node_registry(load_workspace_config(workspace_path))
    assert missing_factory.value.rule_id == "WORKSPACE.REGISTRY.FACTORY"


def test_workspace_mode_rejects_config_level_policy(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(project_root, [("test.start", "StartNode", {}, {})])
    _write_project_config(project_root)
    _write_project_config(framework_root)
    config_path = project_root / "bad.jsonc"
    config_path.write_text(
        json.dumps(
                {
                    "policy": {"node_source": {"max_lines": 100}},
                    "pipeline": {"nodes": [_node_call("start", "test.start", "Starts forbidden resource config.")]},
                }
        ),
        encoding="utf-8",
    )

    report = validate_workspace_config_path(config_path, workspace=load_workspace_config(workspace_path))

    assert report.status in {"FAIL", "ERROR"}
    assert report.errors[0].rule_id == "WORKSPACE.CONFIG.FIELD_FORBIDDEN"
    assert report.errors[0].root_id == "project"
    assert report.errors[0].source_path == str(config_path.resolve())


def test_workspace_quality_scans_enabled_roots_and_annotates_findings(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root, quality_enabled=False)
    _write_project_config(project_root, quality_enabled=True)
    (project_root / "too_long.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    (framework_root / "ignored.py").write_text("x = 1\ny = 2\n", encoding="utf-8")

    report = scan_workspace_code_quality(
        load_workspace_config(workspace_path),
        thresholds=QualityThresholds(max_file_lines=1, warn_file_lines=1),
    )

    assert report.status == "FAIL"
    assert [root["id"] for root in report.workspace_roots] == ["project"]
    assert {finding.root_id for finding in report.findings} == {"project"}
    assert all(finding.source_path.startswith(str(project_root.resolve())) for finding in report.findings)


def test_workspace_quality_applies_root_structure_limits_by_default(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root, quality_enabled=False)
    _write_project_config(project_root, quality_enabled=True)
    nodes = project_root / "nodes"
    nodes.mkdir()
    for index in range(17):
        (nodes / f"part_{index}.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = scan_workspace_code_quality(load_workspace_config(workspace_path))
    finding = next(item for item in report.findings if item.rule_id == "QUALITY.STRUCTURE.DIRECTORY_TOO_MANY_CODE_FILES")

    assert report.status == "FAIL"
    assert finding.root_id == "project"
    assert finding.root_path == str(project_root.resolve())
    assert finding.source_path.endswith("project/nodes/part_0.py")


def test_workspace_quality_role_imports_use_declared_base_lib_paths_and_modules(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root, quality_enabled=False)
    _write_registry(project_root, [])
    (project_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "registry": "registry.py:build_node_registry",
                "quality_enabled": True,
                "base_lib": {
                    "paths": ["task_base_lib"],
                    "modules": [{"module": "task_base_lib.helpers"}],
                },
                "plugins": [],
            }
        ),
        encoding="utf-8",
    )
    for directory in ("nodes", "task_base_lib", "plugins"):
        package = project_root / directory
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "nodes" / "main.py").write_text("import task_base_lib.helpers\n", encoding="utf-8")
    (project_root / "task_base_lib" / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
    (project_root / "task_base_lib" / "bad.py").write_text("import plugins.policy\n", encoding="utf-8")
    (project_root / "plugins" / "policy.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = scan_workspace_code_quality(load_workspace_config(workspace_path))
    rule_ids = {finding.rule_id for finding in report.findings}

    assert "QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT" not in rule_ids
    assert "QUALITY.STRUCTURE.BASE_LIB_UPWARD_IMPORT" in rule_ids
    upward = next(finding for finding in report.findings if finding.rule_id == "QUALITY.STRUCTURE.BASE_LIB_UPWARD_IMPORT")
    assert upward.object_id == "task_base_lib.bad -> plugins.policy"
    assert upward.root_id == "project"


def test_workspace_resources_have_root_source_and_feed_policy(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(project_root, [("test.start", "StartNode", {}, {})])
    _write_registry(framework_root, [])
    base_dir = project_root / "base_lib"
    base_dir.mkdir()
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    (base_dir / "math_tools.py").write_text(
        """
from vibeflow import BaseLibInfo

BASE_LIB_INFO = BaseLibInfo("base_lib.math_tools", "Math Tools", "math", "Workspace helper.", "0.1.0")
""".strip(),
        encoding="utf-8",
    )
    plugin_path = project_root / "runtime_plugin.py"
    plugin_path.write_text(
        """
from vibeflow import PluginInfo

PLUGIN_INFO = PluginInfo("workspace_runtime", "runtime", "Workspace Runtime", "runtime", "Workspace runtime plugin.", "0.1.0")

class Plugin:
    plugin_type = "runtime"
    name = "workspace_runtime"
    priority = 10
""".strip(),
        encoding="utf-8",
    )
    _append_resource_registry(
        project_root,
        base_libs=[("math_tools", "base_lib.math_tools", "Math Tools", "Workspace helper.")],
        plugins=[("workspace_runtime", "runtime_plugin.py", "Plugin", "runtime", "Workspace Runtime", "Workspace runtime plugin.")],
    )
    _write_project_config(project_root)
    _write_project_config(framework_root)
    config_path = project_root / "configs" / "main.jsonc"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps(
            {
                "base_lib": {"modules": ["math_tools"]},
                "plugins": [{"id": "workspace_runtime"}],
                "pipeline": {"nodes": [_node_call("start", "test.start", "Starts resource flow.")]},
            }
        ),
        encoding="utf-8",
    )

    workspace = load_workspace_config(workspace_path)
    env = build_workspace_environment(workspace)
    available = env.available_resources.to_dict()
    report = validate_workspace_config_path(config_path, workspace=workspace)
    resources = report.info["resources"]

    assert available["base_lib"]["modules"][0]["root_id"] == "project"
    assert available["base_lib"]["modules"][0]["source_path"].endswith("project/vibeflow_project.jsonc")
    assert available["plugins"][0]["root_id"] == "project"
    assert resources["base_lib"]["modules"][0]["id"] == "math_tools"
    assert resources["base_lib"]["modules"][0]["source_path"].endswith("project/configs/main.jsonc")
    assert resources["plugins"][0]["id"] == "workspace_runtime"
    assert str(project_root.resolve()) in report.effective_policy["base_lib"]["allowed_paths"]
    assert "base_lib.math_tools" in report.effective_policy["base_lib"]["allowed_modules"]


def test_workspace_mermaid_hides_resources_from_unused_roots(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(project_root, [("test.start", "StartNode", {}, {}), ("test.seed", "SeedNode", {"value": {"type": "number"}}, {"value": 1}), ("test.in_end", "InEndNode", {}, {})])
    _write_registry(framework_root, [])
    framework_base = project_root / "base_lib"
    framework_base.mkdir()
    (framework_base / "__init__.py").write_text("", encoding="utf-8")
    (framework_base / "math_tools.py").write_text(
        """
from vibeflow import BaseLibInfo

BASE_LIB_INFO = BaseLibInfo("base_lib.math_tools", "Framework Math", "math", "Unused workspace helper.", "0.1.0")
""".strip(),
        encoding="utf-8",
    )
    project_plugin = project_root / "runtime_plugin.py"
    project_plugin.write_text(
        """
from vibeflow import PluginInfo

PLUGIN_INFO = PluginInfo("project_runtime", "runtime", "Project Runtime", "runtime", "Project runtime plugin.", "0.1.0")

class Plugin:
    plugin_type = "runtime"
    name = "project_runtime"
""".strip(),
        encoding="utf-8",
    )
    _append_resource_registry(
        project_root,
        base_libs=[("framework_math", "base_lib.math_tools", "Framework Math", "Unused workspace helper.")],
        plugins=[("project_runtime", "runtime_plugin.py", "Plugin", "runtime", "Project Runtime", "Project runtime plugin.")],
    )
    _write_project_config(project_root)
    _write_project_config(framework_root)
    config_path = project_root / "configs" / "main.jsonc"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({"plugins": [{"id": "project_runtime"}], "pipeline": _seed_only_pipeline()}), encoding="utf-8")

    graph, compiled, _, resources, error = load_workspace_graph_for_export(config_path, workspace=load_workspace_config(workspace_path))

    assert error is None
    assert resources.to_dict()["base_lib"]["modules"] == []
    mermaid = export_mermaid(graph, compiled=compiled, resources=resources)
    assert "Project Runtime" in mermaid
    assert "Framework Math" not in mermaid
    assert "resource_base_lib" not in mermaid


def test_workspace_unknown_resource_ids_are_preflight_errors(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(project_root, [("test.start", "StartNode", {}, {})])
    _append_resource_registry(project_root)
    _write_project_config(project_root)
    _write_project_config(framework_root)
    config_path = project_root / "configs" / "main.jsonc"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps(
            {
                "base_lib": {"modules": ["missing_base"]},
                "plugins": [{"id": "missing_plugin"}],
                "pipeline": {"nodes": [_node_call("start", "test.start", "Starts resource flow.")]},
            }
        ),
        encoding="utf-8",
    )

    report = validate_workspace_config_path(config_path, workspace=load_workspace_config(workspace_path))
    rule_ids = {finding.rule_id for finding in report.errors}

    assert report.status in {"FAIL", "ERROR"}
    assert "CONFIG.RESOURCE.UNKNOWN_BASE_LIB" in rule_ids
    assert "PLUGIN.CONFIG.UNKNOWN_RESOURCE" in rule_ids


def test_workspace_available_base_lib_does_not_allow_node_import_until_config_references_it(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root)
    for directory in ("nodes", "base_lib"):
        package = project_root / directory
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "base_lib" / "math_tools.py").write_text(
        """
from vibeflow import BaseLibInfo

BASE_LIB_INFO = BaseLibInfo("base_lib.math_tools", "Math Tools", "math", "Registered helper.", "0.1.0")
VALUE = 1
""".strip(),
        encoding="utf-8",
    )
    (project_root / "nodes" / "uses_math.py").write_text(
        """
import base_lib.math_tools
from vibeflow import DataProvider, NodeContract, NodeInfo

class UsesMathNode:
    NODE_INFO = NodeInfo("test.uses_math", "Uses Math", "test", "Imports a helper.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=(DataProvider("value.out", "value.out"),),
        output_semantics={"value.out": ("computed value",)},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"value.out": 1}
""".strip(),
        encoding="utf-8",
    )
    (project_root / "registry.py").write_text(
        """
from vibeflow import BaseLibRegistry, NodeRegistry
from tests.unit import strict_support_runtime_nodes as support
from nodes.uses_math import UsesMathNode

def build_node_registry():
    registry = NodeRegistry()
    registry.register("test.start", support.StartNode, config_schema={}, config_defaults={})
    registry.register("test.uses_math", UsesMathNode, config_schema={}, config_defaults={})
    registry.register("test.out_end", support.OutEndNode, config_schema={}, config_defaults={})
    return registry

def build_base_lib_registry():
    registry = BaseLibRegistry()
    registry.register("math_tools", module="base_lib.math_tools", display_name="Math Tools", description="Registered helper.")
    return registry
""".strip(),
        encoding="utf-8",
    )
    _write_project_config(project_root)
    config_path = project_root / "configs" / "main.jsonc"
    config_path.parent.mkdir()
    nodes = [
        _node_call("start", "test.start", "Starts flow."),
        _node_call("math", "test.uses_math", "Uses registered helper.", provides=[PROV_SPEC("value.out")]),
        _node_call("end", "test.out_end", "Ends flow.", requires=[REQ_SPEC("value.out")]),
    ]
    config_path.write_text(json.dumps({"pipeline": {"nodes": nodes, "edges": _edge_chain("start", "math", "end")}}), encoding="utf-8")

    missing = validate_workspace_config_path(config_path, workspace=load_workspace_config(workspace_path))
    config_path.write_text(
        json.dumps(
                {
                    "base_lib": {"modules": ["math_tools"]},
                    "pipeline": {"nodes": nodes, "edges": _edge_chain("start", "math", "end")},
                }
        ),
        encoding="utf-8",
    )
    referenced = validate_workspace_config_path(config_path, workspace=load_workspace_config(workspace_path))

    assert "base_lib.math_tools" not in missing.effective_policy["base_lib"]["allowed_modules"]
    assert "base_lib.math_tools" in referenced.effective_policy["base_lib"]["allowed_modules"]
    assert "NODE.BASE_LIB.BASE_LIB_UNDECLARED" not in {finding.rule_id for finding in (*referenced.errors, *referenced.warnings)}


def test_cli_workspace_validate_and_quality_default_roots(tmp_path, capsys) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(
        project_root,
        [
            ("test.start", "StartNode", {}, {}),
            ("test.seed", "SeedNode", {"value": {"type": "number"}}, {"value": 1}),
            ("test.in_end", "InEndNode", {}, {}),
        ],
    )
    _write_project_config(project_root, quality_enabled=True)
    _write_project_config(framework_root, quality_enabled=False)
    config_path = project_root / "main.jsonc"
    config_path.write_text(json.dumps({"pipeline": _seed_only_pipeline()}), encoding="utf-8")
    (project_root / "too_long.py").write_text("x = 1\ny = 2\n", encoding="utf-8")

    assert cli_main(["validate", "--workspace", str(workspace_path), "--config", str(config_path), "--json"]) == 0
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_payload["info"]["workspace"]["roots"][1]["id"] == "project"

    assert cli_main(["quality-check", "--workspace", str(workspace_path), "--json", "--max-lines", "1", "--warn-lines", "1"]) == 1
    quality_payload = json.loads(capsys.readouterr().out)
    assert [root["id"] for root in quality_payload["workspace_roots"]] == ["project"]
    assert {finding["root_id"] for finding in quality_payload["errors"] + quality_payload["warnings"]} == {"project"}


def test_cli_workspace_quality_config_error_text_output(tmp_path, capsys) -> None:
    missing_workspace = tmp_path / "missing" / "vibeflow_config.jsonc"

    assert cli_main(["quality-check", "--workspace", str(missing_workspace)]) == 1

    output = capsys.readouterr().out
    assert "ERROR" in output
    assert "CONFIG.READ" in output


def _workspace_fixture(tmp_path: Path, *, write_workspace: bool = True) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    project_root = repo / "project"
    framework_root = repo / "vibetrain"
    project_root.mkdir(parents=True)
    framework_root.mkdir(parents=True)
    workspace_path = repo / "vibeflow_config.jsonc"
    if write_workspace:
        workspace_path.write_text(
            json.dumps({"policy": {}, "roots": [{"id": "vibetrain", "path": "vibetrain"}, {"id": "project", "path": "project"}]}),
            encoding="utf-8",
        )
    return workspace_path, project_root, framework_root


def _write_project_config(root: Path, *, quality_enabled: bool = True, runtime: dict[str, object] | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "registry": "registry.py:build_node_registry",
        "quality_enabled": quality_enabled,
        "base_lib": {"paths": [], "modules": []},
        "plugins": [],
    }
    if runtime is not None:
        payload["runtime"] = runtime
    (root / "vibeflow_project.jsonc").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    if not (root / "registry.py").exists():
        _write_registry(root, [])


def _write_registry(root: Path, registrations: list[tuple[str, str, dict, dict]]) -> None:
    lines = [
        "from vibeflow import NodeRegistry",
        "from tests.unit import strict_support_runtime_nodes as nodes",
        "",
        "def build_node_registry():",
        "    registry = NodeRegistry()",
    ]
    for key, class_name, schema, defaults in registrations:
        lines.append(f"    registry.register({key!r}, nodes.{class_name}, config_schema={schema!r}, config_defaults={defaults!r})")
    lines.append("    return registry")
    lines.append("")
    root.mkdir(parents=True, exist_ok=True)
    (root / "registry.py").write_text("\n".join(lines), encoding="utf-8")


def _append_resource_registry(
    root: Path,
    *,
    base_libs: list[tuple[str, str, str, str]] = (),
    plugins: list[tuple[str, str, str, str, str, str]] = (),
) -> None:
    lines = [
        "",
        "from vibeflow import BaseLibRegistry, PluginResourceRegistry",
        "",
        "def build_base_lib_registry():",
        "    registry = BaseLibRegistry()",
    ]
    for resource_id, module, display_name, description in base_libs:
        lines.append(f"    registry.register({resource_id!r}, module={module!r}, display_name={display_name!r}, description={description!r})")
    lines.extend(
        [
            "    return registry",
            "",
            "def build_plugin_registry():",
            "    registry = PluginResourceRegistry()",
        ]
    )
    for resource_id, module, class_name, plugin_type, display_name, description in plugins:
        lines.append(
            f"    registry.register({resource_id!r}, module={module!r}, class_name={class_name!r}, plugin_type={plugin_type!r}, display_name={display_name!r}, description={description!r})"
        )
    lines.append("    return registry")
    with (root / "registry.py").open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
