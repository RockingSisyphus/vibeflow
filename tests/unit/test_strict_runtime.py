from tests.unit.strict_support import *

def test_checked_run_refuses_failed_health_before_runtime(tmp_path) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text(
        json.dumps({"pipeline": {"nodes": [{"name": "missing", "type": "test.missing", "provides": ["value.out"]}]}}),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="bad_run")
    result = exc_info.value.result
    assert result.health.status == "FAIL"
    assert any(error.rule_id == "NODE.TYPE.UNKNOWN" for error in result.health.errors)
    assert (result.run_dir / "health_report.json").exists()
    assert (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8") == ""

def test_checked_run_writes_runtime_failure_trace(tmp_path) -> None:
    config_path = tmp_path / "runtime_fail.json"
    config_path.write_text(
        json.dumps({"pipeline": {"nodes": [{"name": "nan", "type": "test.nan_output", "provides": ["value.out"]}]}}),
        encoding="utf-8",
    )
    with pytest.raises(PipelineRuntimeError, match="not JSON snapshot serializable"):
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="runtime_fail")
    trace_lines = [
        json.loads(line)
        for line in (tmp_path / "runs" / "runtime_fail" / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert trace_lines[0]["kind"] == "node_failed"
    assert "not JSON snapshot serializable" in trace_lines[0]["failure"]
    assert trace_lines[-1]["kind"] == "runtime_summary"

def test_checked_run_trace_records_nodeset_enter_exit(tmp_path) -> None:
    config_path = tmp_path / "nodeset_workflow.json"
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
                            "inputs": ["value.in"],
                            "nodes": [
                                {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]}
                            ],
                        },
                    )
                ],
                "pipeline": {
                    "inputs": ["value.in"],
                    "nodes": [
                        {
                            "name": "composite",
                            "type": "nodeset.math.add_one",
                            "requires": ["value.in"],
                            "provides": ["value.out"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(
        config_path,
        registry=_registry(),
        initial={"value": {"in": 2}},
        run_root=tmp_path / "runs",
        run_id="nodeset_run",
    )
    assert result.context.get("value.out") == 3
    trace_kinds = [
        json.loads(line)["kind"]
        for line in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "nodeset_enter" in trace_kinds
    assert "nodeset_exit" in trace_kinds

def test_cli_run_uses_checked_run_and_refuses_without_registered_nodes(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps({"pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]}}),
        encoding="utf-8",
    )
    code = cli_main(
        [
            "run",
            "--config",
            str(config_path),
            "--run-root",
            str(tmp_path / "runs"),
            "--run-id",
            "cli_run",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "FAIL"
    run_dir = Path(payload["run_dir"])
    assert (run_dir / "health_report.json").exists()
    assert payload["health"]["errors"][0]["rule_id"] == "NODE.TYPE.UNKNOWN"

def test_cli_run_succeeds_with_global_registry_and_writes_artifacts(tmp_path, capsys) -> None:
    from topology_kernel.registry import GLOBAL_NODE_REGISTRY

    original = dict(getattr(GLOBAL_NODE_REGISTRY, "_registry"))
    GLOBAL_NODE_REGISTRY.register("test.seed", SeedNode, overwrite=True)
    try:
        config_path = tmp_path / "workflow.json"
        input_path = tmp_path / "input.json"
        config_path.write_text(
            json.dumps({"pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": 9}]}}),
            encoding="utf-8",
        )
        input_path.write_text("{}", encoding="utf-8")
        code = cli_main(
            [
                "run",
                "--config",
                str(config_path),
                "--input",
                str(input_path),
                "--run-root",
                str(tmp_path / "runs"),
                "--run-id",
                "cli_ok",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
    finally:
        getattr(GLOBAL_NODE_REGISTRY, "_registry").clear()
        getattr(GLOBAL_NODE_REGISTRY, "_registry").update(original)
    assert code == 0
    assert payload["status"] in {"PASS", "CONCERNS"}
    run_dir = Path(payload["run_dir"])
    for name in ("compiled_graph.json", "health_report.json", "graph.mmd", "runtime_trace.jsonl", "output_summary.json"):
        assert (run_dir / name).exists()

def test_policy_plugin_tightens_effective_policy_and_health_uses_it(tmp_path) -> None:
    plugin_path = tmp_path / "tight_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "tight_policy"
    priority = 1

    def extend_policy(self, policy):
        return {"node_source": {"max_lines": 1}}
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_tight")
    payload = exc_info.value.result.health.to_dict()
    assert payload["effective_policy"]["node_source"]["max_lines"] == 1
    assert "plugin.policy:tight_policy" in payload["effective_policy"]["sources"]
    assert any(error["details"].get("legacy_code") == "source_too_large" for error in payload["errors"])

def test_policy_plugin_relaxation_requires_audited_downgradeable_rule(tmp_path) -> None:
    plugin_path = tmp_path / "relax_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "relax_policy"

    def extend_policy(self, policy):
        return {"imports": {"allowed_roots": ["numpy"]}}
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_relax")
    assert exc_info.value.result.health.status == "ERROR"
    assert any(error.rule_id == "PLUGIN.POLICY.RELAXATION_REQUIRED" for error in exc_info.value.result.health.errors)

def test_policy_plugin_allows_audited_downgradeable_relaxation(tmp_path) -> None:
    plugin_path = tmp_path / "audited_relax_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "audited_relax_policy"

    def extend_policy(self, policy):
        return {
            "policy": {
                "rules": {
                    "downgrades": [
                        {
                            "rule_id": "GRAPH.OUTPUT.UNCONSUMED",
                            "to": "warning",
                            "scope": {"pipeline": "demo"},
                            "reason": "documented project preference",
                            "expires": "2026-12-31"
                        }
                    ]
                }
            },
            "relaxations": [
                {
                    "rule_id": "GRAPH.OUTPUT.UNCONSUMED",
                    "scope": {"pipeline": "demo"},
                    "reason": "documented project preference",
                    "source": "audited_relax_policy"
                }
            ]
        }
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {
                    "nodes": [
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_audited")
    assert len(result.health.effective_policy["rules"]["downgrades"]) == 1
    assert "plugin.policy:audited_relax_policy" in result.health.effective_policy["sources"]

def test_plugin_load_and_execution_fail_closed(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad_plugin.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(tmp_path / "missing.py"), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]},
            }
        ),
        encoding="utf-8",
    )
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["errors"][0]["rule_id"] == "PLUGIN.LOAD"

    plugin_path = tmp_path / "raise_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "raise_policy"

    def extend_policy(self, policy):
        raise RuntimeError("boom")
""".strip(),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_exec")
    assert exc_info.value.result.health.status == "ERROR"
    assert any(error.rule_id == "PLUGIN.EXECUTION" for error in exc_info.value.result.health.errors)

def test_plugin_schema_extension_errors_are_fail_closed(tmp_path) -> None:
    plugin_path = tmp_path / "schema_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "schema_policy"

    def extend_node_metadata_schema(self, schema):
        raise RuntimeError("schema boom")
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_schema")
    assert exc_info.value.result.health.status == "ERROR"
    assert any(error.rule_id == "PLUGIN.EXECUTION" for error in exc_info.value.result.health.errors)

def test_policy_plugin_can_add_node_and_graph_findings(tmp_path) -> None:
    plugin_path = tmp_path / "finding_plugin.py"
    plugin_path.write_text(
        """
from topology_kernel import HealthFinding

class Plugin:
    name = "finding_policy"

    def validate_node(self, spec, node_cls, metrics):
        return [HealthFinding(
            rule_id="PLUGIN.NODE.CHECK",
            severity="warning",
            object_type="node",
            object_id=spec.name,
            failure_layer="plugin",
            message="plugin node check",
            suggested_fix_type="fix_node",
        )]

    def validate_graph(self, graph, compiled):
        return [HealthFinding(
            rule_id="PLUGIN.GRAPH.CHECK",
            severity="warning",
            object_type="pipeline",
            object_id="pipeline",
            failure_layer="plugin",
            message="plugin graph check",
            suggested_fix_type="fix_config",
        )]
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_findings")
    rule_ids = {warning.rule_id for warning in result.health.warnings}
    assert "PLUGIN.NODE.CHECK" in rule_ids
    assert "PLUGIN.GRAPH.CHECK" in rule_ids
    assert result.health.info["plugins"]["plugins"][0]["name"] == "finding_policy"
