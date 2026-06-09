from tests.unit.strict_support import *

def test_failure_examples_manifest_covers_absolute_guardrails(tmp_path, capsys) -> None:
    manifest = load_config_document(_repo_root() / "examples" / "failure_cases" / "cases.jsonc").data
    observed: set[str] = set()

    for case in manifest["node_cases"]:
        code, payload = _inspect_node_source(tmp_path / str(case["name"]), capsys, _failure_case_source(case))
        assert code == 1
        legacy_codes = {
            finding["details"].get("legacy_code")
            for finding in (*payload["health"]["errors"], *payload["health"]["warnings"])
        }
        expected = str(case["expected_legacy_code"])
        assert expected in legacy_codes
        observed.add(expected)

    for case in manifest["config_cases"]:
        config_path = tmp_path / f"{case['name']}.json"
        config_path.write_text(json.dumps(case["config"]), encoding="utf-8")
        code = cli_main(["validate", "--config", str(config_path), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert code == 1
        rule_ids = {finding["rule_id"] for finding in (*payload["errors"], *payload["warnings"])}
        expected_rule = str(case["expected_rule_id"])
        assert expected_rule in rule_ids
        observed.add(expected_rule)

    for case in manifest["base_lib_cases"]:
        base_dir = tmp_path / str(case["name"]) / "base_lib"
        base_dir.mkdir(parents=True)
        (base_dir / "bad.py").write_text(str(case["module_source"]), encoding="utf-8")
        report = scan_base_lib(base_dir.parent, policy=PurityPolicy(max_source_lines=1000))
        rule_ids = {finding.rule_id for finding in report.findings}
        expected_rule = str(case["expected_rule_id"])
        assert expected_rule in rule_ids
        observed.add(expected_rule)

    assert {
        "source_too_large",
        "banned_call",
        "node_direct_call",
        "GRAPH.COMPILE",
        "CONFIG.SCHEMA.BOUNDARY_CONSUMES_KEY",
        "BASE_LIB.FORBIDDEN_PROJECT_IMPORT",
    } <= observed

def test_policy_downgrade_schema_requires_audit_fields() -> None:
    findings = collect_config_schema_findings(
        {
            "policy": {
                "rules": {
                    "downgrades": [
                        {"rule_id": "GRAPH.OUTPUT.UNCONSUMED", "to": "warning", "scope": "bad"}
                    ]
                }
            },
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    assert "CONFIG.SCHEMA.POLICY_RULE_REASON" in rule_ids
    assert "CONFIG.SCHEMA.POLICY_RULE_SCOPE" in rule_ids
    assert "CONFIG.SCHEMA.POLICY_RULE_EXPIRES" in rule_ids

def test_mermaid_collapsed_and_expanded_views_share_top_level_compiled_edges() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "inputs": ["value.in"],
                        "nodes": [{"name": "inner", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]}],
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                    {"name": "flow", "type": "nodeset.math.add_one", "requires": ["value.in"], "provides": ["value.out"]},
                ]
            },
        }
    )
    collapsed = export_mermaid(graph, expand_nodesets=False)
    expanded = export_mermaid(graph, expand_nodesets=True)
    assert "seed -->|max=1| flow" in collapsed
    assert "seed -->|max=1| flow" in expanded
    assert "flow__inner" not in collapsed
    assert "flow__inner" in expanded

