from __future__ import annotations

import json
import shutil
from pathlib import Path

from tests.unit.strict_support import _nodeset_config, _seed_add_pipeline, _seed_only_pipeline, cli_main

from vibeflow.config.loader import load_raw_config_document
from vibeflow.rendering.architecture_document import ARCHITECTURE_DOCUMENT_HEADER
from vibeflow.workspace import load_workspace_config, run_workspace_checked, validate_workspace_config_path


def _write_architecture_workspace(
    tmp_path: Path,
    *,
    registered: bool = True,
    include_unused_nodeset: bool = False,
    include_resource: bool = False,
) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    project = repo / "project"
    configs = project / "configs"
    configs.mkdir(parents=True)
    workspace_path = repo / "vibeflow_config.jsonc"
    workflow_path = configs / "main.jsonc"
    document_path = project / "ARCHITECTURE.jsonc"

    workspace_path.write_text(
        json.dumps({"policy": {}, "roots": [{"id": "project", "path": "project"}]}),
        encoding="utf-8",
    )
    project_config: dict[str, object] = {
        "registry": "registry.py:build_node_registry",
        "quality_enabled": False,
    }
    if registered:
        project_config["architecture"] = {
            "documents": [
                {"workflow": "configs/main.jsonc", "document": "ARCHITECTURE.jsonc"}
            ]
        }
    (project / "vibeflow_project.jsonc").write_text(
        json.dumps(project_config, indent=2),
        encoding="utf-8",
    )
    registry_lines = [
        "from vibeflow import BaseLibRegistry, NodeRegistry",
        "from tests.unit import strict_support_runtime_nodes as nodes",
        "",
        "def build_node_registry():",
        "    registry = NodeRegistry()",
        "    registry.register('test.start', nodes.StartNode, config_schema={}, config_defaults={})",
        "    registry.register('test.seed', nodes.SeedNode, config_schema={'value': {'type': 'number'}}, config_defaults={'value': 1})",
        "    registry.register('test.add', nodes.AddNode, config_schema={'delta': {'type': 'number'}}, config_defaults={'delta': 1})",
        "    registry.register('test.out_end', nodes.OutEndNode, config_schema={}, config_defaults={})",
        "    registry.register('test.in_end', nodes.InEndNode, config_schema={}, config_defaults={})",
        "    return registry",
        "",
    ]
    if include_resource:
        registry_lines.extend(
            [
                "def build_base_lib_registry():",
                "    registry = BaseLibRegistry()",
                "    registry.register('fixture_lib', module='base_lib.fixture', display_name='Fixture Lib', description='Fixture resource one.')",
                "    return registry",
                "",
            ]
        )
        base_lib = project / "base_lib"
        base_lib.mkdir()
        (base_lib / "__init__.py").write_text("", encoding="utf-8")
        (base_lib / "fixture.py").write_text(
            "from vibeflow import BaseLibInfo\n\n"
            "BASE_LIB_INFO = BaseLibInfo('base_lib.fixture', 'Fixture Lib', 'test', 'Fixture resource one.', '0.1.0')\n",
            encoding="utf-8",
        )
    (project / "registry.py").write_text("\n".join(registry_lines), encoding="utf-8")
    workflow: dict[str, object] = {"pipeline": _seed_add_pipeline()}
    if include_resource:
        workflow["base_lib"] = {"modules": [{"id": "fixture_lib"}]}
    if include_unused_nodeset:
        nodeset_path = configs / "nodesets" / "unused.jsonc"
        nodeset_path.parent.mkdir()
        nodeset_path.write_text(
            json.dumps(
                _nodeset_config(
                    "fixture.unused",
                    pipeline=_seed_only_pipeline(),
                    provides=["value.in"],
                ),
                indent=2,
            ),
            encoding="utf-8",
        )
        workflow["nodeset_imports"] = [{"path": "nodesets/unused.jsonc"}]
    workflow_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    return workspace_path, workflow_path, document_path


def _export_registered_document(workspace_path: Path, workflow_path: Path, document_path: Path) -> int:
    return cli_main(
        [
            "export-architecture",
            "--workspace",
            str(workspace_path),
            "--config",
            str(workflow_path),
            "--output",
            str(document_path),
        ]
    )


