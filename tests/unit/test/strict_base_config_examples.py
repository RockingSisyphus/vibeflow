from tests.unit.strict_support import *

import ast

from vibeflow import build_architecture_report
from vibeflow.purity.ast_rules import import_aliases, import_roots, qualified_call_name

def test_failure_examples_manifest_covers_absolute_guardrails(tmp_path, capsys) -> None:
    manifest = load_config_document(_repo_root() / "examples" / "failure_cases" / "cases.jsonc").data
    observed: set[str] = set()
    from tests.unit.strict_support_runtime_nodes import RouteNode as RuntimeRouteNode

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

    for case in manifest["health_cases"]:
        registry = _registry()
        register_node(registry, "test.route", RuntimeRouteNode)
        graph = parse_graph_config(case["config"])
        report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
        rule_ids = {finding.rule_id for finding in (*report.errors, *report.warnings)}
        expected_rule = str(case["expected_rule_id"])
        assert expected_rule in rule_ids
        if expected_rule.startswith("GRAPH.EDGE."):
            assert expected_rule in report.info["rule_catalog"]
        observed.add(expected_rule)

    for case in manifest["policy_cases"]:
        registry = _registry()
        graph = parse_graph_config(case["config"])
        policy = resolve_effective_policy(case["config"], config_path=tmp_path / f"{case['name']}.json").effective_policy
        report = validate_graph_health(graph, registry=registry, effective_policy=policy)
        buckets = {
            "errors": report.errors,
            "warnings": report.warnings,
            "skipped": report.skipped,
        }
        expected_rule = str(case["expected_rule_id"])
        expected_bucket = str(case["expected_bucket"])
        assert any(finding.rule_id == expected_rule for finding in buckets[expected_bucket])
        assert not any(finding.rule_id == expected_rule for finding in (*report.errors, *report.warnings))
        observed.add(expected_rule)

    for case in manifest["quality_cases"]:
        case_dir = tmp_path / str(case["name"])
        case_dir.mkdir()
        for rel_path, source in case["files"].items():
            path = case_dir / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        args = ["quality-check", "--path", str(case_dir), "--json", *case.get("args", [])]
        code = cli_main(args)
        assert code in {0, 1}
        payload = json.loads(capsys.readouterr().out)
        rule_ids = {finding["rule_id"] for finding in (*payload["errors"], *payload["warnings"])}
        if "expected_rule_id" in case:
            expected_rule = str(case["expected_rule_id"])
            assert expected_rule in rule_ids
            assert payload["summary"]["score"] < 100
            assert payload["top_offenders"]
            observed.add(expected_rule)
        if "expected_absent_rule_id" in case:
            assert str(case["expected_absent_rule_id"]) not in rule_ids

    for case in manifest["architecture_cases"]:
        registry = _registry()
        graph = parse_graph_config(case["config"])
        compiled = GraphCompiler().compile(graph, registry=registry)
        health = validate_graph_health(graph, registry=registry)
        architecture = build_architecture_report(graph, compiled=compiled)
        assert architecture["summary"]["nodes"] == len(graph.nodes)
        assert architecture["nodes"]
        assert "architecture_report" not in health.info
        observed.add("ARCHITECTURE.REPORT.OPTIONAL")

    assert {
        "source_too_large",
        "banned_call",
        "effect_call",
        "node_direct_call",
        "module_side_effect",
        "CONFIG.LOOPS.REMOVED",
        "CONFIG.BOUNDARY.REMOVED",
        "BASE_LIB.FORBIDDEN_PROJECT_IMPORT",
        "GRAPH.CYCLE.FORBIDDEN",
        "GRAPH.EDGE.DUPLICATE",
        "GRAPH.EDGE.CONFLICTING_DUPLICATE",
        "GRAPH.SMELL.CONFUSING_NODE_NAME",
        "QUALITY.FUNCTION.TOO_MANY_PARAMS",
        "QUALITY.SIDE_EFFECT.CALL",
        "ARCHITECTURE.REPORT.OPTIONAL",
    } <= observed

