from tests.fixtures.support.strict_support import *
from tests.fixtures.support.declarations import write_node_plugin
from tests.fixtures.support.plugins import resource, append_resource, write_lifecycle_fixture

from importlib import resources

from vibeflow.tooling.application.python.workspace_service import (
    load_workspace_graph_for_export,
    run_workspace_checked,
    validate_workspace_config_path,
)
from vibeflow.tooling.application.python.project.core import (
    build_workspace_environment,
    build_workspace_node_registry,
    load_workspace_config,
)
from vibeflow.tooling.application.python.project.project_options import _workspace_runtime_options
from vibeflow.tooling.project.architecture_types import ArchitectureDocumentSpec, WorkspaceConfigError
from vibeflow.tooling.project.config_loader import load_workspace_config_document


def test_published_config_schema_excludes_retired_host_extension_syntax() -> None:
    schema = json.loads(
        resources.files("vibeflow")
        .joinpath("tooling/project/schema/config.schema.json")
        .read_text(encoding="utf-8")
    )
    properties = schema["properties"]
    import_object = properties["nodeset_imports"]["items"]["anyOf"][1]

    assert import_object["required"] == ["path"]
    assert import_object["properties"]["root"] == {
        "type": "string",
        "minLength": 1,
    }
    assert "host_extensions" not in properties
    assert "definition_id" in schema["$defs"]["nodes"]["items"]["properties"]


def test_workspace_rejects_private_nodeset_import_from_another_root(tmp_path) -> None:
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
    _write_project_config(framework_root, source_checks=True)
    _write_project_config(project_root, source_checks=True)
    nodeset_path = framework_root / "configs" / "nodeset_types" / "add_one.jsonc"
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
                "nodeset_imports": [{"root": "framework", "path": "configs/nodeset_types/add_one.jsonc"}],
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts workspace flow."),
                        _node_call("seed", "test.seed", "Produces value.in.",  value=4),
                        _node_call("flow", "framework.add_one", "Calls framework nodeset."),
                        _node_call("end", "test.out_end", "Consumes value.out."),
                    ],
                    "edges": _edge_chain("start", "seed", "flow", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
            }
        ),
        encoding="utf-8",
    )

    workspace = load_workspace_config(workspace_path)
    _select_fixture_plugins(config_path,project_root,framework_root)
    report = validate_workspace_config_path(config_path, workspace=workspace)

    assert report.status in {"FAIL", "ERROR"}
    assert any(item.rule_id == "WORKSPACE.NODESET.PRIVATE" for item in report.errors)