def _architecture_error_rule(report) -> str:
    assert len(report.errors) == 1
    return report.errors[0].rule_id


def test_architecture_cli_stdout_contains_canonical_document(tmp_path, capsys) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path)

    code = cli_main(
        [
            "export-architecture",
            "--workspace",
            str(workspace_path),
            "--config",
            str(workflow_path),
        ]
    )
    output = capsys.readouterr().out

    assert code == 0
    assert output.startswith(ARCHITECTURE_DOCUMENT_HEADER + "{")
    assert list(json.loads(output.removeprefix(ARCHITECTURE_DOCUMENT_HEADER))) == [
        "workflow",
        "nodesets",
        "node_types",
        "resources",
    ]
    assert not document_path.exists()


def test_architecture_cli_output_and_check_are_byte_exact(tmp_path, capsys) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path)

    assert _export_registered_document(workspace_path, workflow_path, document_path) == 0
    assert capsys.readouterr().out == ""
    first = document_path.read_bytes()

    code = cli_main(
        [
            "export-architecture",
            "--workspace",
            str(workspace_path),
            "--config",
            str(workflow_path),
            "--output",
            str(document_path),
            "--check",
        ]
    )

    assert code == 0
    assert capsys.readouterr().out == ""
    assert document_path.read_bytes() == first

    document_path.write_bytes(first + b"\n")
    code = cli_main(
        [
            "export-architecture",
            "--workspace",
            str(workspace_path),
            "--config",
            str(workflow_path),
            "--output",
            str(document_path),
            "--check",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["errors"][0]["rule_id"] == "ARCHITECTURE.DOCUMENT.NON_CANONICAL"


def test_architecture_cli_creates_registered_document_parent_directories(tmp_path, capsys) -> None:
    workspace_path, workflow_path, _ = _write_architecture_workspace(tmp_path)
    project_config_path = workflow_path.parents[1] / "vibeflow_project.jsonc"
    project_config = json.loads(project_config_path.read_text(encoding="utf-8"))
    project_config["architecture"]["documents"][0]["document"] = "review/generated/ARCHITECTURE.jsonc"
    project_config_path.write_text(json.dumps(project_config, indent=2), encoding="utf-8")
    document_path = workflow_path.parents[1] / "review" / "generated" / "ARCHITECTURE.jsonc"

    code = _export_registered_document(workspace_path, workflow_path, document_path)

    assert code == 0
    assert capsys.readouterr().out == ""
    assert document_path.read_text(encoding="utf-8").startswith(ARCHITECTURE_DOCUMENT_HEADER)


def test_architecture_export_rejects_real_graph_health_errors_before_writing(tmp_path, capsys) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path)
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    seed = next(node for node in workflow["pipeline"]["nodes"] if node["id"] == "seed")
    workflow["pipeline"] = {"nodes": [seed], "edges": []}
    workflow_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    document_path.write_text("do not overwrite", encoding="utf-8")

    code = _export_registered_document(workspace_path, workflow_path, document_path)
    report = json.loads(capsys.readouterr().out)

    assert code == 1
    assert report["status"] == "FAIL"
    assert any(item["rule_id"] == "GRAPH.FLOW.MISSING_START" for item in report["errors"])
    assert all(not item["rule_id"].startswith("ARCHITECTURE.DOCUMENT.") for item in report["errors"])
    assert document_path.read_text(encoding="utf-8") == "do not overwrite"


def test_workspace_registered_architecture_missing_then_current(tmp_path) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path)
    workspace = load_workspace_config(workspace_path)

    missing = validate_workspace_config_path(workflow_path, workspace=workspace)

    assert missing.status == "FAIL"
    assert _architecture_error_rule(missing) == "ARCHITECTURE.DOCUMENT.MISSING"
    finding = missing.errors[0]
    assert finding.details["project_config_path"] == str((document_path.parent / "vibeflow_project.jsonc").resolve())
    assert finding.details["workflow_path"] == str(workflow_path.resolve())
    assert finding.details["document_path"] == str(document_path.resolve())
    assert "--output project/ARCHITECTURE.jsonc" in finding.details["regenerate_command"]

    assert _export_registered_document(workspace_path, workflow_path, document_path) == 0
    current = validate_workspace_config_path(workflow_path, workspace=workspace)

    assert current.status in {"PASS", "CONCERNS"}
    assert current.errors == ()