def test_policy_downgrade_schema_requires_audit_fields() -> None:
    findings = collect_config_schema_findings(
        {
            "policy": {
                "rules": {
                    "downgrades": [
                        {"rule_id": "GRAPH.DATA.UNCONSUMED_PROVIDER", "to": "warning", "scope": "bad"}
                    ]
                }
            },
            "pipeline": {"nodes": [_node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")])]},
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
                    pipeline=_input_add_pipeline(add={"id": "inner"}),
                )
            ],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the nodeset fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("flow", "math.add_one", "Calls the add-one nodeset.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "seed", "flow", "end"),
            },
        }
    )
    collapsed = export_mermaid(graph, expand_nodesets=False)
    expanded = export_mermaid(graph, expand_nodesets=True)
    assert "data: Value In" in collapsed
    assert "data: Value In" in expanded
    assert "flow__inner" not in collapsed
    assert "flow__inner" in expanded

def test_checked_run_artifact_integrity_cross_links_health_graph_trace(tmp_path) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": _seed_add_pipeline(seed={"value": 6}, add={"delta": 2})
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="integrity")
    compiled = json.loads((result.run_dir / "compiled_graph.json").read_text(encoding="utf-8"))
    health = json.loads((result.run_dir / "health_report.json").read_text(encoding="utf-8"))
    graph_mmd = (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    trace = [json.loads(line) for line in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]

    assert result.context.get("value.out")["value"] == 8
    assert health["status"] == result.health.status
    assert compiled["effective_edges"] == [
        {"from": "start", "to": "seed", "when": ""},
        {"from": "seed", "to": "add", "when": ""},
        {"from": "add", "to": "end", "when": ""},
    ]
    assert "data: Value In" in graph_mmd
    assert [event["node"] for event in trace if event.get("kind") == "node"] == ["start", "seed", "add", "end"]

def test_code_quality_tool_reports_file_function_dependency_and_side_effect_findings(tmp_path) -> None:
    (tmp_path / "a.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "",
                "import b",
                "",
                "def too_big(flag):",
                "    path = Path('x.txt')",
                "    if flag:",
                "        if flag > 1:",
                "            return open('x.txt').read()",
                "    path.write_text('ok')",
                "    Path('y.txt').read_text()",
                "    (path / 'child').open()",
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
            max_file_branches=1,
            max_function_lines=3,
            max_function_branches=1,
            max_function_nesting=1,
            warn_dependency_chain=2,
            max_dependency_chain=2,
        ),
        check_side_effects=True,
    )

    rule_ids = {finding.rule_id for finding in report.findings}
    assert report.status == "FAIL"
    assert "QUALITY.FILE.MAX_LINES" in rule_ids
    assert "QUALITY.FILE.TOO_MANY_BRANCHES" in rule_ids
    assert "QUALITY.FUNCTION.MAX_LINES" in rule_ids
    assert "QUALITY.FUNCTION.TOO_MANY_BRANCHES" in rule_ids
    assert "QUALITY.FUNCTION.TOO_DEEP_NESTING" in rule_ids
    assert "QUALITY.SIDE_EFFECT.CALL" in rule_ids
    side_effect_messages = [finding.message for finding in report.findings if finding.rule_id == "QUALITY.SIDE_EFFECT.CALL"]
    assert any("open" in message for message in side_effect_messages)
    assert any("write_text" in message for message in side_effect_messages)
    assert any("read_text" in message for message in side_effect_messages)
    assert "QUALITY.DEPENDENCY.CHAIN_TOO_DEEP" in rule_ids
    assert report.longest_dependency_chain == ("a", "b", "c")
    chain = next(finding for finding in report.findings if finding.rule_id == "QUALITY.DEPENDENCY.CHAIN_TOO_DEEP")
    assert chain.details["edge_import_sites"][0]["source"] == "a"
    assert chain.details["edge_import_sites"][0]["import_sites"][0]["line"] == 3
    assert report.to_dict()["summary"]["score"] < 100
    assert report.to_dict()["top_offenders"]["files"]

