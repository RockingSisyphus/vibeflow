from tests.fixtures.support.preview import preview_directory, preview_architecture, preview_snapshot
from tests.fixtures.support.strict_support import *
from tests.fixtures.support.projects import project_root
from tests.fixtures.support.rule_inspection import _valid_node_source, _inspect_node_source, write_registry_project, node_document


def _chain_declarations(modules):
    node = node_document()
    node["base_libs"] = ["test.library"]
    library = {"kind": "base_lib", "id": "test.library", "display_name": "Library",
        "description": "A declared chain of pure helper functions", "rulesets": [],
        "implementations": [{"language": "python", "targets": ["python"],
            "source": {"kind": "file", "ref": "base_lib/a.py", "export": "helper"},
            "implementation_files": [{"kind": "file", "ref": "base_lib/__init__.py"},
                *[{"kind": "file", "ref": "base_lib/" + name + ".py"} for name in modules[1:]]]}]}
    return node, library

def test_node_base_lib_dependency_chain_warning_and_error(tmp_path, capsys, monkeypatch) -> None:
    tmp_path = project_root(tmp_path)
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_base_lib_chain(tmp_path, ["a", "b", "c", "d"])
    source = _valid_node_source(
        run_body="""
        from base_lib.a import helper
        return {"demo.out": helper()}
""".rstrip()
    )
    descriptor, library = _chain_declarations(["a", "b", "c", "d"])
    code, payload = _inspect_node_source(tmp_path, capsys, source, descriptor=descriptor, additional_nodes=[library])
    assert code == 0, payload
    assert payload["health"]["status"] == "CONCERNS"
    warning = next(item for item in payload["health"]["warnings"] if item["rule_id"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP")
    assert warning["details"]["longest_chain_length"] == 5
    assert warning["details"]["longest_chain"] == ["node", "base_lib.a", "base_lib.b", "base_lib.c", "base_lib.d"]
    assert payload["base_lib_dependency_chain"]["longest_chain_length"] == 5

    deeper = project_root(tmp_path.parent / "deep")
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(deeper))
    _write_base_lib_chain(deeper, ["a", "b", "c", "d", "e", "f"])
    descriptor, library = _chain_declarations(["a", "b", "c", "d", "e", "f"])
    code, payload = _inspect_node_source(deeper, capsys, source, descriptor=descriptor, additional_nodes=[library])
    assert code == 1
    error = next(item for item in payload["health"]["errors"] if item["rule_id"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP")
    assert error["details"]["longest_chain_length"] == 7
    assert error["suggested_fix_type"] == "fix_base_lib"

def test_jsonc_loader_strips_comments_without_changing_runtime_data(tmp_path) -> None:
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        """
{
  // this comment must not become data
  "url": "http://example.test/not//comment",
  "marker": "/* not a comment */",
  /*
    block comment
  */
    "pipeline": {
    "nodes": [
      {"id": "seed", "definition_id": "test.seed", "display_name": "Seed", "description": "Produces value.in.", "provides": [{"key": "value.in", "type": "value.in"}]}
    ]
  }
}
""".strip(),
        encoding="utf-8",
    )
    document = load_config_document(config_path)
    assert document.format == "jsonc"
    assert "comment" not in document.data
    assert document.data["url"] == "http://example.test/not//comment"
    assert document.data["marker"] == "/* not a comment */"

def test_jsonc_loader_reports_unterminated_block_comment_location(tmp_path) -> None:
    config_path = tmp_path / "bad.jsonc"
    config_path.write_text('{\n  "pipeline": {},\n  /* missing end\n', encoding="utf-8")
    with pytest.raises(ConfigLoadError) as exc_info:
        load_config_document(config_path)
    exc = exc_info.value
    assert exc.rule_id == "CONFIG.JSONC.UNTERMINATED_BLOCK_COMMENT"
    assert exc.failure_layer == "syntax"
    assert exc.source_location["line"] == 3
    assert exc.source_location["column"] == 3

def test_jsonc_loader_keeps_parse_error_location_after_comments(tmp_path) -> None:
    config_path = tmp_path / "bad.jsonc"
    config_path.write_text(
        '{\n  // stable width comment\n  "pipeline": {"nodes": []},\n  "bad": [1,]\n}',
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError) as exc_info:
        load_config_document(config_path)
    exc = exc_info.value
    assert exc.rule_id == "CONFIG.JSON"
    assert exc.source_location["line"] == 4
    assert exc.source_location["column"] > 1





def test_schema_validation_rejects_invalid_pipeline_shapes() -> None:
    findings = collect_config_schema_findings(
        {
            "pipeline": {
                "nodes": [
                    {"definition_id": "test.seed"},
                    {"id": "bad_requires", "definition_id": "test.seed", "requires": "x"},
                ],
                "edges": [{"from": "a", "to": "b", "max_executions": 0}],
                "loops": [{"id": "loop", "edges": [["a", "b"]]}],
            },
            "nodeset_types": [{"id": "bad"}],
            "boundary": {"config": []},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    object_ids = {finding.object_id for finding in findings}
    assert "CONFIG.SCHEMA.NODE_MISSING_ID" in rule_ids
    assert "CONFIG.SCHEMA.NODE_REQUIRES_LIST" in rule_ids
    assert "CONFIG.LOOP_LIMITS.REMOVED" in rule_ids
    assert "CONFIG.LOOPS.REMOVED" in rule_ids
    assert "CONFIG.NODESETS.INLINE_REMOVED" in rule_ids
    assert "CONFIG.BOUNDARY.REMOVED" in rule_ids
    assert "pipeline.nodes[0].id" in object_ids


def test_cli_validate_jsonc_outputs_effective_policy(tmp_path, capsys) -> None:
    tmp_path = project_root(tmp_path)
    selection = write_registry_project(tmp_path, _registry(), ("test.start", "test.seed", "test.add", "test.out_end"))
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        """
{
  "policy": {
    "node_source": {"max_lines": 222}
  },
  "pipeline": {
    // explicit edges define the graph
    "nodes": [
      {"id": "start", "definition_id": "test.start", "display_name": "Start", "description": "Starts the flow."},
      {"id": "seed", "definition_id": "test.seed", "display_name": "Seed", "description": "Produces value.in."},
      {"id": "add", "definition_id": "test.add", "display_name": "Add", "description": "Adds value.in."},
      {"id": "end", "definition_id": "test.out_end", "display_name": "End", "description": "Ends the flow."}
    ],
    "edges": [["start", "seed"], ["seed", "add"], ["add", "end"]],
    "outputs": [{"type": "value.out", "cardinality": "exactly_one", "display_name": "Value Out"}]
  }
}
""".strip(),
        encoding="utf-8",
    )
    document = json.loads(config_path.read_text().replace("// explicit edges define the graph", ""))
    document.pop("policy")
    document["plugins"] = [selection]
    config_path.write_text(json.dumps(document), encoding="utf-8")
    workspace_path = tmp_path.parent / "vibeflow_config.jsonc"
    code = cli_main(["validate", "--config", str(config_path), "--workspace", str(workspace_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "CONCERNS"
    assert {item["code"] for item in payload["warnings"]} == {"GRAPH.SMELL.DUPLICATE_LOGIC"}
    assert payload["effective_policy"]["node_source"]["max_lines"] > 0
    assert payload["effective_policy"]["sources"] == ["kernel.default_policy"]

def test_cli_validate_bad_jsonc_reports_syntax_layer(tmp_path, capsys) -> None:
    tmp_path = project_root(tmp_path)
    config_path = tmp_path / "bad.jsonc"
    config_path.write_text('{\n  "pipeline": {"nodes": []},\n  "bad": [1,]\n}', encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["errors"][0]["rule_id"] == "CONFIG.JSON"
    assert payload["errors"][0]["failure_layer"] == "syntax"
    assert payload["errors"][0]["source_location"]["line"] == 3

def test_cli_validate_schema_error_reports_schema_layer(tmp_path, capsys) -> None:
    tmp_path = project_root(tmp_path)
    config_path = tmp_path / "bad_schema.json"
    config_path.write_text('{"pipeline": {"nodes": [{"definition_id": "test.seed"}]}}', encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "FAIL"
    assert payload["errors"][0]["rule_id"] == "CONFIG.SCHEMA.NODE_MISSING_ID"
    assert payload["errors"][0]["failure_layer"] == "schema"

def test_cli_validate_topology_error_reports_topology_layer(tmp_path, capsys) -> None:
    tmp_path = project_root(tmp_path)
    config_path = tmp_path / "bad_topology.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [{"id": "seed", "definition_id": "test.seed", "display_name": "Seed", "description": "Seed fixture."}],
                    "edges": [["seed", "missing"]],
                }
            }
        ),
        encoding="utf-8",
    )
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "FAIL"
    assert payload["errors"][0]["failure_layer"] == "topology"


def test_minimal_example_project_runs_only_through_declared_extension_points(tmp_path, monkeypatch) -> None:
    project = _repo_root() / "sandbox" / "python" / "minimal" / "project"
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(project))
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry
    registry = declared_python_registry(load_project_workspace(project), project / "configs/config.jsonc")

    result = run_checked(
        project / "configs/config.jsonc",
        run_root=tmp_path / "runs",
        run_id="minimal_example",
        preview_root=tmp_path / "preview",
    )

    assert result.context.get("value.out")["value"] == 5
    assert result.health.status == "CONCERNS"
    assert result.health.info["rule_executions"]
    assert result.health.info["effective_resources"]["base_lib"]["modules"][0]["id"] == "base_lib.math_tools"
    assert (result.run_dir / "compiled_graph.json").exists()
    assert "example.add_one" in preview_architecture(result.run_dir)["nodeset_types"]

    imported_result = run_checked(
        project / "configs/config_with_imports.jsonc",
        run_root=tmp_path / "runs",
        run_id="minimal_example_imports",
        preview_root=tmp_path / "preview",
    )
    assert imported_result.context.get("value.out")["value"] == 5
    assert imported_result.health.info["nodeset_imports"][0]["type_keys"] == ["example.add_one"]