def test_workspace_registered_architecture_rejects_stale_document(tmp_path) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path)
    workspace = load_workspace_config(workspace_path)
    assert _export_registered_document(workspace_path, workflow_path, document_path) == 0
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["pipeline"]["nodes"][1]["description"] = "Changed architecture metadata."
    workflow_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")

    report = validate_workspace_config_path(workflow_path, workspace=workspace)

    assert report.status == "FAIL"
    assert _architecture_error_rule(report) == "ARCHITECTURE.DOCUMENT.STALE"
    assert any(path.startswith("$.workflow.nodes") for path in report.errors[0].details["difference_paths"])


def test_workspace_architecture_tracks_unused_imported_nodeset_changes(tmp_path) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(
        tmp_path,
        include_unused_nodeset=True,
    )
    assert _export_registered_document(workspace_path, workflow_path, document_path) == 0
    nodeset_path = workflow_path.parent / "nodesets" / "unused.jsonc"
    nodeset = json.loads(nodeset_path.read_text(encoding="utf-8"))
    nodeset["description"] = "Changed unused architecture definition."
    nodeset_path.write_text(json.dumps(nodeset, indent=2), encoding="utf-8")

    report = validate_workspace_config_path(
        workflow_path,
        workspace=load_workspace_config(workspace_path),
    )

    assert report.status == "FAIL"
    assert _architecture_error_rule(report) == "ARCHITECTURE.DOCUMENT.STALE"
    assert "$.nodesets.fixture.unused.description" in report.errors[0].details["difference_paths"]


def test_workspace_architecture_tracks_registry_config_default_changes(tmp_path) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path)
    assert _export_registered_document(workspace_path, workflow_path, document_path) == 0
    registry_path = document_path.parent / "registry.py"
    registry_text = registry_path.read_text(encoding="utf-8")
    registry_path.write_text(
        registry_text.replace("config_defaults={'value': 1}", "config_defaults={'value': 22}"),
        encoding="utf-8",
    )

    report = validate_workspace_config_path(
        workflow_path,
        workspace=load_workspace_config(workspace_path),
    )

    assert report.status == "FAIL"
    assert _architecture_error_rule(report) == "ARCHITECTURE.DOCUMENT.STALE"
    assert "$.node_types.test.seed.config.defaults.value" in report.errors[0].details["difference_paths"]


def test_workspace_architecture_tracks_active_resource_registration_changes(tmp_path) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(
        tmp_path,
        include_resource=True,
    )
    assert _export_registered_document(workspace_path, workflow_path, document_path) == 0
    registry_path = document_path.parent / "registry.py"
    registry_text = registry_path.read_text(encoding="utf-8")
    registry_path.write_text(
        registry_text.replace("Fixture resource one.", "Fixture resource changed substantially."),
        encoding="utf-8",
    )

    report = validate_workspace_config_path(
        workflow_path,
        workspace=load_workspace_config(workspace_path),
    )

    assert report.status == "FAIL"
    assert _architecture_error_rule(report) == "ARCHITECTURE.DOCUMENT.STALE"
    assert "$.resources.base_lib[0].description" in report.errors[0].details["difference_paths"]


def test_workspace_registered_architecture_rejects_non_canonical_document(tmp_path) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path)
    workspace = load_workspace_config(workspace_path)
    assert _export_registered_document(workspace_path, workflow_path, document_path) == 0
    document_path.write_text(document_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    report = validate_workspace_config_path(workflow_path, workspace=workspace)

    assert report.status == "FAIL"
    assert _architecture_error_rule(report) == "ARCHITECTURE.DOCUMENT.NON_CANONICAL"


def test_workspace_without_architecture_registration_keeps_previous_behavior(tmp_path) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path, registered=False)
    workspace = load_workspace_config(workspace_path)

    report = validate_workspace_config_path(workflow_path, workspace=workspace)

    assert report.status in {"PASS", "CONCERNS"}
    assert report.errors == ()
    assert not document_path.exists()