def test_code_quality_function_qualnames_include_classes_and_nested_functions(tmp_path) -> None:
    (tmp_path / "models.py").write_text(
        "\n".join(
            [
                "class Alpha:",
                "    def to_dict(self):",
                "        return {'value': 1}",
                "",
                "class Beta:",
                "    def to_dict(self):",
                "        return {'value': 1}",
                "",
                "def outer():",
                "    def inner():",
                "        return 1",
                "    return inner()",
            ]
        ),
        encoding="utf-8",
    )

    report = scan_code_quality(tmp_path)
    qualnames = {function.qualname for file in report.files for function in file.functions}

    assert {"Alpha.to_dict", "Beta.to_dict", "outer", "outer.inner"} <= qualnames


def test_code_quality_reports_too_many_function_params(tmp_path) -> None:
    (tmp_path / "wide.py").write_text("def too_wide(a, b, c):\n    return a + b + c\n", encoding="utf-8")

    report = scan_code_quality(tmp_path, thresholds=QualityThresholds(max_function_params=2))
    payload = report.to_dict()

    assert "QUALITY.FUNCTION.TOO_MANY_PARAMS" in {finding.rule_id for finding in report.findings}
    assert payload["top_offenders"]["functions"][0]["params"] == 3


def test_shared_ast_rules_resolve_imports_and_calls() -> None:
    tree = ast.parse("import pathlib as pl\nfrom subprocess import run as r\nr(['true'])\npl.Path('x').write_text('ok')\n")
    aliases = import_aliases(tree)
    calls = [qualified_call_name(node.func, aliases) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    roots = [root for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for root in import_roots(node)]

    assert aliases["r"] == "subprocess.run"
    assert "subprocess.run" in calls
    assert roots == ["pathlib", "subprocess"]


def test_optional_architecture_report_is_not_health_gate() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the architecture fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("add", "test.add", "Adds value.in.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "seed", "add", "end"),
            }
        }
    )
    compiled = GraphCompiler().compile(graph, registry=_registry())
    health = validate_graph_health(graph, registry=_registry())
    report = build_architecture_report(graph, compiled=compiled)
    add = next(node for node in report["nodes"] if node["id"] == "add")

    assert "architecture_report" not in health.info
    assert report["summary"]["nodes"] == 4
    assert report["summary"]["data_edges"] == 0
    assert report["entry_nodes"] == ["start"]
    assert add["affected"] == ["end"]

def test_code_quality_report_groups_files_and_findings_by_scope(tmp_path) -> None:
    src_dir = tmp_path / "src" / "demo"
    tests_dir = tmp_path / "tests"
    distribution_dir = tmp_path / "distribution"
    devtools_dir = tmp_path / "src" / "vibeflow" / "devtools"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir()
    distribution_dir.mkdir()
    devtools_dir.mkdir(parents=True)
    (src_dir / "bad.py").write_text("def side_effect():\n    return open('src.txt').read()\n", encoding="utf-8")
    (tests_dir / "bad_test.py").write_text("def side_effect():\n    return open('test.txt').read()\n", encoding="utf-8")
    (distribution_dir / "bad_dist.py").write_text("def side_effect():\n    return open('dist.txt').read()\n", encoding="utf-8")
    (tmp_path / "build_distribution.py").write_text("def side_effect():\n    return open('build.txt').read()\n", encoding="utf-8")
    (devtools_dir / "bad_tool.py").write_text("def side_effect():\n    return open('tool.txt').read()\n", encoding="utf-8")

    payload = scan_code_quality(tmp_path, check_side_effects=True).to_dict()
    scope_summary = payload["scope_summary"]

    assert scope_summary["src"]["files"] == 1
    assert scope_summary["tests"]["files"] == 0
    assert scope_summary["devtools"]["files"] == 1
    assert scope_summary["src"]["warnings"] == 1
    assert scope_summary["tests"]["warnings"] == 0
    assert scope_summary["devtools"]["warnings"] == 1
    scanned_files = {file["path"] for file in payload["files"]}
    assert "tests/bad_test.py" not in scanned_files
    assert "distribution/bad_dist.py" not in scanned_files
    assert "build_distribution.py" not in scanned_files

