from tests.unit.strict_support import *

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
      {"name": "seed", "type": "test.seed", "provides": ["value.in"]}
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
    config_path.write_text(
        json.dumps(
            {
                "policy": {
                    "node_source": {"max_bytes": 3000},
                    "imports": {"allowed_roots": ["inline_allowed"]},
                    "rules": {
                        "downgrades": [
                            {
                                "rule_id": "NODE.SOURCE.MAX_LINES",
                                "to": "warning",
                                "scope": {"node": "inline"},
                                "reason": "inline",
                                "expires": "2026-12-31",
                            }
                        ]
                    },
                },
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    discovered_path.write_text(
        '{"node_source": {"max_lines": 400}, "imports": {"allowed_roots": ["discovered"]}}',
        encoding="utf-8",
    )
    explicit_path.write_text(
        json.dumps(
            {
                "policy": {
                    "node_source": {"max_lines": 250},
                    "imports": {"allowed_roots": ["explicit"]},
                    "rules": {
                        "downgrades": [
                            {
                                "rule_id": "NODE.IMPORT.BANNED",
                                "to": "info",
                                "scope": {"node": "explicit"},
                                "reason": "explicit",
                                "expires": "2026-12-31",
                            }
                        ],
                        "exemptions": [
                            {
                                "rule_id": "NODE.IMPORT.BANNED",
                                "scope": {"node": "explicit"},
                                "reason": "explicit",
                                "expires": "2026-12-31",
                            }
                        ],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    document = load_config_document(config_path)
    result = resolve_effective_policy(document.data, config_path=config_path, explicit_policy_path=explicit_path)
    policy = result.effective_policy.to_dict()
    assert result.findings == ()
    assert policy["node_source"]["max_lines"] == 250
    assert policy["node_source"]["max_bytes"] == 3000
    assert policy["imports"]["allowed_roots"] == ["inline_allowed"]
    assert len(policy["rules"]["downgrades"]) == 2
    assert len(policy["rules"]["exemptions"]) == 1
    assert policy["sources"][0] == "kernel.default_policy"
    assert f"project.policy:{discovered_path}" in policy["sources"]
    assert f"project.policy:{explicit_path}" in policy["sources"]
    assert policy["sources"][-1] == "config.inline_policy"

def test_policy_discovery_prefers_kernel_policy_over_governance(tmp_path) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text('{"pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]}}', encoding="utf-8")
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
                    {"type": "test.seed"},
                    {"name": "bad_requires", "type": "test.seed", "requires": "x"},
                ],
                "edges": [{"from": "a", "to": "b", "max_executions": 0}],
                "loops": [{"name": "loop", "edges": [["a", "b"]]}],
            },
            "nodesets": [{"name": "bad"}],
            "boundary": {"config": []},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    object_ids = {finding.object_id for finding in findings}
    assert "CONFIG.SCHEMA.NODE_MISSING_NAME" in rule_ids
    assert "CONFIG.SCHEMA.NODE_REQUIRES_LIST" in rule_ids
    assert "CONFIG.LOOP_LIMITS.REMOVED" in rule_ids
    assert "CONFIG.LOOPS.REMOVED" in rule_ids
    assert "CONFIG.SCHEMA.NODESET_PIPELINE" in rule_ids
    assert "CONFIG.BOUNDARY.REMOVED" in rule_ids
    assert "pipeline.nodes[0].name" in object_ids

def test_schema_validation_rejects_policy_bool_as_int() -> None:
    findings = collect_config_schema_findings(
        {
            "policy": {"node_source": {"max_lines": True}},
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]},
        }
    )
    assert any(finding.object_id == "policy.node_source.max_lines" for finding in findings)
    assert any(finding.rule_id == "CONFIG.SCHEMA.POLICY_POSITIVE_INT" for finding in findings)

def test_cli_validate_jsonc_outputs_effective_policy(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        """
{
  "policy": {
    "node_source": {"max_lines": 222},
    "base_lib": {"allowed_paths": ["src/shared"], "allowed_modules": ["shared.math"]}
  },
  "pipeline": {
    // data edge should be inferred
    "nodes": [
      {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
      {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]}
    ]
  }
}
""".strip(),
        encoding="utf-8",
    )
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["effective_policy"]["node_source"]["max_lines"] == 222
    assert payload["effective_policy"]["base_lib"]["allowed_modules"] == ["shared.math"]
    assert payload["effective_policy"]["sources"][-1] == "config.inline_policy"

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
    config_path.write_text('{"pipeline": {"nodes": [{"type": "test.seed"}]}}', encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "FAIL"
    assert payload["errors"][0]["rule_id"] == "CONFIG.SCHEMA.NODE_MISSING_NAME"
    assert payload["errors"][0]["failure_layer"] == "schema"

def test_cli_validate_topology_error_reports_topology_layer(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad_topology.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [{"name": "seed", "type": "test.seed"}],
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

def test_cli_export_mermaid_reads_jsonc(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        """
{
  "pipeline": {
    "nodes": [
      {"name": "start", "type": "test.start"},
      {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
      {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
      {"name": "end", "type": "test.out_end", "requires": ["value.out"]}
    ],
    "edges": [["start", "seed"], ["seed", "add"], ["add", "end"]]
  }
}
""".strip(),
        encoding="utf-8",
    )
    code = cli_main(["export-mermaid", "--config", str(config_path)])
    output = capsys.readouterr().out
    assert code == 0
    assert "flowchart TD" in output
    assert "seed --> add" in output
    assert "provides: value.in" in output


def test_cli_export_ascii_reads_jsonc(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        """
{
  "pipeline": {
    "nodes": [
      {"name": "start", "type": "test.start"},
      {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
      {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
      {"name": "end", "type": "test.out_end", "requires": ["value.out"]}
    ],
    "edges": [["start", "seed"], ["seed", "add"], ["add", "end"]]
  }
}
""".strip(),
        encoding="utf-8",
    )
    code = cli_main(["export-ascii", "--config", str(config_path)])
    output = capsys.readouterr().out
    assert code == 0
    assert "TOPOLOGY FLOWCHART" in output
    assert "seed ----> add" in output
    assert "provides=value.in" in output


def test_ascii_flowchart_distinguishes_standard_shapes() -> None:
    nodes = [
        ("start", "terminal"),
        ("input", "io"),
        ("prepare", "preparation"),
        ("call", "predefined"),
        ("route", "decision"),
        ("work", "process"),
        ("store", "data_store"),
        ("doc", "document"),
        ("end", "terminal"),
    ]
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": name, "status": "planned", "flow_kind": flow_kind}
                    for name, flow_kind in nodes
                ],
                "edges": [
                    {"from": source, "to": target, "when": "flow.route == 'ok'"}
                    if source == "route"
                    else [source, target]
                    for (source, _), (target, _) in zip(nodes, nodes[1:])
                ],
            }
        }
    )
    text = export_ascii_flowchart(graph)
    for marker in ("● START", "⇄ I/O", "INIT", "CALL", "DECISION", "PROCESS", "▣ STORE", "DOC", "~~~~~~~~"):
        assert marker in text
    assert "Node contracts:" in text

def test_cli_export_mermaid_writes_output_and_expands_nodesets(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.jsonc"
    output_path = tmp_path / "graph.mmd"
    config_path.write_text(
        json.dumps(
            {
                "nodesets": [
                    _nodeset_config(
                        "math.add_one",
                        requires=["value.in"],
                        provides=["value.out"],
                        exports=["value.out"],
                        pipeline={
                            **_input_add_pipeline(add={"name": "inner"}),
                        },
                    )
                ],
                "pipeline": {
                    "inputs": ["value.in"],
                    "nodes": [
                        {"name": "start", "type": "test.start"},
                        {"name": "input", "type": "test.value_input", "requires": ["value.in"]},
                        {
                            "name": "composite",
                            "type": "nodeset.math.add_one",
                            "requires": ["value.in"],
                            "provides": ["value.out"],
                        },
                        {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                    ],
                    "edges": _edge_chain("start", "input", "composite", "end"),
                },
            }
        ),
        encoding="utf-8",
    )
    code = cli_main(["export-mermaid", "--config", str(config_path), "--output", str(output_path), "--expand-nodesets"])
    assert capsys.readouterr().out == ""
    assert code == 0
    output = output_path.read_text(encoding="utf-8")
    assert "flowchart TD" in output
    assert 'subgraph composite__expanded["math.add_one"]' in output
    assert "composite__inner" in output

def test_cli_export_mermaid_reports_config_errors_as_health_report(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad.jsonc"
    config_path.write_text('{\n  "pipeline": {"nodes": []},\n  "bad": [1,]\n}', encoding="utf-8")
    code = cli_main(["export-mermaid", "--config", str(config_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["errors"][0]["rule_id"] == "CONFIG.JSON"
    assert payload["errors"][0]["source_location"]["line"] == 3

def test_minimal_example_project_runs_only_through_declared_extension_points(tmp_path, monkeypatch) -> None:
    project = _repo_root() / "examples" / "minimal_project"
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(project))
    module = _load_module_from_path(project / "nodes.py", "_minimal_project_nodes")
    registry = NodeRegistry()
    register_node(registry, "example.start", module.StartNode)
    register_node(registry, "example.end", module.EndNode)
    register_node(registry, "example.seed", module.SeedNode, {"value": {"type": "number"}}, {"value": 1})
    register_node(registry, "example.add", module.AddNode, {"delta": {"type": "number"}}, {"delta": 1})

    result = run_checked(
        project / "config.jsonc",
        registry=registry,
        run_root=tmp_path / "runs",
        run_id="minimal_example",
    )

    assert result.context.get("value.out") == 5
    assert result.health.status == "CONCERNS"
    assert "plugin.policy:minimal_project_policy" in result.health.effective_policy["sources"]
    assert result.health.effective_policy["base_lib"]["allowed_modules"] == ["base_lib.math_tools"]
    assert (result.run_dir / "compiled_graph.json").exists()
    assert (result.run_dir / "graph.txt").exists()
    assert (result.run_dir / "graph.mmd").exists()
    assert "nodeset.example.add_one" in (result.run_dir / "graph.mmd").read_text(encoding="utf-8")

    imported_result = run_checked(
        project / "config_with_imports.jsonc",
        registry=registry,
        run_root=tmp_path / "runs",
        run_id="minimal_example_imports",
    )
    assert imported_result.context.get("value.out") == 5
    assert imported_result.health.info["nodeset_imports"][0]["names"] == ["example.add_one"]
