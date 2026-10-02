from tests.fixtures.support.strict_support import *
from tests.fixtures.support.rule_inspection import _valid_node_source, _inspect_node_source, write_registry_project

def test_node_base_lib_dependency_chain_warning_and_error(tmp_path, capsys, monkeypatch) -> None:
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_base_lib_chain(tmp_path, ["a", "b", "c", "d"])
    policy_path = tmp_path / "kernel_policy.jsonc"
    policy_path.write_text(
        '{"base_lib": {"allowed_paths": ["base_lib"], "allowed_modules": ["base_lib.a"]}}',
        encoding="utf-8",
    )
    source = _valid_node_source(
        run_body="""
        from base_lib.a import helper
        return {"demo.out": helper()}
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source, extra_args=["--policy", str(policy_path)])
    assert code == 0
    assert payload["health"]["status"] == "CONCERNS"
    warning = next(item for item in payload["health"]["warnings"] if item["rule_id"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP")
    assert warning["details"]["longest_chain_length"] == 5
    assert warning["details"]["longest_chain"] == ["node", "base_lib.a", "base_lib.b", "base_lib.c", "base_lib.d"]
    assert payload["base_lib_dependency_chain"]["longest_chain_length"] == 5

    deeper = tmp_path / "deep"
    deeper.mkdir()
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(deeper))
    _write_base_lib_chain(deeper, ["a", "b", "c", "d", "e", "f"])
    deep_policy = deeper / "kernel_policy.jsonc"
    deep_policy.write_text(
        '{"base_lib": {"allowed_paths": ["base_lib"], "allowed_modules": ["base_lib.a"]}}',
        encoding="utf-8",
    )
    code, payload = _inspect_node_source(deeper, capsys, source, extra_args=["--policy", str(deep_policy)])
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
      {"id": "seed", "type_used": "test.seed", "display_name": "Seed", "description": "Produces value.in.", "provides": [{"key": "value.in", "type": "value.in"}]}
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

def test_policy_default_discovery_explicit_and_inline_merge_order(tmp_path) -> None:
    config_path = tmp_path / "workflow.jsonc"
    discovered_path = tmp_path / "kernel_policy.jsonc"
    explicit_path = tmp_path / "explicit_policy.jsonc"
    config_path.write_text(json.dumps({"policy": {"node_source": {"max_bytes": 3000}, "imports": {"allowed_roots": ["inline_allowed"]}},
        "pipeline": {"nodes": [_node_call("seed", "test.seed", "Produces value.in.")]}}), encoding="utf-8")
    discovered_path.write_text('{"node_source": {"max_lines": 400}, "imports": {"allowed_roots": ["discovered"]}}', encoding="utf-8")
    explicit_path.write_text('{"policy": {"node_source": {"max_lines": 250}, "imports": {"allowed_roots": ["explicit"]}}}', encoding="utf-8")
    result = resolve_effective_policy(load_config_document(config_path).data, config_path=config_path, explicit_policy_path=explicit_path)
    policy = result.effective_policy.to_dict()
    assert result.findings == ()
    assert policy["node_source"]["max_lines"] == 250
    assert policy["node_source"]["max_bytes"] == 3000
    assert policy["imports"]["allowed_roots"] == ["inline_allowed"]
    assert policy["sources"][0] == "kernel.default_policy"
    assert f"project.policy:{discovered_path}" in policy["sources"]
    assert f"project.policy:{explicit_path}" in policy["sources"]
    assert policy["sources"][-1] == "config.inline_policy"


def test_policy_diagnostic_filters_are_replaced_by_rule_graph_configuration(tmp_path) -> None:
    document = {"policy": {"rules": {"downgrades": [{"rule_id": "NODE.IMPORT.BANNED", "to": "warning"}]}}}
    result = resolve_effective_policy(document, config_path=tmp_path / "workflow.jsonc")
    assert any(item.code == "CONFIG.POLICY.RULES.REMOVED" for item in result.findings)

def test_policy_discovery_prefers_kernel_policy_over_governance(tmp_path) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text('{"pipeline": {"nodes": [{"id": "seed", "type_used": "test.seed", "display_name": "Seed", "description": "Seed fixture."}]}}', encoding="utf-8")
    (tmp_path / "kernel_policy.jsonc").write_text('{"node_source": {"max_lines": 321}}', encoding="utf-8")
    (tmp_path / "governance.jsonc").write_text('{"node_source": {"max_lines": 123}}', encoding="utf-8")
    result = resolve_effective_policy(load_config_document(config_path).data, config_path=config_path)
    policy = result.effective_policy.to_dict()
    assert policy["node_source"]["max_lines"] == 321
    assert f"project.policy:{tmp_path / 'governance.jsonc'}" not in policy["sources"]

def test_schema_validation_rejects_invalid_pipeline_shapes() -> None:
    findings = collect_config_schema_findings(
        {
            "pipeline": {
                "nodes": [
                    {"type_used": "test.seed"},
                    {"id": "bad_requires", "type_used": "test.seed", "requires": "x"},
                ],
                "edges": [{"from": "a", "to": "b", "max_executions": 0}],
                "loops": [{"id": "loop", "edges": [["a", "b"]]}],
            },
            "nodesets": [{"id": "bad"}],
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

def test_schema_validation_rejects_policy_bool_as_int() -> None:
    findings = collect_config_schema_findings(
        {
            "policy": {"node_source": {"max_lines": True}},
        "pipeline": {"nodes": [{"id": "seed", "type_used": "test.seed", "display_name": "Seed", "description": "Seed fixture."}]},
        }
    )
    assert any(finding.object_id == "policy.node_source.max_lines" for finding in findings)
    assert any(finding.rule_id == "CONFIG.SCHEMA.POLICY_POSITIVE_INT" for finding in findings)

def test_cli_validate_jsonc_outputs_effective_policy(tmp_path, capsys) -> None:
    write_registry_project(tmp_path, _registry(), ("test.start", "test.seed", "test.add", "test.out_end"))
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        """
{
  "policy": {
    "node_source": {"max_lines": 222},
    "base_lib": {"allowed_paths": ["src/shared"], "allowed_modules": ["shared.math"]}
  },
  "pipeline": {
    // explicit edges define the graph
    "nodes": [
      {"id": "start", "type_used": "test.start", "display_name": "Start", "description": "Starts the flow."},
      {"id": "seed", "type_used": "test.seed", "display_name": "Seed", "description": "Produces value.in."},
      {"id": "add", "type_used": "test.add", "display_name": "Add", "description": "Adds value.in."},
      {"id": "end", "type_used": "test.out_end", "display_name": "End", "description": "Ends the flow."}
    ],
    "edges": [["start", "seed"], ["seed", "add"], ["add", "end"]],
    "outputs": [{"type": "value.out", "cardinality": "exactly_one", "display_name": "Value Out"}]
  }
}
""".strip(),
        encoding="utf-8",
    )
    document = json.loads(config_path.read_text().replace("// explicit edges define the graph", ""))
    policy = document.pop("policy")
    config_path.write_text(json.dumps(document), encoding="utf-8")
    workspace_path = tmp_path / "vibeflow_config.jsonc"
    workspace_path.write_text(json.dumps({"policy": policy, "roots": [{"id": "project", "path": "."}]}), encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path), "--workspace", str(workspace_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "CONCERNS"
    assert {item["code"] for item in payload["warnings"]} == {"GRAPH.SMELL.DUPLICATE_LOGIC"}
    assert payload["effective_policy"]["node_source"]["max_lines"] == 222
    assert payload["effective_policy"]["base_lib"]["allowed_modules"] == ["shared.math"]
    assert payload["effective_policy"]["sources"][-1] == f"workspace.policy:{workspace_path}"

def test_cli_validate_bad_jsonc_reports_syntax_layer(tmp_path, capsys) -> None:
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
    config_path = tmp_path / "bad_schema.json"
    config_path.write_text('{"pipeline": {"nodes": [{"type_used": "test.seed"}]}}', encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "FAIL"
    assert payload["errors"][0]["rule_id"] == "CONFIG.SCHEMA.NODE_MISSING_ID"
    assert payload["errors"][0]["failure_layer"] == "schema"

def test_cli_validate_topology_error_reports_topology_layer(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad_topology.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [{"id": "seed", "type_used": "test.seed", "display_name": "Seed", "description": "Seed fixture."}],
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

def test_cli_validate_explicit_policy_path_and_inspect_config(tmp_path, capsys) -> None:
    write_registry_project(tmp_path, _registry(), ("test.start", "test.seed", "test.add", "test.out_end"))
    config_path = tmp_path / "workflow.json"
    policy_path = tmp_path / "policy.jsonc"
    config_path.write_text(
        json.dumps(
            {"pipeline": _seed_add_pipeline()}
        ),
        encoding="utf-8",
    )
    policy_path.write_text('{"node_source": {"max_lines": 111}}', encoding="utf-8")
    code = cli_main(["inspect-config", "--config", str(config_path), "--policy", str(policy_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["health"]["effective_policy"]["node_source"]["max_lines"] == 111
    assert payload["config"]["effective_edges"] == [
        {"from": "start", "to": "seed", "when": ""},
        {"from": "seed", "to": "add", "when": ""},
        {"from": "add", "to": "end", "when": ""},
    ]

def test_minimal_example_project_runs_only_through_declared_extension_points(tmp_path, monkeypatch) -> None:
    project = _repo_root() / "sandbox" / "python" / "minimal"
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(project))
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry
    registry = declared_python_registry(load_project_workspace(project))

    result = run_checked(
        project / "config.jsonc",
        registry=registry,
        run_root=tmp_path / "runs",
        run_id="minimal_example",
    )

    assert result.context.get("value.out")["value"] == 5
    assert result.health.status == "CONCERNS"
    assert result.health.info["rule_executions"]
    assert result.health.effective_policy["base_lib"]["allowed_modules"] == ["base_lib.math_tools"]
    assert (result.run_dir / "compiled_graph.json").exists()
    assert (result.run_dir / "graph.txt").exists()
    assert (result.run_dir / "graph.mmd").exists()
    assert "type_key: example.add_one" in (result.run_dir / "graph.mmd").read_text(encoding="utf-8")

    imported_result = run_checked(
        project / "config_with_imports.jsonc",
        registry=registry,
        run_root=tmp_path / "runs",
        run_id="minimal_example_imports",
    )
    assert imported_result.context.get("value.out")["value"] == 5
    assert imported_result.health.info["nodeset_imports"][0]["type_keys"] == ["example.add_one"]