def test_code_quality_report_includes_directory_structure_graph(tmp_path) -> None:
    for directory in ("left", "right", "shared", "x", "y"):
        package = tmp_path / directory
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "left" / "a.py").write_text("import right.b\nimport shared.core\n", encoding="utf-8")
    (tmp_path / "right" / "b.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (tmp_path / "shared" / "core.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (tmp_path / "x" / "feature.py").write_text("import shared.core\n", encoding="utf-8")
    (tmp_path / "y" / "feature.py").write_text("import shared.core\n", encoding="utf-8")

    report = scan_code_quality(
        tmp_path,
        thresholds=QualityThresholds(max_directory_fanout=1, max_directory_fanin=1),
    )
    payload = report.to_dict()
    directories = {item["directory"]: item for item in payload["directory_graph"]}
    rule_ids = {finding.rule_id for finding in report.findings}

    assert directories["left"]["outgoing_directories"] == ["right", "shared"]
    assert sorted(directories["shared"]["incoming_directories"]) == ["left", "x", "y"]
    assert payload["structure_summary"]["directory_count"] == 5
    assert "QUALITY.STRUCTURE.DIRECTORY_FANOUT" in rule_ids
    assert "QUALITY.STRUCTURE.DIRECTORY_FANIN" in rule_ids
    fanin = next(finding for finding in report.findings if finding.rule_id == "QUALITY.STRUCTURE.DIRECTORY_FANIN")
    assert fanin.details["suggested_entry_files"] == ("__init__.py", "api.py")


def test_code_quality_root_structure_limits_report_warning_error_and_role_imports(tmp_path) -> None:
    nodes = tmp_path / "nodes"
    base_lib = tmp_path / "base_lib"
    plugins = tmp_path / "plugins"
    for directory in (nodes, base_lib, plugins):
        directory.mkdir()
        (directory / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "registry.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (nodes / "main.py").write_text("import helper\n", encoding="utf-8")
    (base_lib / "bad.py").write_text("import plugins.policy\n", encoding="utf-8")
    (plugins / "policy.py").write_text("import nodes.main\n", encoding="utf-8")
    for index in range(17):
        (nodes / f"part_{index}.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = scan_code_quality(tmp_path, structure_limits=QualityStructureLimits())
    by_rule = {finding.rule_id: finding for finding in report.findings}

    assert report.status == "FAIL"
    assert by_rule["QUALITY.STRUCTURE.DIRECTORY_TOO_MANY_CODE_FILES"].severity == "error"
    assert by_rule["QUALITY.STRUCTURE.ROOT_LEVEL_CODE_FILE"].severity == "warning"
    assert by_rule["QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT"].object_id == "nodes.main -> helper"
    assert by_rule["QUALITY.STRUCTURE.BASE_LIB_UPWARD_IMPORT"].object_id == "base_lib.bad -> plugins.policy"
    assert by_rule["QUALITY.STRUCTURE.PLUGIN_NODE_IMPORT"].object_id == "plugins.policy -> nodes.main"
    assert report.structure_summary["root_layout"]["code_files"] == 25
    assert report.structure_summary["root_layout"]["code_dirs"] == 3


def test_code_quality_path_scan_does_not_enable_root_structure_by_default(tmp_path) -> None:
    (tmp_path / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = scan_code_quality(tmp_path)

    assert report.status == "PASS"
    assert not any(finding.rule_id.startswith("QUALITY.STRUCTURE.ROOT_LEVEL") for finding in report.findings)


def test_code_quality_report_identifies_prefix_clusters(tmp_path) -> None:
    feature = tmp_path / "feature"
    feature.mkdir()
    (feature / "__init__.py").write_text("", encoding="utf-8")
    (feature / "feature.py").write_text("import feature.feature_rules\n", encoding="utf-8")
    (feature / "feature_rules.py").write_text("import feature.feature_types\n", encoding="utf-8")
    (feature / "feature_types.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text("import feature.feature_rules\n", encoding="utf-8")

    report = scan_code_quality(
        tmp_path,
        thresholds=QualityThresholds(max_prefix_cluster_files=2),
    )
    payload = report.to_dict()
    clusters = {item["cluster_name"]: item for item in payload["prefix_clusters"]}
    rule_ids = {finding.rule_id for finding in report.findings}

    assert "feature/feature" in clusters
    assert "feature.feature" in clusters["feature/feature"]["public_entry_candidates"]
    assert clusters["feature/feature"]["external_incoming_modules"] == ["consumer"]
    assert payload["structure_summary"]["prefix_cluster_count"] == 1
    assert "QUALITY.STRUCTURE.PREFIX_CLUSTER_SHOULD_BE_PACKAGE" in rule_ids
    package_finding = next(
        finding
        for finding in report.findings
        if finding.rule_id == "QUALITY.STRUCTURE.PREFIX_CLUSTER_SHOULD_BE_PACKAGE"
    )
    assert package_finding.details["suggested_package_dir"] == "feature/feature"
    assert "feature/feature/rules.py" in package_finding.details["suggested_layout"]
    assert package_finding.details["import_update_candidates"] == ("consumer",)

def test_code_quality_reports_public_entry_boundary_violations(tmp_path) -> None:
    feature = tmp_path / "feature"
    feature.mkdir()
    (feature / "__init__.py").write_text("", encoding="utf-8")
    (feature / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    (feature / "feature_helpers.py").write_text("HELPER = 1\n", encoding="utf-8")
    (feature / "feature_rules.py").write_text("RULE = 1\n", encoding="utf-8")
    (feature / "feature_visitors.py").write_text("VISITOR = 1\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "\n".join(
            [
                "import feature.feature_helpers",
                "import feature.feature_rules",
                "import feature.feature_visitors",
            ]
        ),
        encoding="utf-8",
    )

    report = scan_code_quality(
        tmp_path,
        thresholds=QualityThresholds(max_public_entry_bypass_imports=2),
    )
    rule_ids = {finding.rule_id for finding in report.findings}

    assert "QUALITY.STRUCTURE.INTERNAL_MODULE_IMPORTED_EXTERNALLY" in rule_ids
    assert "QUALITY.STRUCTURE.PUBLIC_ENTRY_BYPASSED" in rule_ids
    internal = next(
        finding
        for finding in report.findings
        if finding.rule_id == "QUALITY.STRUCTURE.INTERNAL_MODULE_IMPORTED_EXTERNALLY"
    )
    assert internal.details["import_sites"][0]["raw_import"] == "import feature.feature_helpers"
    bypass = next(finding for finding in report.findings if finding.rule_id == "QUALITY.STRUCTURE.PUBLIC_ENTRY_BYPASSED")
    assert bypass.details["import_sites"][0]["import_sites"][0]["path"] == "consumer.py"

def test_code_quality_reports_dependency_distance_violations(tmp_path) -> None:
    for directory in (
        "app/feature",
        "lib/common",
        "platform/config",
        "platform/schema",
    ):
        package = tmp_path
        for part in directory.split("/"):
            package = package / part
            package.mkdir(exist_ok=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "platform" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "lib" / "common" / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "lib" / "common" / "feature_helpers.py").write_text("HELPER = 1\n", encoding="utf-8")
    (tmp_path / "platform" / "config" / "settings.py").write_text("VALUE = 2\n", encoding="utf-8")
    (tmp_path / "platform" / "schema" / "models.py").write_text("VALUE = 3\n", encoding="utf-8")
    (tmp_path / "app" / "feature" / "worker.py").write_text(
        "\n".join(
            [
                "import lib.common.feature_helpers",
                "import platform.config.settings",
                "import platform.schema.models",
            ]
        ),
        encoding="utf-8",
    )

    report = scan_code_quality(
        tmp_path,
        thresholds=QualityThresholds(max_dependency_distance=1, max_scattered_dependency_directories=1),
    )

    rule_ids = {finding.rule_id for finding in report.findings}
    assert "QUALITY.STRUCTURE.DISTANT_INTERNAL_IMPORT" in rule_ids
    assert "QUALITY.STRUCTURE.CLUSTER_SCATTERED_DEPENDENCY" in rule_ids
    assert report.to_dict()["structure_summary"]["dependency_distance"]["max_distance"] >= 4
    distance_finding = next(
        finding
        for finding in report.findings
        if finding.rule_id == "QUALITY.STRUCTURE.DISTANT_INTERNAL_IMPORT"
    )
    assert "suggestion" in distance_finding.details
    assert distance_finding.details["import_sites"][0]["line"] == 1
    scattered = next(
        finding
        for finding in report.findings
        if finding.rule_id == "QUALITY.STRUCTURE.CLUSTER_SCATTERED_DEPENDENCY"
    )
    assert "platform.config.settings" in scattered.details["far_targets"]

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
    cycle = next(finding for finding in report.findings if finding.rule_id == "QUALITY.DEPENDENCY.CYCLE")
    assert cycle.details["edge_import_sites"][0]["import_sites"][0]["raw_import"] == "import b"
    bidirectional = next(finding for finding in report.findings if finding.rule_id == "QUALITY.DEPENDENCY.BIDIRECTIONAL")
    assert bidirectional.details["forward_import_sites"][0]["line"] == 1
    assert bidirectional.details["reverse_import_sites"][0]["line"] == 1
    duplicate = next(finding for finding in report.findings if finding.rule_id == "QUALITY.DUPLICATE.AST_FINGERPRINT")
    assert duplicate.details["fingerprint"]
    assert duplicate.details["group_size"] == 2
    assert duplicate.details["function_details"][0]["line_start"] == 3

def test_code_quality_tool_reports_python_syntax_errors(tmp_path) -> None:
    (tmp_path / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

    report = scan_code_quality(tmp_path)

    assert report.status == "FAIL"
    assert any(finding.rule_id == "QUALITY.SYNTAX.PYTHON" for finding in report.findings)

def test_cli_quality_check_json_and_text_outputs(tmp_path, capsys) -> None:
    (tmp_path / "bad.py").write_text(
        "\n".join(
            [
                "def side_effect():",
                "    return open('x.txt').read()",
                "",
                "def normalize_one(value):",
                "    result = value + 1",
                "    return result",
                "",
                "def normalize_two(item):",
                "    result = item + 1",
                "    return result",
            ]
        ),
        encoding="utf-8",
    )

    json_code = cli_main(["quality-check", "--path", str(tmp_path), "--json", "--check-side-effects"])
    json_payload = json.loads(capsys.readouterr().out)
    text_code = cli_main(["quality-check", "--path", str(tmp_path), "--check-side-effects"])
    text_output = capsys.readouterr().out

    assert json_code == 0
    assert json_payload["status"] == "CONCERNS"
    assert json_payload["scope_summary"]["other"]["warnings"] >= 1
    assert "score" in json_payload["summary"]
    assert "top_offenders" in json_payload
    assert json_payload["warnings"][0]["rule_id"] == "QUALITY.SIDE_EFFECT.CALL"
    assert text_code == 0
    assert "scopes:" in text_output
    assert "score=" in text_output
    assert "QUALITY.SIDE_EFFECT.CALL" in text_output
    assert "file:bad.py" in text_output
    assert "details:" in text_output


def test_cli_quality_structure_limits_are_explicit_for_path_scans(tmp_path, capsys) -> None:
    (tmp_path / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert cli_main(["quality-check", "--path", str(tmp_path), "--json"]) == 0
    default_payload = json.loads(capsys.readouterr().out)
    assert default_payload["errors"] == []
    assert default_payload["warnings"] == []

    assert cli_main(["quality-check", "--path", str(tmp_path), "--json", "--enable-structure-limits"]) == 0
    enabled_payload = json.loads(capsys.readouterr().out)
    assert [finding["rule_id"] for finding in enabled_payload["warnings"]] == ["QUALITY.STRUCTURE.ROOT_LEVEL_CODE_FILE"]