def test_workspace_architecture_gate_is_isolated_per_root(tmp_path) -> None:
    workspace_path, first_workflow, first_document = _write_architecture_workspace(tmp_path)
    repo = workspace_path.parent
    second_project = repo / "second"
    shutil.copytree(first_document.parent, second_project)
    second_workflow = second_project / "configs" / "main.jsonc"
    second_document = second_project / "ARCHITECTURE.jsonc"
    second_registry = second_project / "registry.py"
    second_registry.write_text(
        "from vibeflow import NodeRegistry\n\n"
        "def build_node_registry():\n"
        "    return NodeRegistry()\n",
        encoding="utf-8",
    )
    second_payload = json.loads(second_workflow.read_text(encoding="utf-8"))
    for node in second_payload["pipeline"]["nodes"]:
        node["type_used"] = f"second.{node['id']}"
        node["status"] = "planned"
        node["flow_kind"] = "terminal" if node["id"] in {"start", "end"} else "process"
    second_workflow.write_text(json.dumps(second_payload, indent=2), encoding="utf-8")
    workspace_path.write_text(
        json.dumps(
            {
                "policy": {},
                "roots": [
                    {"id": "first", "path": "project"},
                    {"id": "second", "path": "second"},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert _export_registered_document(workspace_path, first_workflow, first_document) == 0
    assert _export_registered_document(workspace_path, second_workflow, second_document) == 0
    first_document.write_text(first_document.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    workspace = load_workspace_config(workspace_path)

    first = validate_workspace_config_path(first_workflow, workspace=workspace)
    second = validate_workspace_config_path(second_workflow, workspace=workspace)

    assert _architecture_error_rule(first) == "ARCHITECTURE.DOCUMENT.NON_CANONICAL"
    assert second.status in {"PASS", "CONCERNS"}
    assert second.errors == ()


def test_workspace_graph_errors_precede_architecture_freshness_noise(tmp_path) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path)
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["pipeline"]["nodes"][1]["id"] = "start"
    workflow_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")

    report = validate_workspace_config_path(
        workflow_path,
        workspace=load_workspace_config(workspace_path),
    )

    assert report.status in {"FAIL", "ERROR"}
    assert report.errors
    assert all(not finding.rule_id.startswith("ARCHITECTURE.DOCUMENT.") for finding in report.errors)
    assert not document_path.exists()


def test_workspace_validate_rejects_architecture_document_with_registered_workflow_hint(tmp_path, capsys) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path)
    assert _export_registered_document(workspace_path, workflow_path, document_path) == 0
    assert capsys.readouterr().out == ""

    code = cli_main(
        [
            "validate",
            "--workspace",
            str(workspace_path),
            "--config",
            str(document_path),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["errors"][0]["rule_id"] == "CONFIG.ARCHITECTURE_DOCUMENT.NON_EXECUTABLE"
    assert str(workflow_path.resolve()) in payload["errors"][0]["message"]
    assert str((document_path.parent / "vibeflow_project.jsonc").resolve()) in payload["errors"][0]["message"]


def test_workspace_run_writes_canonical_architecture_artifact(tmp_path) -> None:
    workspace_path, workflow_path, document_path = _write_architecture_workspace(tmp_path)
    workspace = load_workspace_config(workspace_path)
    assert _export_registered_document(workspace_path, workflow_path, document_path) == 0

    result = run_workspace_checked(
        workflow_path,
        workspace=workspace,
        run_root=tmp_path / "runs",
        run_id="architecture-artifact",
    )
    artifact_path = result.run_dir / "architecture.jsonc"
    artifact = artifact_path.read_text(encoding="utf-8")

    assert artifact_path.is_file()
    assert artifact.startswith(ARCHITECTURE_DOCUMENT_HEADER + "{")
    assert artifact == document_path.read_text(encoding="utf-8")
    assert list(load_raw_config_document(artifact_path).data) == [
        "workflow",
        "nodesets",
        "node_types",
        "resources",
    ]