def test_checked_run_artifact_integrity_cross_links_health_graph_trace(tmp_path) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": 6},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 2},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="integrity")
    compiled = json.loads((result.run_dir / "compiled_graph.json").read_text(encoding="utf-8"))
    health = json.loads((result.run_dir / "health_report.json").read_text(encoding="utf-8"))
    graph_mmd = (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    trace = [json.loads(line) for line in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]

    assert result.context.get("value.out") == 8
    assert health["status"] == result.health.status
    assert compiled["effective_edges"] == [{"from": "seed", "to": "add", "max_executions": 1, "loop": ""}]
    assert "seed -->|max=1| add" in graph_mmd
    assert [event["node"] for event in trace if event.get("kind") == "node"] == ["seed", "add"]

def test_code_quality_tool_reports_file_function_dependency_and_side_effect_findings(tmp_path) -> None:
    (tmp_path / "a.py").write_text(
        "\n".join(
            [
                "import b",
                "",
                "def too_big(flag):",
                "    if flag:",
                "        if flag > 1:",
                "            return open('x.txt').read()",
                "    return 'ok'",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text("import c\n\ndef helper():\n    return 1\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("def leaf():\n    return 1\n", encoding="utf-8")

    report = scan_code_quality(
        tmp_path,
        thresholds=QualityThresholds(
            max_file_lines=5,
            warn_file_lines=4,
            max_function_lines=3,
            max_function_branches=1,
            max_function_nesting=1,
            warn_dependency_chain=2,
            max_dependency_chain=2,
        ),
    )

    rule_ids = {finding.rule_id for finding in report.findings}
    assert report.status == "FAIL"
    assert "QUALITY.FILE.MAX_LINES" in rule_ids
    assert "QUALITY.FUNCTION.MAX_LINES" in rule_ids
    assert "QUALITY.FUNCTION.TOO_MANY_BRANCHES" in rule_ids
    assert "QUALITY.FUNCTION.TOO_DEEP_NESTING" in rule_ids
    assert "QUALITY.SIDE_EFFECT.CALL" in rule_ids
    assert "QUALITY.DEPENDENCY.CHAIN_TOO_DEEP" in rule_ids
    assert report.longest_dependency_chain == ("a", "b", "c")

def test_code_quality_report_groups_files_and_findings_by_scope(tmp_path) -> None:
    src_dir = tmp_path / "src" / "demo"
    tests_dir = tmp_path / "tests"
    devtools_dir = tmp_path / "src" / "topology_kernel" / "devtools"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir()
    devtools_dir.mkdir(parents=True)
    (src_dir / "bad.py").write_text("def side_effect():\n    return open('src.txt').read()\n", encoding="utf-8")
    (tests_dir / "bad_test.py").write_text("def side_effect():\n    return open('test.txt').read()\n", encoding="utf-8")
    (devtools_dir / "bad_tool.py").write_text("def side_effect():\n    return open('tool.txt').read()\n", encoding="utf-8")

    payload = scan_code_quality(tmp_path).to_dict()
    scope_summary = payload["scope_summary"]

    assert scope_summary["src"]["files"] == 1
    assert scope_summary["tests"]["files"] == 1
    assert scope_summary["devtools"]["files"] == 1
    assert scope_summary["src"]["warnings"] == 1
    assert scope_summary["tests"]["warnings"] == 1
    assert scope_summary["devtools"]["warnings"] == 1

def test_code_quality_tool_detects_cycles_and_duplicate_function_fingerprints(tmp_path) -> None:
    (tmp_path / "a.py").write_text(
        "import b\n\ndef normalize_one(value):\n    result = value + 1\n    return result\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "import a\n\ndef normalize_two(item):\n    result = item + 1\n    return result\n",
        encoding="utf-8",
    )

    report = scan_code_quality(tmp_path)
    rule_ids = {finding.rule_id for finding in report.findings}
    assert "QUALITY.DEPENDENCY.CYCLE" in rule_ids
    assert "QUALITY.DEPENDENCY.BIDIRECTIONAL" in rule_ids
    assert "QUALITY.DUPLICATE.AST_FINGERPRINT" in rule_ids

def test_code_quality_tool_reports_python_syntax_errors(tmp_path) -> None:
    (tmp_path / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

    report = scan_code_quality(tmp_path)

    assert report.status == "FAIL"
    assert any(finding.rule_id == "QUALITY.SYNTAX.PYTHON" for finding in report.findings)

def test_cli_quality_check_json_and_text_outputs(tmp_path, capsys) -> None:
    (tmp_path / "bad.py").write_text("def side_effect():\n    return open('x.txt').read()\n", encoding="utf-8")

    json_code = cli_main(["quality-check", "--path", str(tmp_path), "--json"])
    json_payload = json.loads(capsys.readouterr().out)
    text_code = cli_main(["quality-check", "--path", str(tmp_path)])
    text_output = capsys.readouterr().out

    assert json_code == 0
    assert json_payload["status"] == "CONCERNS"
    assert json_payload["scope_summary"]["other"]["warnings"] == 1
    assert json_payload["warnings"][0]["rule_id"] == "QUALITY.SIDE_EFFECT.CALL"
    assert text_code == 0
    assert "scopes:" in text_output
    assert "QUALITY.SIDE_EFFECT.CALL" in text_output
