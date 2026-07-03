from tests.unit.strict_support import *


class GlobalParamNode:
    NODE_INFO = NodeInfo(
        type_key="test.global_param",
        display_name="Global Param",
        category="test",
        description="Reads global config from params.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("global config value",)},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {"_global": {"offset": 1}}},),
    )

    def run_pure(self, inputs, params):
        return {"value.out": params["_global"]["offset"]}


def test_config_resource_schema_rejects_invalid_status_and_plugin_config() -> None:
    findings = collect_config_schema_findings(
        {
            "global_config": [],
            "base_lib": {"paths": "base_lib", "modules": [{"module": "base_lib.math", "status": "future"}]},
            "plugins": [{"name": "bad", "status": "later", "config": []}],
            "pipeline": _seed_only_pipeline(),
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    assert "CONFIG.SCHEMA.GLOBAL_CONFIG" in rule_ids
    assert "CONFIG.SCHEMA.BASE_LIB_PATHS" in rule_ids
    assert "CONFIG.SCHEMA.RESOURCE_STATUS" in rule_ids
    assert "CONFIG.SCHEMA.PLUGIN_CONFIG" in rule_ids

    flag_findings = collect_config_schema_findings(
        {
            "global_config": {"config": {"delta": 1}, "allow_config_override": "no"},
            "nodesets": [
                _nodeset_config("math.add_one", pipeline=_input_add_pipeline())
                | {"global_config": {"values": [], "override_child_config": "no"}}
            ],
            "pipeline": {
                "nodes": [
                    {
                        "name": "flow",
                        "type": "nodeset.math.add_one",
                        "allow_config_override": "no",
                        "provides": ["value.out"],
                    }
                ]
            },
        }
    )
    flag_rule_ids = {finding.rule_id for finding in flag_findings}
    assert "CONFIG.SCHEMA.CONFIG_OVERRIDE_FLAG" in flag_rule_ids
    assert "CONFIG.SCHEMA.GLOBAL_CONFIG_VALUES" in flag_rule_ids


def test_config_resources_global_config_plugins_base_lib_and_mermaid(tmp_path) -> None:
    _write_base_lib_info_module(tmp_path, "math_tools")
    (tmp_path / "base_lib" / "future_tools.py").write_text(
        """
from pathlib import Path

Path("planned.txt").write_text("not executable")
""".strip(),
        encoding="utf-8",
    )
    marker_path = tmp_path / "plugin_marker.json"
    plugin_path = tmp_path / "runtime_plugin.py"
    plugin_path.write_text(
        f"""
import json
from pathlib import Path
from vibeflow import PluginInfo

class RuntimePlugin:
    PLUGIN_INFO = PluginInfo("configured_runtime", "runtime", "Configured Runtime", "test", "Records runtime config.", "0.1.0")
    name = "configured_runtime"

    def configure(self, config):
        Path(config["marker"]).write_text(json.dumps({{"configured": config["label"]}}, sort_keys=True), encoding="utf-8")

    def before_run(self, state):
        payload = json.loads(Path(self.config["marker"]).read_text(encoding="utf-8"))
        payload["before_run"] = True
        Path(self.config["marker"]).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "global_config": {"offset": 7},
                "base_lib": {
                    "paths": ["base_lib"],
                    "modules": [
                        "base_lib.math_tools",
                        {"module": "base_lib.future_tools", "status": "planned", "description": "Planned helper library."},
                    ],
                },
                "plugins": [
                    {
                        "module": str(plugin_path),
                        "class": "RuntimePlugin",
                        "type": "runtime",
                        "config": {"marker": str(marker_path), "label": "ready"},
                    },
                    {"name": "future_runtime_plugin", "type": "runtime", "status": "planned", "description": "Planned runtime hook."},
                ],
                "pipeline": {
                    "nodes": [
                        {"name": "start", "type": "test.start"},
                        {"name": "global", "type": "test.global_param", "provides": ["value.out"]},
                        {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                    ],
                    "edges": _edge_chain("start", "global", "end"),
                },
            }
        ),
        encoding="utf-8",
    )
    registry = _registry()
    register_node(registry, "test.global_param", GlobalParamNode)

    result = run_checked(config_path, registry=registry, run_root=tmp_path / "runs", run_id="resources")

    assert result.context.get("value.out") == 7
    assert json.loads(marker_path.read_text(encoding="utf-8")) == {"before_run": True, "configured": "ready"}
    resources = result.health.info["resources"]
    assert resources["global_config"] == {"offset": 7}
    assert [item["status"] for item in resources["base_lib"]["modules"]] == ["implemented", "planned"]
    assert [item["status"] for item in resources["plugins"]] == ["implemented", "planned"]
    assert result.health.info["plugins"]["plugins"] == [
        {
            "name": "configured_runtime",
            "type": "runtime",
            "priority": 100,
            "scope": "project",
            "source": str(plugin_path),
        }
    ]
    graph_payload = json.loads((result.run_dir / "compiled_graph.json").read_text(encoding="utf-8"))
    assert graph_payload["effective_edges"] == [
        {"from": "start", "to": "global", "when": ""},
        {"from": "global", "to": "end", "when": ""},
    ]
    mermaid = (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    assert "resource_base_lib" in mermaid
    assert "Math Tools" in mermaid
    assert "base_lib.future_tools" in mermaid
    assert "Configured Runtime" in mermaid
    assert "future_runtime_plugin" in mermaid
    assert "plannedResource" in mermaid
    assert not any(finding.rule_id == "GRAPH.FLOW.ORPHAN_NODE" for finding in (*result.health.errors, *result.health.warnings))
    assert not any(finding.rule_id.startswith("BASE_LIB.") for finding in (*result.health.errors, *result.health.warnings))


def test_global_config_overrides_node_params_and_warns_when_not_allowed(tmp_path) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "global_config": {"config": {"delta": 5}, "allow_config_override": False},
                "pipeline": _seed_add_pipeline(add={"config": {"delta": 1}}),
            }
        ),
        encoding="utf-8",
    )

    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="global_override")

    assert result.context.get("value.out") == 6
    warnings = {warning.rule_id for warning in result.health.warnings}
    assert "CONFIG.GLOBAL_CONFIG.OVERRIDES_LOCAL" in warnings

    config_path.write_text(
        json.dumps(
            {
                "global_config": {"config": {"delta": 5}, "allow_config_override": True},
                "pipeline": _seed_add_pipeline(add={"config": {"delta": 1}}),
            }
        ),
        encoding="utf-8",
    )
    allowed = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="global_override_allowed")
    assert allowed.context.get("value.out") == 6
    assert "CONFIG.GLOBAL_CONFIG.OVERRIDES_LOCAL" not in {warning.rule_id for warning in allowed.health.warnings}


def test_nodeset_call_config_overrides_nodeset_global_and_inner_node_config(tmp_path) -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"config": {"delta": 1}}),
                )
                | {"global_config": {"config": {"delta": 2}, "allow_config_override": False}}
            ],
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "input", "type": "test.value_input", "requires": ["value.in"]},
                    {
                        "name": "flow",
                        "type": "nodeset.math.add_one",
                        "requires": ["value.in"],
                        "provides": ["value.out"],
                        "config": {"delta": 6},
                        "allow_config_override": False,
                    },
                    {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                ],
                "edges": _edge_chain("start", "input", "flow", "end"),
            },
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    runtime = PipelineRuntime(graph, registry=_registry())

    assert runtime._plan.frame("flow").subplan.frame("add").params["delta"] == 6
    assert runtime.run({"value.in": 2}).get("value.out") == 8
    warning_ids = {warning.rule_id for warning in report.warnings}
    assert "NODESET.CONFIG.OVERRIDES_GLOBAL_CONFIG" in warning_ids
    assert "CONFIG.GLOBAL_CONFIG.OVERRIDES_LOCAL" in warning_ids


def test_imported_nodeset_file_global_config_is_used_for_inner_nodes(tmp_path) -> None:
    imports_path = tmp_path / "nodesets.jsonc"
    imports_path.write_text(
        json.dumps(
            {
                "global_config": {"config": {"delta": 4}, "allow_config_override": True},
                "nodesets": [
                    _nodeset_config(
                        "math.add_one",
                        requires=["value.in"],
                        provides=["value.out"],
                        exports=["value.out"],
                        pipeline=_input_add_pipeline(add={"config": {"delta": 1}}),
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        json.dumps(
            {
                "nodeset_imports": [{"path": "nodesets.jsonc", "names": ["math.add_one"]}],
                "pipeline": {
                    "inputs": ["value.in"],
                    "nodes": [
                        {"name": "start", "type": "test.start"},
                        {"name": "input", "type": "test.value_input", "requires": ["value.in"]},
                        {"name": "flow", "type": "nodeset.math.add_one", "requires": ["value.in"], "provides": ["value.out"]},
                        {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                    ],
                    "edges": _edge_chain("start", "input", "flow", "end"),
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="imported_nodeset_global", initial={"value": {"in": 2}})

    assert result.context.get("value.out") == 6


def test_implemented_resources_require_metadata_but_planned_resources_skip_load(tmp_path) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    (base_dir / "missing_info.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    plugin_path = tmp_path / "missing_info_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "missing_info"
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "base_lib": {
                    "paths": ["base_lib"],
                    "modules": [
                        {"module": "base_lib.missing_info", "status": "implemented"},
                        {"name": "base_lib.future_missing", "status": "planned", "description": "Future helper."},
                    ],
                },
                "plugins": [
                    {"module": str(plugin_path), "type": "policy"},
                    {"name": "future_policy", "status": "planned", "description": "Future policy."},
                ],
                "pipeline": _seed_only_pipeline(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="missing_metadata")

    rule_ids = {error.rule_id for error in exc_info.value.result.health.errors}
    assert "PLUGIN.LOAD" in rule_ids
    assert "BASE_LIB.INFO.MISSING" not in rule_ids

    plugin_path.write_text(
        """
from vibeflow import PluginInfo

class Plugin:
    PLUGIN_INFO = PluginInfo("with_info", "policy", "With Info", "test", "Valid policy metadata.", "0.1.0")
    name = "with_info"
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="missing_base_lib_metadata")

    rule_ids = {error.rule_id for error in exc_info.value.result.health.errors}
    assert "BASE_LIB.INFO.MISSING" in rule_ids
    assert "BASE_LIB.LOAD" not in rule_ids


def test_planned_base_lib_does_not_satisfy_node_import_allowlist(tmp_path, monkeypatch) -> None:
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_base_lib_info_module(tmp_path, "math_tools")
    future = tmp_path / "base_lib" / "future_tools.py"
    future.write_text("def helper():\n    return 9\n", encoding="utf-8")
    node_path = tmp_path / "future_node.py"
    node_path.write_text(
        """
from vibeflow import NodeContract, NodeInfo

class FutureNode:
    NODE_INFO = NodeInfo("test.future", "Future", "test", "Imports a planned base_lib.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("future value",)},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        from base_lib.future_tools import helper
        return {"value.out": helper()}
""".strip(),
        encoding="utf-8",
    )
    module = _load_module_from_path(node_path, "_future_node")
    registry = _registry()
    register_node(registry, "test.future", module.FutureNode)
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "base_lib": {
                    "paths": ["base_lib"],
                    "modules": [
                        {"module": "base_lib.math_tools", "status": "implemented"},
                        {"module": "base_lib.future_tools", "status": "planned", "description": "Future helper."},
                    ],
                },
                "pipeline": {
                    "nodes": [
                        {"name": "start", "type": "test.start"},
                        {"name": "future", "type": "test.future", "provides": ["value.out"]},
                        {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                    ],
                    "edges": _edge_chain("start", "future", "end"),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=registry, run_root=tmp_path / "runs", run_id="planned_base_lib_import")

    assert any(error.details.get("legacy_code") == "base_lib_undeclared" for error in exc_info.value.result.health.errors)
    assert exc_info.value.result.health.effective_policy["base_lib"]["allowed_modules"] == ["base_lib.math_tools"]


def _write_base_lib_info_module(tmp_path: Path, name: str) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir(exist_ok=True)
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    (base_dir / f"{name}.py").write_text(
        f"""
from vibeflow import BaseLibInfo

BASE_LIB_INFO = BaseLibInfo(
    module="base_lib.{name}",
    display_name="{name.replace("_", " ").title()}",
    category="test",
    description="Pure helper module.",
    version="0.1.0",
)

def helper():
    return 1
""".strip(),
        encoding="utf-8",
    )
