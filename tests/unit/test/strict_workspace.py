from tests.unit.strict_support import *

from vibeflow.workspace import (
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


def test_workspace_mode_rejects_config_level_project_resources(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(project_root, [("test.start", "StartNode", {}, {})])
    _write_project_config(project_root)
    _write_project_config(framework_root)
    config_path = project_root / "bad.jsonc"
    config_path.write_text(
        json.dumps(
            {
                "base_lib": {"paths": ["base_lib"]},
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


def test_workspace_resources_have_root_source_and_feed_policy(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(project_root, [])
    _write_registry(framework_root, [])
    base_dir = framework_root / "base_lib"
    base_dir.mkdir()
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
    (framework_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "registry": "registry.py:build_node_registry",
                "quality_enabled": True,
                "base_lib": {
                    "paths": ["base_lib"],
                    "modules": [{"module": "base_lib.math_tools", "display_name": "Math Tools", "description": "Workspace helper."}],
                },
                "plugins": [],
            }
        ),
        encoding="utf-8",
    )
    (project_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "registry": "registry.py:build_node_registry",
                "quality_enabled": True,
                "base_lib": {"paths": [], "modules": []},
                "plugins": [
                    {
                        "module": "runtime_plugin.py",
                        "class": "Plugin",
                        "type": "runtime",
                        "display_name": "Workspace Runtime",
                        "description": "Workspace runtime plugin.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    env = build_workspace_environment(load_workspace_config(workspace_path))
    resources = env.resources.to_dict()

    assert resources["base_lib"]["modules"][0]["root_id"] == "vibetrain"
    assert resources["base_lib"]["modules"][0]["source_path"].endswith("vibetrain/vibeflow_project.jsonc")
    assert resources["plugins"][0]["root_id"] == "project"
    assert resources["plugins"][0]["source_path"].endswith("project/vibeflow_project.jsonc")
    assert str((framework_root / "base_lib").resolve()) in env.effective_policy.to_dict()["base_lib"]["allowed_paths"]
    assert "base_lib.math_tools" in env.effective_policy.to_dict()["base_lib"]["allowed_modules"]


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


def _write_project_config(root: Path, *, quality_enabled: bool = True) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "registry": "registry.py:build_node_registry",
                "quality_enabled": quality_enabled,
                "base_lib": {"paths": [], "modules": []},
                "plugins": [],
            }
        ),
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
