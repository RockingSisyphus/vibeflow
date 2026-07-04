from tests.unit.strict_support import *


def test_policy_plugin_tightens_effective_policy_and_health_uses_it(tmp_path) -> None:
    plugin_path = tmp_path / "tight_plugin.py"
    plugin_path.write_text(
        """
from vibeflow import PluginInfo

class Plugin:
    PLUGIN_INFO = PluginInfo("tight_policy", "policy", "Tight Policy", "test", "Tightens node source limits.", "0.1.0")
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
                "pipeline": {"nodes": [_node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")])]},
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


@pytest.mark.parametrize(
    ("filename", "plugin_source", "run_id", "expected_rule_id"),
    [
        (
            "relax_plugin.py",
            """
from vibeflow import PluginInfo

class Plugin:
    PLUGIN_INFO = PluginInfo("relax_policy", "policy", "Relax Policy", "test", "Relaxes import policy.", "0.1.0")
    name = "relax_policy"

    def extend_policy(self, policy):
        return {"imports": {"allowed_roots": ["numpy"]}}
""",
            "plugin_relax",
            "PLUGIN.POLICY.RELAXATION_REQUIRED",
        ),
        (
            "schema_plugin.py",
            """
from vibeflow import PluginInfo

class Plugin:
    PLUGIN_INFO = PluginInfo("schema_policy", "policy", "Schema Policy", "test", "Extends node metadata schema.", "0.1.0")
    name = "schema_policy"

    def extend_node_metadata_schema(self, schema):
        raise RuntimeError("schema boom")
""",
            "plugin_schema",
            "PLUGIN.EXECUTION",
        ),
    ],
)
def test_policy_plugin_errors_are_fail_closed(tmp_path, filename, plugin_source, run_id, expected_rule_id) -> None:
    config_path = _write_policy_plugin_workflow(tmp_path, filename=filename, plugin_source=plugin_source)
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id=run_id)
    assert exc_info.value.result.health.status == "ERROR"
    assert any(error.rule_id == expected_rule_id for error in exc_info.value.result.health.errors)


def test_policy_plugin_allows_audited_downgradeable_relaxation(tmp_path) -> None:
    plugin_path = tmp_path / "audited_relax_plugin.py"
    plugin_path.write_text(
        """
from vibeflow import PluginInfo

class Plugin:
    PLUGIN_INFO = PluginInfo("audited_relax_policy", "policy", "Audited Relax Policy", "test", "Declares audited policy relaxation.", "0.1.0")
    name = "audited_relax_policy"

    def extend_policy(self, policy):
        return {
            "policy": {
                "rules": {
                    "downgrades": [
                        {
                            "rule_id": "GRAPH.DATA.UNCONSUMED_PROVIDER",
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
                    "rule_id": "GRAPH.DATA.UNCONSUMED_PROVIDER",
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
                "pipeline": _seed_add_pipeline(),
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
from vibeflow import PluginInfo

class Plugin:
    PLUGIN_INFO = PluginInfo("raise_policy", "policy", "Raise Policy", "test", "Raises during policy extension.", "0.1.0")
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


def _write_policy_plugin_workflow(tmp_path: Path, *, filename: str, plugin_source: str) -> Path:
    plugin_path = tmp_path / filename
    plugin_path.write_text(plugin_source.strip(), encoding="utf-8")
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": _seed_only_pipeline(),
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_policy_plugin_can_add_node_and_graph_findings(tmp_path) -> None:
    plugin_path = tmp_path / "finding_plugin.py"
    plugin_path.write_text(
        """
from vibeflow import HealthFinding, PluginInfo

class Plugin:
    PLUGIN_INFO = PluginInfo("finding_policy", "policy", "Finding Policy", "test", "Adds node and graph findings.", "0.1.0")
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
                "pipeline": _seed_only_pipeline(),
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_findings")
    rule_ids = {warning.rule_id for warning in result.health.warnings}
    assert "PLUGIN.NODE.CHECK" in rule_ids
    assert "PLUGIN.GRAPH.CHECK" in rule_ids
    assert result.health.info["plugins"]["plugins"][0]["name"] == "finding_policy"