def test_workspace_rejects_duplicate_root_ids_and_unknown_top_level_fields(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(project_root)
    _write_project_config(framework_root)
    workspace_path.write_text(
        json.dumps(
            {
                "roots": [
                    {"id": "dup", "path": "framework"},
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


def test_workspace_requires_an_explicit_valid_project_target(tmp_path) -> None:
    workspace_path, project_root, _ = _workspace_fixture(
        tmp_path,
        write_workspace=False,
    )
    project_config = project_root / "vibeflow_project.jsonc"
    workspace_path.write_text(
        json.dumps({"roots": [{"id": "project", "path": "project"}]}),
        encoding="utf-8",
    )

    project_config.write_text("{}", encoding="utf-8")
    with pytest.raises(WorkspaceConfigError) as missing:
        load_workspace_config(workspace_path)
    assert missing.value.rule_id == "WORKSPACE.PROJECT_TARGET.MISSING"
    assert missing.value.source_location["field"] == "project_target"

    for value in (None, "", "typescript", "Python", 1):
        project_config.write_text(
            json.dumps({"project_target": value}),
            encoding="utf-8",
        )
        with pytest.raises(WorkspaceConfigError) as invalid:
            load_workspace_config(workspace_path)
        assert invalid.value.rule_id == "WORKSPACE.PROJECT_TARGET.INVALID"
        assert invalid.value.source_location["value"] == value


@pytest.mark.parametrize(
    ("payload", "fields"),
    [
        (
            {
                "project_target": "python",
                "javascript": {"package_root": "."},
            },
            ["javascript"],
        ),
        (
            {
                "project_target": "python",
                "descriptors": {
                    "host_extensions": ["manifests/host_extensions"]
                },
            },
            ["descriptors.host_extensions"],
        ),
        (
            {
                "project_target": "javascript",
                "runtime": {},
                "base_lib": {},
                "plugins": [],
            },
            ["base_lib", "plugins", "runtime"],
        ),
    ],
)
def test_workspace_rejects_project_target_field_conflicts(
    tmp_path,
    payload,
    fields,
) -> None:
    workspace_path, project_root, _ = _workspace_fixture(
        tmp_path,
        write_workspace=False,
    )
    (project_root / "vibeflow_project.jsonc").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    workspace_path.write_text(
        json.dumps({"roots": [{"id": "project", "path": "project"}]}),
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError) as conflict:
        load_workspace_config(workspace_path)

    removed = sorted(set(payload) & {"descriptors", "registry", "base_lib", "plugins"})
    assert conflict.value.rule_id == ("PLUGIN.REGISTRATION.MIGRATION" if removed else "WORKSPACE.PROJECT_TARGET.FIELD_CONFLICT")
    assert conflict.value.source_location["fields"] == (removed or fields)


def test_workspace_root_exposes_project_target_and_rejects_cross_target_nodeset(
    tmp_path,
) -> None:
    workspace_path, python_root, javascript_root = _workspace_fixture(
        tmp_path,
        write_workspace=False,
    )
    _write_project_config(python_root)
    (javascript_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "javascript",
                "javascript": {"package_root": "."},
            }
        ),
        encoding="utf-8",
    )
    nodeset_path = javascript_root / "foreign.jsonc"
    nodeset_path.write_text(
        json.dumps(
            {
                "type_key": "foreign.group",
                "display_name": "Foreign Group",
                "description": "Belongs to another Target.",
                "requires": [],
                "provides": [],
                "pipeline": {
                    "nodes": [
                        _node_call("start", "foreign.start", "Starts foreign flow.")
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    workflow_path = python_root / "main.jsonc"
    workflow_path.write_text(
        json.dumps(
            {
                "nodeset_imports": [
                    {"root": "framework", "path": "foreign.jsonc"}
                ],
                "pipeline": {
                    "nodes": [_node_call("start", "test.start", "Starts flow.")]
                },
            }
        ),
        encoding="utf-8",
    )
    workspace_path.write_text(
        json.dumps(
            {
                "roots": [
                    {"id": "project", "path": "project"},
                    {"id": "framework", "path": "framework"},
                ]
            }
        ),
        encoding="utf-8",
    )
    workspace = load_workspace_config(workspace_path)

    assert workspace.root_by_id("project").project_target == "python"
    assert workspace.root_by_id("framework").project_target == "javascript"
    document = load_workspace_config_document(workflow_path, workspace=workspace)
    assert document.nodeset_imports[0]["import_target"] == "javascript"
    assert document.nodeset_imports[0]["source_target"] == "python"


def test_workspace_project_config_override_and_missing_project_config(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(framework_root)
    (project_root / "custom_project_config.jsonc").write_text(
        json.dumps(
            {
                "project_target": "python",

            }
        ),
        encoding="utf-8",
    )
    workspace_path.write_text(
        json.dumps(
            {
                "roots": [
                    {"id": "framework", "path": "framework"},
                    {"id": "project", "path": "project", "config": "custom_project_config.jsonc"},
                ]
            }
        ),
        encoding="utf-8",
    )
    workspace = load_workspace_config(workspace_path)
    assert workspace.root_by_id("project").config_path.name == "custom_project_config.jsonc"

    (framework_root / "vibeflow_project.jsonc").unlink()
    with pytest.raises(WorkspaceConfigError) as missing:
        load_workspace_config(workspace_path)
    assert missing.value.rule_id == "WORKSPACE.PROJECT_CONFIG.MISSING"


def test_workspace_project_runtime_config_and_override_precedence(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root, runtime={"status_interval": 2})
    _write_project_config(project_root, runtime={"status_interval": 8})
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
        overrides={"trace": "boundary", "status_interval": 5},
    )
    full_override = _workspace_runtime_options(
        project_config,
        workspace=workspace,
        overrides=RuntimeOptions(status_interval=3),
    )

    assert framework_options.status_interval == 2
    assert project_options.status_interval == 8
    assert sparse_override.status_interval == 5
    assert sparse_override.trace == "boundary"
    assert full_override.status_interval == 3


def test_run_workspace_checked_uses_one_effective_root_runtime_options_object(tmp_path, monkeypatch) -> None:
    import vibeflow.tooling.application.python.runner as runner_module

    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root, runtime={"status_interval": 2})
    _write_registry(
        project_root,
        [
            ("test.start", "StartNode", {}, {}),
            ("test.seed", "SeedNode", {"value": {"type": "number"}}, {"value": 1}),
            ("test.in_end", "InEndNode", {}, {}),
        ],
    )
    _write_project_config(project_root, runtime={"status_interval": 7})
    config_path = project_root / "configs" / "main.jsonc"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts root runtime options fixture."),
                        _node_call("seed", "test.seed", "Produces value.in."),
                        _node_call("end", "test.in_end", "Consumes value.in."),
                    ],
                    "edges": _edge_chain("start", "seed", "end"),
                    "outputs": [REQ_SPEC("value.in")],
                }
            }
        ),
        encoding="utf-8",
    )
    seen: dict[str, object] = {}
    from vibeflow.tooling.application.python import preflight
    original_refuse = preflight._refuse_on_planned_run
    from vibeflow.tooling.application.python import execution
    original_execute = execution._execute_runtime

    def record_refuse(*args, **kwargs):
        seen["refuse"] = kwargs["runtime_options"]
        return original_refuse(*args, **kwargs)

    def record_execute(graph, registry, plugin_registry, initial, run_dir, runtime_options, resources, **kwargs):
        seen["execute"] = runtime_options
        return original_execute(graph, registry, plugin_registry, initial, run_dir, runtime_options, resources, **kwargs)

    monkeypatch.setattr(preflight, "_refuse_on_planned_run", record_refuse)
    monkeypatch.setattr(execution, "_execute_runtime", record_execute)

    _select_fixture_plugins(config_path,project_root,framework_root)
    result = run_workspace_checked(
        config_path,
        workspace=load_workspace_config(workspace_path),
        run_root=tmp_path / "runs",
        runtime_options={"trace": "boundary", "status_interval": 6},
    )

    assert result.context.get("value.in")["value"] == 1
    assert seen["refuse"] is seen["execute"]
    assert seen["execute"].status_interval == 6
    assert seen["execute"].trace == "boundary"


@pytest.mark.parametrize(
    "runtime",
    [
        [],
        {"unknown": 1},
        {"nodeset_max_depth": 0},
        {"nodeset_max_depth": True},
        {"nodeset_max_depth": 1.5},
        {"async_flush_timeout": -1},
        {"async_flush_timeout": True},
        {"async_flush_timeout": "30"},
        {"nodeset_max_depth": 0},
        {"nodeset_max_depth": -1},
        {"nodeset_max_depth": True},
        {"nodeset_max_depth": 1.5},
        {"nodeset_max_depth": "4"},
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


def test_workspace_root_architecture_documents_are_normalized_and_typed(tmp_path) -> None:
    workspace_path, project_root, _ = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(project_root)
    workflow_path = project_root / "configs" / "main.jsonc"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("{}", encoding="utf-8")
    project_config_path = project_root / "vibeflow_project.jsonc"
    payload = json.loads(project_config_path.read_text(encoding="utf-8"))
    payload["architecture"] = {
        "documents": [
            {
                "workflow": "configs/./main.jsonc",
                "document": "review/ARCHITECTURE.architecture.jsonc",
            }
        ]
    }
    project_config_path.write_text(json.dumps(payload), encoding="utf-8")
    workspace_path.write_text(json.dumps({"roots": [{"id": "project", "path": "project"}]}), encoding="utf-8")

    workspace = load_workspace_config(workspace_path)
    documents = workspace.root_by_id("project").architecture_documents

    assert len(documents) == 1
    spec = documents[0]
    assert isinstance(spec, ArchitectureDocumentSpec)
    assert spec.workflow == "configs/main.jsonc"
    assert spec.document == "review/ARCHITECTURE.architecture.jsonc"
    assert spec.workflow_path == workflow_path.resolve()
    assert spec.document_path == (project_root / "review" / "ARCHITECTURE.architecture.jsonc").resolve()
    assert spec.registration_field == "architecture.documents[0]"
    assert not spec.document_path.exists()


@pytest.mark.parametrize(
    "architecture",
    [
        None,
        [],
        {},
        {"documents": []},
        {"documents": "configs/main.jsonc"},
        {"documents": [{"workflow": "configs/main.jsonc", "document": "ARCHITECTURE.jsonc"}], "unknown": True},
        {"documents": [None]},
        {"documents": [{"workflow": "configs/main.jsonc"}]},
        {"documents": [{"workflow": "configs/main.jsonc", "document": "ARCHITECTURE.jsonc", "unknown": True}]},
        {"documents": [{"workflow": "", "document": "ARCHITECTURE.jsonc"}]},
        {"documents": [{"workflow": "configs/main.jsonc", "document": 1}]},
        {"documents": [{"workflow": "configs/main.json", "document": "ARCHITECTURE.jsonc"}]},
        {"documents": [{"workflow": "configs/main.jsonc", "document": "ARCHITECTURE.md"}]},
        {"documents": [{"workflow": "../outside.jsonc", "document": "ARCHITECTURE.jsonc"}]},
        {"documents": [{"workflow": "configs/main.jsonc", "document": "../ARCHITECTURE.jsonc"}]},
        {"documents": [{"workflow": "C:\\outside\\main.jsonc", "document": "ARCHITECTURE.jsonc"}]},
    ],
)
def test_workspace_project_architecture_schema_and_paths_are_strict(tmp_path, architecture) -> None:
    workspace_path, project_root, _ = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(project_root)
    workflow_path = project_root / "configs" / "main.jsonc"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("{}", encoding="utf-8")
    project_config_path = project_root / "vibeflow_project.jsonc"
    payload = json.loads(project_config_path.read_text(encoding="utf-8"))
    payload["architecture"] = architecture
    project_config_path.write_text(json.dumps(payload), encoding="utf-8")
    workspace_path.write_text(json.dumps({"roots": [{"id": "project", "path": "project"}]}), encoding="utf-8")

    with pytest.raises(WorkspaceConfigError) as invalid:
        load_workspace_config(workspace_path)

    assert invalid.value.rule_id == "WORKSPACE.PROJECT_CONFIG.ARCHITECTURE"
    assert invalid.value.source_location["path"] == str(project_config_path.resolve())
    assert invalid.value.source_location["project_config_path"] == str(project_config_path.resolve())
    assert str(invalid.value.source_location["field"]).startswith("architecture")
    assert str(project_config_path.resolve()) in invalid.value.message
    assert str(invalid.value.source_location["field"]) in invalid.value.message


def test_workspace_project_architecture_rejects_absolute_same_and_duplicate_paths(tmp_path) -> None:
    workspace_path, project_root, _ = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(project_root)
    configs = project_root / "configs"
    configs.mkdir(parents=True)
    (configs / "main.jsonc").write_text("{}", encoding="utf-8")
    (configs / "other.jsonc").write_text("{}", encoding="utf-8")
    project_config_path = project_root / "vibeflow_project.jsonc"
    base_payload = json.loads(project_config_path.read_text(encoding="utf-8"))
    workspace_path.write_text(json.dumps({"roots": [{"id": "project", "path": "project"}]}), encoding="utf-8")
    cases = (
        {
            "documents": [
                {"workflow": str((configs / "main.jsonc").resolve()), "document": "ARCHITECTURE.jsonc"},
            ]
        },
        {"documents": [{"workflow": "configs/main.jsonc", "document": "configs/./main.jsonc"}]},
        {
            "documents": [
                {"workflow": "configs/main.jsonc", "document": "main.architecture.jsonc"},
                {"workflow": "configs/./main.jsonc", "document": "other.architecture.jsonc"},
            ]
        },
        {
            "documents": [
                {"workflow": "configs/main.jsonc", "document": "ARCHITECTURE.jsonc"},
                {"workflow": "configs/other.jsonc", "document": "./ARCHITECTURE.jsonc"},
            ]
        },
        {
            "documents": [
                {"workflow": "configs/main.jsonc", "document": "configs/other.jsonc"},
                {"workflow": "configs/other.jsonc", "document": "other.architecture.jsonc"},
            ]
        },
        {
            "documents": [
                {"workflow": "configs/main.jsonc", "document": "main.architecture.jsonc"},
                {"workflow": "configs/other.jsonc", "document": "configs/main.jsonc"},
            ]
        },
    )

    for architecture in cases:
        payload = {**base_payload, "architecture": architecture}
        project_config_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(WorkspaceConfigError) as invalid:
            load_workspace_config(workspace_path)
        assert invalid.value.rule_id == "WORKSPACE.PROJECT_CONFIG.ARCHITECTURE"
        assert "architecture.documents[" in invalid.value.message


def test_workspace_project_architecture_requires_existing_workflow_but_not_document(tmp_path) -> None:
    workspace_path, project_root, _ = _workspace_fixture(tmp_path, write_workspace=False)
    _write_project_config(project_root)
    project_config_path = project_root / "vibeflow_project.jsonc"
    payload = json.loads(project_config_path.read_text(encoding="utf-8"))
    payload["architecture"] = {
        "documents": [
            {"workflow": "configs/missing.jsonc", "document": "ARCHITECTURE.architecture.jsonc"},
        ]
    }
    project_config_path.write_text(json.dumps(payload), encoding="utf-8")
    workspace_path.write_text(json.dumps({"roots": [{"id": "project", "path": "project"}]}), encoding="utf-8")

    with pytest.raises(WorkspaceConfigError) as missing:
        load_workspace_config(workspace_path)

    assert missing.value.rule_id == "WORKSPACE.PROJECT_CONFIG.ARCHITECTURE"
    assert missing.value.source_location["field"] == "architecture.documents[0].workflow"
    assert missing.value.source_location["workflow"] == "configs/missing.jsonc"
    assert missing.value.source_location["resolved_path"] == str((project_root / "configs" / "missing.jsonc").resolve())
    assert "create or correct 'configs/missing.jsonc'" in missing.value.message


def test_workspace_nodeset_depth_limit_uses_explicit_workflow_rules(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root)
    _write_project_config(project_root)
    framework_config = framework_root / "configs" / "depth.jsonc"
    project_config = project_root / "configs" / "depth.jsonc"
    framework_config.parent.mkdir(parents=True)
    project_config.parent.mkdir(parents=True)
    _write_config_file(framework_config, _workspace_nodeset_depth_config(5))
    _write_config_file(project_config, _workspace_nodeset_depth_config(5))
    from tests.fixtures.support.rule_inspection import depth_ruleset
    for root, config, maximum in ((framework_root,framework_config,4),(project_root,project_config,5)):
        append_resource(root,depth_ruleset(maximum).to_dict())
        data=json.loads(config.read_text());data['rulesets']=['test.depth'];config.write_text(json.dumps(data))
    workspace = load_workspace_config(workspace_path)

    _select_fixture_plugins(framework_config,project_root,framework_root)
    framework_report = validate_workspace_config_path(framework_config, workspace=workspace)
    _select_fixture_plugins(project_config,project_root,framework_root)
    project_report = validate_workspace_config_path(project_config, workspace=workspace)

    framework_depth = next(error for error in framework_report.errors if error.rule_id == "NODESET.NESTING.DEPTH_EXCEEDED")
    assert framework_depth.details["limit"] == 4
    assert framework_depth.root_id == "framework"
    assert "NODESET.NESTING.DEPTH_EXCEEDED" not in {error.rule_id for error in project_report.errors}


@pytest.mark.parametrize("field", ["source_checks", "quality_enabled", "quality", "policy"])
def test_workspace_rejects_retired_quality_configuration(tmp_path, field):
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root)
    (project_root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target":"python", field:{}}))
    with pytest.raises(WorkspaceConfigError) as error:
        load_workspace_config(workspace_path)
    assert error.value.rule_id == "WORKSPACE.PROJECT_CONFIG.UNKNOWN_FIELD"


def test_same_business_definition_id_in_different_private_roots_is_independent(tmp_path):
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    for root, value in ((framework_root,1),(project_root,2)):
        _write_registry(root, [("shared.node", "SeedNode", {"value":{"type":"number"}}, {"value":value})])
        _write_project_config(root, source_checks=False)
    workspace = load_workspace_config(workspace_path)
    registry = build_workspace_node_registry(workspace, config_path=_fixture_scope(workspace))
    assert registry.available() == ["shared.node"]
    descriptor = registry.descriptor("shared.node")
    assert descriptor.contract.params_defaults["value"] == 2


def test_workspace_declaration_and_implementation_errors_are_explicit(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root)
    _write_project_config(project_root)
    _write_registry(project_root, [("test.seed", "SeedNode", {}, {})])
    path = resource(project_root,"node","test.seed")
    payload = json.loads(path.read_text())
    payload["implementations"][0]["source"]["ref"] = "missing.py"
    path.write_text(json.dumps(payload))
    from vibeflow.targets.python.project import NodeRegistryError
    with pytest.raises((WorkspaceConfigError, NodeRegistryError), match="source does not exist"):
        build_workspace_node_registry(load_workspace_config(workspace_path), config_path=_fixture_scope(load_workspace_config(workspace_path)))
    payload["implementations"][0]["source"]["ref"] = "nodes/fixture_nodes.py"
    payload["implementations"][0]["source"]["export"] = "MissingClass"
    path.write_text(json.dumps(payload))
    registry = build_workspace_node_registry(load_workspace_config(workspace_path), config_path=_fixture_scope(load_workspace_config(workspace_path)))
    with pytest.raises((AttributeError, NodeRegistryError), match="MissingClass"):
        registry.get("test.seed")


def test_workspace_declarations_cannot_import_another_roots_private_source(tmp_path):
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root, source_checks=False)
    _write_registry(project_root, [("task.private", "SeedNode", {}, {})])
    _write_project_config(project_root, source_checks=False)
    declaration = resource(project_root,"node","task.private")
    data = json.loads(declaration.read_text())
    data["implementations"][0]["source"]["ref"] = str(framework_root / "private.py")
    (framework_root / "private.py").write_text("class SeedNode: pass")
    declaration.write_text(json.dumps(data))
    workspace = load_workspace_config(workspace_path)
    build_workspace_node_registry(workspace, config_path=_fixture_scope(workspace))
    from vibeflow.tooling.project.preparation import ProjectPreparation
    (project_root / "root_rules.jsonc").write_text('{"rulesets":[{"rule_id":"vibeflow.root.resources"}]}')
    assert any(item.rule_id == "ROOT.RESOURCE.PRIVATE_IMPORT" for item in ProjectPreparation(workspace).review().findings)


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

    _select_fixture_plugins(config_path,project_root,framework_root)
    report = validate_workspace_config_path(config_path, workspace=load_workspace_config(workspace_path))

    assert report.status in {"FAIL", "ERROR"}
    assert report.errors[0].rule_id == "CONFIG.POLICY.RETIRED"
    assert report.errors[0].root_id == "project"
    assert report.errors[0].source_path == str(config_path.resolve())






@pytest.mark.parametrize("directory", ["ordinary", "nodes", "task_nodes", "custom_nodes", "base_lib", "plugins"])
def test_workspace_quality_unclaimed_source_identity_is_independent_of_directory(tmp_path, capsys, directory) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    for root in (framework_root, project_root):
        _write_project_config(root, source_checks=False)
    (project_root / directory).mkdir(exist_ok=True)
    (project_root / "utility").mkdir()
    (project_root / directory / "worker.py").write_text("from utility.math import double\ndef work(value):\n    return double(value)\n")
    (project_root / "utility/math.py").write_text("def double(value):\n    return value * 2\n")
    from vibeflow.tooling.application.python.project.source_files import collect_root_source_facts
    facts = collect_root_source_facts(project_root)
    assert not facts.findings
    files = {item.path:item for item in facts.files}
    assert f"{directory}/worker.py" in files
    assert files[f"{directory}/worker.py"].imports == ("utility.math", "utility.math.double")




def test_workspace_resources_have_root_source_and_feed_policy(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(project_root, [("test.start", "StartNode", {}, {})])
    _write_registry(framework_root, [])
    base_dir = project_root / "base_lib"
    base_dir.mkdir(exist_ok=True)
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    (base_dir / "math_tools.py").write_text(
        """
def helper():
    return 1
""".strip(),
        encoding="utf-8",
    )
    plugin_path = project_root / "runtime_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    plugin_type = "runtime"
    name = "workspace_runtime"
    priority = 10
""".strip(),
        encoding="utf-8",
    )
    lifecycle = _append_resource_registry(
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
                "plugins": lifecycle,
                "pipeline": {"nodes": [_node_call("start", "test.start", "Starts resource flow.")]},
            }
        ),
        encoding="utf-8",
    )

    workspace = load_workspace_config(workspace_path)
    _select_fixture_plugins(config_path,project_root,framework_root)
    env = build_workspace_environment(workspace, config_path=config_path)
    available = env.available_resources.to_dict()
    _select_fixture_plugins(config_path,project_root,framework_root)
    report = validate_workspace_config_path(config_path, workspace=workspace)
    resources = report.info["resources"]

    assert available["base_lib"]["modules"][0]["root_id"] == "project"
    assert available["base_lib"]["modules"][0]["source_path"].endswith("project/base_lib/code_plugin_declarations.py")
    assert available["plugins"][0]["root_id"] == "project"
    assert resources["base_lib"]["modules"][0]["id"] == "math_tools"
    assert resources["base_lib"]["modules"][0]["source_path"].endswith("project/base_lib/code_plugin_declarations.py")
    assert resources["plugins"][0]["id"] == "workspace_runtime.runtime"
    assert resources["base_lib"]["modules"][0]["module"] == "base_lib.math_tools"


def test_python_workspace_rejects_javascript_host_extension_fields(
    tmp_path,
) -> None:
    from vibeflow.tooling.application.python.presentation.architecture_document import (
        build_architecture_document,
    )

    workspace_path, project_root, framework_root = _workspace_fixture(
        tmp_path
    )
    _write_registry(
        project_root,
        [("test.start", "StartNode", {}, {})],
    )
    _write_registry(framework_root, [])
    _write_project_config(project_root)
    _write_project_config(framework_root)

    extension_source = project_root / "src" / "legacy_host.ts"
    extension_source.parent.mkdir()
    extension_source.write_text(
        (
            "export function createHostExtension() {\n"
            "  return { start() {}, stop() {} };\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    project_config_path = project_root / "vibeflow_project.jsonc"
    project_config = json.loads(project_config_path.read_text())
    project_config["javascript"] = {
        "package_root": ".",
        "external_packages": [],
        "host_extensions": ["demo.legacy_host"],
    }
    project_config_path.write_text(
        json.dumps(project_config),
        encoding="utf-8",
    )

    config_path = project_root / "configs" / "main.jsonc"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        _node_call(
                            "start",
                            "test.start",
                            "Starts the legacy Host Extension fixture.",
                        )
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError) as invalid:
        load_workspace_config(workspace_path)

    assert invalid.value.rule_id == "WORKSPACE.PROJECT_TARGET.FIELD_CONFLICT"
    assert invalid.value.source_location["fields"] == ["javascript"]


def test_workspace_mermaid_hides_resources_from_unused_roots(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_registry(project_root, [("test.start", "StartNode", {}, {}), ("test.seed", "SeedNode", {"value": {"type": "number"}}, {"value": 1}), ("test.in_end", "InEndNode", {}, {})])
    _write_registry(framework_root, [])
    framework_base = project_root / "base_lib"
    framework_base.mkdir(exist_ok=True)
    (framework_base / "__init__.py").write_text("", encoding="utf-8")
    (framework_base / "math_tools.py").write_text(
        """
def helper():
    return 1
""".strip(),
        encoding="utf-8",
    )
    project_plugin = project_root / "runtime_plugin.py"
    project_plugin.write_text(
        """
class Plugin:
    plugin_type = "runtime"
    name = "project_runtime"
""".strip(),
        encoding="utf-8",
    )
    lifecycle = _append_resource_registry(
        project_root,
        base_libs=[("framework_math", "base_lib.math_tools", "Framework Math", "Unused workspace helper.")],
        plugins=[("project_runtime", "runtime_plugin.py", "Plugin", "runtime", "Project Runtime", "Project runtime plugin.")],
    )
    _write_project_config(project_root)
    _write_project_config(framework_root)
    config_path = project_root / "configs" / "main.jsonc"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({"base_lib":{"modules":[]},"plugins": lifecycle, "pipeline": _seed_only_pipeline()}), encoding="utf-8")

    _select_fixture_plugins(config_path,project_root,framework_root)
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

    _select_fixture_plugins(config_path,project_root,framework_root)
    report = validate_workspace_config_path(config_path, workspace=load_workspace_config(workspace_path))
    rule_ids = {finding.rule_id for finding in report.errors}

    assert report.status in {"FAIL", "ERROR"}
    assert "PLUGIN.SELECTION.SOURCE" in rule_ids


def test_workspace_node_library_dependency_is_explicit(tmp_path) -> None:
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    _write_project_config(framework_root)
    package = project_root / "base_lib"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "math_tools.py").write_text("def helper():\n    return 1\n")
    (project_root / "uses_math.py").write_text('from base_lib.math_tools import helper\nclass UsesMathNode:\n    def run_pure(self,inputs,params):\n        return {"value.out":helper()}\n')
    _write_registry(project_root,[("test.start","StartNode",{},{}),("test.math","LargePredictionNode",{},{}),("test.out_end","OutEndNode",{}, {})])
    descriptor = resource(project_root,"node","test.math")
    payload = json.loads(descriptor.read_text())
    payload["implementations"][0]["source"] = {"kind":"file","ref":"uses_math.py","export":"UsesMathNode"}
    descriptor.write_text(json.dumps(payload))
    _append_resource_registry(project_root,base_libs=[("math","base_lib.math_tools","Math","Arithmetic helper.")])
    _write_project_config(project_root)
    config_path = project_root / "main.jsonc"
    config_path.write_text(json.dumps({"pipeline":{"nodes":[_node_call("start","test.start","Starts flow."),
        _node_call("math","test.math","Uses the library."),
        _node_call("end","test.out_end","Ends flow.")],"edges":_edge_chain("start","math","end")}}))
    _select_fixture_plugins(config_path,project_root,framework_root)
    _select_fixture_plugins(config_path,project_root,framework_root)
    missing = validate_workspace_config_path(config_path,workspace=load_workspace_config(workspace_path))
    payload["base_libs"] = ["math"]
    descriptor.write_text(json.dumps(payload))
    _select_fixture_plugins(config_path,project_root,framework_root)
    selection = json.loads(config_path.read_text())
    selection["base_lib"] = {"modules": ["math"]}
    config_path.write_text(json.dumps(selection))
    referenced = validate_workspace_config_path(config_path,workspace=load_workspace_config(workspace_path))
    assert "RESOURCE.REFERENCE.UNAVAILABLE" in {finding.rule_id for finding in (*missing.errors,*missing.warnings)}
    assert "RESOURCE.REFERENCE.UNDECLARED" not in {finding.rule_id for finding in (*referenced.errors,*referenced.warnings)}


def test_cli_workspace_quality_reports_all_roots_with_selected_root_rules(tmp_path, capsys):
    workspace_path, project_root, framework_root = _workspace_fixture(tmp_path)
    for root in (project_root,framework_root):
        _write_project_config(root, source_checks=False)
        (root / "root_rules.jsonc").write_text(json.dumps({"rulesets":[{"rule_id":"vibeflow.root.files"}],
            "rule_params":{"vibeflow.root.files":{"max_file_lines":1,"warn_file_lines":1}}}))
        (root / "too_long.py").write_text("x = 1\ny = 2\n")
    assert cli_main(["quality-check","--workspace",str(workspace_path),"--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert {item["root_id"] for item in payload["errors"]} == {"project","framework"}
    assert all(item["rule_id"] == "QUALITY.FILE.MAX_LINES" for item in payload["errors"])


def test_cli_workspace_quality_config_error_text_output(tmp_path, capsys) -> None:
    missing_workspace = tmp_path / "missing" / "vibeflow_config.jsonc"

    assert cli_main(["quality-check", "--workspace", str(missing_workspace)]) == 1

    output = capsys.readouterr().out
    assert "ERROR" in output
    assert "CONFIG.READ" in output


def _workspace_nodeset_depth_config(depth: int) -> dict:
    nodeset_types = [
        {
            **_nodeset_config(
                "workspace.depth.0",
                provides=["value.out"],
                pipeline={
                    "nodes": [
                        _node_call(
                            "placeholder",
                            "planned.placeholder",
                            "Provides a planned leaf for the depth fixture.",
                            status="planned",
                            flow_kind="process",
                            provides=[PROV_SPEC("value.out")],
                        )
                    ]
                },
            ),
            "status": "planned",
        }
    ]
    for index in range(1, depth):
        child = f"workspace.depth.{index - 1}"
        nodeset_types.append(
            {
                **_nodeset_config(
                    f"workspace.depth.{index}",
                    provides=["value.out"],
                    pipeline={
                        "nodes": [
                            _node_call("call", child, f"Calls {child}.")
                        ]
                    },
                ),
                "status": "planned",
            }
        )
    return {
        "nodeset_types": nodeset_types,
        "pipeline": {
            "nodes": [
                _node_call(
                    "top",
                    f"workspace.depth.{depth - 1}",
                    "Calls the workspace depth fixture.",

                )
            ]
        },
    }


def _workspace_fixture(tmp_path: Path, *, write_workspace: bool = True) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    project_root = repo / "project"
    framework_root = repo / "framework"
    project_root.mkdir(parents=True)
    framework_root.mkdir(parents=True)
    workspace_path = repo / "vibeflow_config.jsonc"
    if write_workspace:
        workspace_path.write_text(
            json.dumps({"roots": [{"id": "framework", "path": "framework"}, {"id": "project", "path": "project"}]}),
            encoding="utf-8",
        )
    return workspace_path, project_root, framework_root


def _write_project_config(root: Path, *, source_checks: bool = True, runtime: dict[str, object] | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_target": "python",
    }
    if runtime is not None:
        payload["runtime"] = runtime
    (root / "vibeflow_project.jsonc").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    (root / "root_rules.jsonc").write_text(json.dumps({"rulesets": ["vibeflow.root.default"] if source_checks else []}))
    if not (root / "plugins/code_plugin/plugin.py").exists():
        _write_registry(root, [])


def _write_registry(root: Path, registrations: list[tuple[str, str, dict, dict]]) -> None:
    return write_node_plugin(root, registrations)


def _append_resource_registry(
    root: Path,
    *,
    base_libs: list[tuple[str, str, str, str]] = (),
    plugins: list[tuple[str, str, str, str, str, str]] = (),
) -> None:
    selections = []
    for resource_id, module, display_name, description in base_libs:
        append_resource(root,{"kind":"base_lib","id":resource_id,"display_name":display_name,"description":description,
            "implementations":[{"language":"python","targets":["python"],"source":{"kind":"module","ref":module}}]})
    for resource_id, module, class_name, plugin_type, display_name, description in plugins:
        filename = "lifecycle_" + resource_id + ".py"
        selection = write_lifecycle_fixture(root,source={"kind":"file","ref":module,"export":class_name},
            plugin_id=resource_id,plugin_type=plugin_type,filename=filename)
        path = root / selection["source"]["ref"]
        path.write_text(path.read_text().replace(f"display_name={resource_id!r}",f"display_name={display_name!r}").replace('description="Native lifecycle fixture"',f"description={description!r}"))
        selections.append(selection)
    return selections


def _fixture_scope(workspace):
    """Select only the consumer root's package and business declarations."""
    from tests.fixtures.support.plugins import resource_declarations
    root = workspace.roots[-1]
    declarations = [entry for entry in resource_declarations(root.path) if entry["kind"] == "node"]
    calls = [{"id":str(index), "definition_id":entry["id"], "display_name":"Fixture", "description":"Fixture definition"}
             for index, entry in enumerate(declarations)]
    config = root.path / "fixture-scope.jsonc"
    config.write_text(json.dumps({"rulesets":[], "plugins":[{"source":{"kind":"file", "ref":"plugins/code_plugin/plugin.py"}}],
        "pipeline":{"nodes":calls}}))
    return config


def _select_fixture_plugins(config, project, framework):
    from vibeflow.tooling.project.config_loader import load_raw_config_document
    data = dict(load_raw_config_document(config).data)
    declaration = {"source":{"kind":"file","ref":"plugins/code_plugin/plugin.py","export":"plugin"}}
    selected = list(data.get("plugins", []))
    if declaration not in selected:
        selected.insert(0, declaration)
    data["plugins"] = selected
    config.write_text(json.dumps(data))
