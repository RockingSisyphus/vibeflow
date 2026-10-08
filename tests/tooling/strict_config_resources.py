from tests.fixtures.support.plugins import publish_native_fixture, append_resource, write_lifecycle_fixture
from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor
from tests.fixtures.support.declarations import node_declaration, configured_declaration
from tests.fixtures.support.strict_support import *
from tests.fixtures.support.strict_support_runtime_implementations import GlobalParamNode


GlobalParamNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.global_param', display_name='Global Param', description='Reads global config from params.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('value.out', 'value.out', display_name='value.out'),), output_semantics={'value.out': ('global config value',)}, examples=({'inputs': {}, 'params': {'_global': {'offset': 1}}},)), rulesets=("vibeflow.process",))

def test_config_resource_schema_rejects_invalid_status_and_plugin_config() -> None:
    findings = collect_config_schema_findings(
        {
            "global_config": [],
            "base_lib": {"paths": "base_lib", "modules": [{"module": "base_lib.math", "status": "future"}]},
            "plugins": [{"id": "bad", "status": "later", "config": []}],
            "pipeline": _seed_only_pipeline(),
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    assert "CONFIG.SCHEMA.GLOBAL_CONFIG" in rule_ids
    assert "CONFIG.BASE_LIB.REGISTRATION_REMOVED" in rule_ids
    assert "CONFIG.SCHEMA.RESOURCE_STATUS" in rule_ids
    assert "CONFIG.SCHEMA.PLUGIN_CONFIG" in rule_ids
    assert "CONFIG.SCHEMA.RESOURCE_METADATA_STRING" in {
        finding.rule_id
        for finding in collect_config_schema_findings(
            {
                "base_lib": {"modules": [{"module": "base_lib.math", "display_name": 1}]},
                "plugins": [{"id": "bad", "status": "planned", "type": "runtime", "description": 2}],
                "pipeline": _seed_only_pipeline(),
            }
        )
    }

    host_findings = collect_config_schema_findings(
        {
            "host_extensions": [
                {
                    "id": "demo.host",
                    "status": "future",
                    "enabled": "yes",
                    "config": [],
                    "targets": "browser",
                },
                "demo.host",
            ],
            "pipeline": _seed_only_pipeline(),
        }
    )
    host_rule_ids = {finding.rule_id for finding in host_findings}
    assert "CONFIG.SCHEMA.RESOURCE_STATUS" in host_rule_ids
    assert "CONFIG.SCHEMA.HOST_EXTENSION_ENABLED" in host_rule_ids
    assert "CONFIG.SCHEMA.HOST_EXTENSION_CONFIG" in host_rule_ids
    assert "CONFIG.SCHEMA.HOST_EXTENSION_STRING_LIST" in host_rule_ids
    assert "CONFIG.SCHEMA.HOST_EXTENSION_DUPLICATE" in host_rule_ids
    assert "CONFIG.SCHEMA.HOST_EXTENSIONS_LIST" in {
        finding.rule_id
        for finding in collect_config_schema_findings(
            {
                "host_extensions": None,
                "pipeline": _seed_only_pipeline(),
            }
        )
    }

    flag_findings = collect_config_schema_findings(
        {
            "global_config": {"config": {"delta": 1}, "allow_config_override": "no"},
            "pipeline": {
                "nodes": [
                    {
                        "id": "flow",
                        "type_used": "math.add_one",
                        "allow_config_override": "no",
                        "provides": [PROV_SPEC("value.out")],
                    }
                ]
            },
        }
    )
    nodeset_flag_findings = collect_config_schema_findings(
        _nodeset_config("math.add_one", pipeline=_input_add_pipeline())
        | {"global_config": {"values": [], "override_child_config": "no"}}
    )
    flag_rule_ids = {finding.rule_id for finding in flag_findings}
    nodeset_flag_rule_ids = {finding.rule_id for finding in nodeset_flag_findings}
    assert "CONFIG.SCHEMA.CONFIG_OVERRIDE_FLAG" in flag_rule_ids
    assert "CONFIG.SCHEMA.GLOBAL_CONFIG_VALUES" in nodeset_flag_rule_ids


def test_config_schema_validates_pipeline_and_node_execution_locks() -> None:
    valid = collect_config_schema_findings(
        {
            "pipeline": {
                **_seed_only_pipeline(),
                "execution_lock": {"key": "trainer"},
            }
        }
    )
    assert not {
        finding.rule_id
        for finding in valid
        if "EXECUTION_LOCK" in finding.rule_id
    }

    invalid = collect_config_schema_findings(
        {
            "pipeline": {
                **_seed_only_pipeline(),
                "execution_lock": {"key": "vibeflow.internal", "mode": "x"},
                "nodes": [
                    {
                        "id": "seed",
                        "type_used": "test.seed",
                        "execution_lock": {"key": ""},
                    }
                ],
            }
        }
    )
    rule_ids = {finding.rule_id for finding in invalid}
    assert "CONFIG.SCHEMA.EXECUTION_LOCK_FIELD" in rule_ids
    assert "CONFIG.SCHEMA.EXECUTION_LOCK_RESERVED" in rule_ids
    assert "CONFIG.SCHEMA.EXECUTION_LOCK_KEY" in rule_ids


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

class RuntimePlugin:
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
                    "modules": [
                        {
                            "id": "base_lib.math_tools",
                            "display_name": "Math Tools Resource",
                            "category": "test",
                            "description": "Configured arithmetic helper resource.",
                            "version": "0.1.0",
                        },
                        {
                            "id": "base_lib.future_tools",
                            "status": "planned",
                            "display_name": "Future Tools",
                            "category": "test",
                            "description": "Planned helper library.",
                            "version": "0.1.0",
                        },
                    ],
                },
                "plugins": [{"id":"future_runtime_plugin","type":"runtime","status":"planned",
                    "display_name":"Future Runtime Plugin","description":"Planned runtime hook."}],
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts the resource fixture."),
                        _node_call("global", "test.global_param", "Reads global config."),
                        _node_call("end", "test.out_end", "Consumes value.out."),
                    ],
                    "edges": _edge_chain("start", "global", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
            }
        ),
        encoding="utf-8",
    )
    registry = _registry()
    register_node(registry, GlobalParamNode_DECLARATION, GlobalParamNode)

    publish_native_fixture(config_path,registry)
    append_resource(tmp_path,{"kind":"base_lib","id":"base_lib.math_tools","display_name":"Math Tools Resource",
        "description":"Configured arithmetic helper resource.","implementations":[{"language":"python","targets":["python"],
        "source":{"kind":"file","ref":"base_lib/math_tools.py"}}]})
    lifecycle = write_lifecycle_fixture(tmp_path,source={"kind":"file","ref":"runtime_plugin.py","export":"RuntimePlugin"},
        plugin_id="configured_runtime",config={"marker":str(marker_path),"label":"ready"},filename="selected_lifecycle_0.py")
    source_path = tmp_path / "selected_lifecycle_0.py"
    source_path.write_text(source_path.read_text().replace("display_name='configured_runtime'", "display_name='Configured Runtime Resource'").replace('description="Native lifecycle fixture"','description="Configured runtime hook resource."'))
    document = json.loads(config_path.read_text())
    document["plugins"].insert(1,lifecycle)
    config_path.write_text(json.dumps(document))
    result = run_checked(config_path, registry=registry, run_root=tmp_path / "runs", run_id="resources")

    assert result.context.get("value.out")["value"] == 7
    assert json.loads(marker_path.read_text(encoding="utf-8")) == {"before_run": True, "configured": "ready"}
    resources = result.health.info["resources"]
    assert resources["global_config"] == {"offset": 7}
    assert [item["status"] for item in resources["base_lib"]["modules"]] == ["implemented", "planned"]
    assert [item["status"] for item in resources["plugins"]] == ["implemented", "planned"]
    assert all(item.get("rulesets", []) == [] for item in resources["plugins"])
    assert result.health.info["production_ready"] is False
    assert result.health.info["plugins"]["plugins"] == [
        {
            "name": "configured_runtime.runtime",
            "type": "runtime",
            "priority": 100,
            "scope": "project",
            "source": str(tmp_path / "selected_lifecycle_0.py"),
            "rulesets": [],
            "source_path": str(tmp_path / "selected_lifecycle_0.py"),
        }
    ]
    graph_payload = json.loads((result.run_dir / "compiled_graph.json").read_text(encoding="utf-8"))
    assert graph_payload["effective_edges"] == [
        {"from": "start", "to": "global", "when": ""},
        {"from": "global", "to": "end", "when": ""},
    ]
    assert graph_payload["production_ready"] is False
    mermaid = (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    assert "resource_base_lib" in mermaid
    assert "Math Tools Resource" in mermaid
    assert "Configured Runtime Resource" in mermaid
    assert "desc: Configured runtime hook resource." in mermaid
    assert "Future Tools" in mermaid
    assert "base_lib.future_tools" in mermaid
    assert "future_runtime_plugin" in mermaid
    assert mermaid.count("plannedResource") >= 2
    assert not any(finding.rule_id == "GRAPH.FLOW.ORPHAN_NODE" for finding in (*result.health.errors, *result.health.warnings))
    assert not any(finding.rule_id.startswith("BASE_LIB.") for finding in (*result.health.errors, *result.health.warnings))
    assert not any(finding.rule_id.startswith("CONFIG.SMELL.MISSING_") for finding in result.health.warnings)


def test_planned_resources_preserve_explicit_review_metadata(tmp_path) -> None:
    from types import SimpleNamespace
    from vibeflow.tooling.application.python.project.resource_selection import select_python_resources
    from vibeflow.core.descriptors import compose_contributions
    planned = {"id":"future_runtime","type":"runtime","status":"planned",
        "display_name":"Future Runtime","description":"Review a future runtime."}
    registry = SimpleNamespace(loaded_plugins=SimpleNamespace(catalogs=compose_contributions(()), lifecycle_selections=(planned,)))
    resources, findings = select_python_resources({"base_lib":{"modules":[{"id":"future_tools","status":"planned",
        "display_name":"Future Tools","description":"Review a future library."}]}},registry=registry)
    assert findings == ()
    assert resources.plugins[0].status == "planned"
    assert resources.plugins[0].display_name == "Future Runtime"
    assert resources.base_libs[0].status == "planned"



def test_host_extension_resources_keep_workflow_status_and_config() -> None:
    from vibeflow.tooling.application.python.project.resource_selection import select_python_resources as load_config_resources

    resources, findings = load_config_resources(
        {
            "host_extensions": [
                {
                    "id": "demo.active_host",
                    "config": {"channel": "primary"},
                    "targets": ["browser"],
                    "provides": ["demo.port"],
                },
                {
                    "id": "demo.future_host",
                    "status": "planned",
                    "display_name": "Future Host",
                    "description": "Planned host boundary.",
                    "dependencies": ["demo.active_host"],
                },
                {
                    "id": "demo.disabled_host",
                    "enabled": False,
                },
            ],
            "pipeline": _seed_only_pipeline(),
        },
        base_path=Path("."),
    )

    assert not [
        finding for finding in findings if finding.severity == "error"
    ]
    payload = resources.to_dict()["host_extensions"]
    assert [item["id"] for item in payload] == [
        "demo.active_host",
        "demo.future_host",
    ]
    assert [item["status"] for item in payload] == [
        "implemented",
        "planned",
    ]
    assert payload[0]["config_keys"] == ["channel"]
    assert payload[1]["dependencies"] == ["demo.active_host"]
    assert resources.host_extensions[0].declared_contract_fields == {
        "targets",
        "provides",
    }


def test_host_extension_resources_resolve_registered_descriptor_metadata(
    tmp_path,
) -> None:
    from vibeflow.tooling.project.host_extensions import (
        HostExtensionResource,
        resolve_host_extension_resources,
    )
    from vibeflow.core.descriptors import HostExtensionCatalog
    from vibeflow.core.descriptors.decode import decode_resource as parse_descriptor_manifest

    catalog = HostExtensionCatalog()
    catalog.register(
        parse_descriptor_manifest(
            {
                "kind": "host_extension",
                "id": "demo.host",
                "display_name": "Registered Host",
                "description": "Registered host boundary.",
                "version": "1.0.0",
                "targets": ["browser"],
                "implementations": [
                    {
                        "language": "typescript",
                        "targets": ["browser"],
                        "source": {
                            "kind": "file",
                            "ref": "host.ts",
                            "export": "createHostExtension",
                        },
                    }
                ],
                "provides": ["demo.port"],
                "dependencies": [],
            }
        ),
        source=tmp_path / "manifests/host.jsonc",
    )

    resolved, findings = resolve_host_extension_resources(
        (
            HostExtensionResource(id="demo.host"),
            HostExtensionResource(
                id="demo.future",
                status="planned",
                display_name="Future Host",
            ),
        ),
        catalog=catalog,
    )

    assert findings == ()
    assert resolved[0].display_name == "Registered Host"
    assert resolved[0].targets == ("browser",)
    assert resolved[0].provides == ("demo.port",)
    assert resolved[0].source_path.endswith(
        "manifests/host.jsonc"
    )
    assert resolved[1].status == "planned"

    _, invalid_findings = resolve_host_extension_resources(
        (
            HostExtensionResource(id="demo.unknown"),
            HostExtensionResource(
                id="demo.host",
                targets=("node",),
                declared_contract_fields=frozenset({"targets"}),
            ),
            HostExtensionResource(
                id="demo.host",
                provides=(),
                declared_contract_fields=frozenset({"provides"}),
            ),
        ),
        catalog=catalog,
    )
    assert {finding.rule_id for finding in invalid_findings} == {
        "CONFIG.RESOURCE.UNKNOWN_HOST_EXTENSION",
        "CONFIG.RESOURCE.HOST_EXTENSION_CONTRACT",
    }


def test_planned_plugin_selection_skips_implementation_load(tmp_path) -> None:
    from types import SimpleNamespace
    from vibeflow.core.descriptors import compose_contributions
    from vibeflow.tooling.application.python.project.resource_selection import select_python_resources
    selection = {"id":"future_runtime","type":"runtime","status":"planned","config":{"mode":"review"},
        "display_name":"Future Policy","description":"Planned policy plugin."}
    registry = SimpleNamespace(loaded_plugins=SimpleNamespace(catalogs=compose_contributions(()),lifecycle_selections=(selection,)))
    resources, findings = select_python_resources({},registry=registry)
    assert findings == ()
    assert resources.plugins[0].descriptor is None
    assert resources.plugins[0].to_dict()["config"] == {"mode":"review"}



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

    registry = _registry()
    publish_native_fixture(config_path,registry)
    result = run_checked(config_path, registry=registry, run_root=tmp_path / "runs", run_id="global_override")

    assert result.context.get("value.out")["value"] == 6
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
    publish_native_fixture(config_path,registry)
    allowed = run_checked(config_path, registry=registry, run_root=tmp_path / "runs", run_id="global_override_allowed")
    assert allowed.context.get("value.out")["value"] == 6
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
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the nodeset config fixture."),
                    _node_call("flow", "math.add_one", "Calls add-one with config override.",  config={"delta": 6}, allow_config_override=False),
                    _node_call("end", "test.out_end", "Consumes value.out."),
                ],
                "edges": _edge_chain("start", "flow", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    runtime = PipelineRuntime(graph, registry=_registry())

    assert runtime._plan.frame("flow").subplan.frame("add").params["delta"] == 6
    assert runtime.run({"value.in": 2}).get("value.out")["value"] == 8
    warning_ids = {warning.rule_id for warning in report.warnings}
    assert "NODESET.CONFIG.OVERRIDES_GLOBAL_CONFIG" in warning_ids
    assert "CONFIG.GLOBAL_CONFIG.OVERRIDES_LOCAL" in warning_ids


def test_imported_nodeset_file_global_config_is_used_for_inner_nodes(tmp_path) -> None:
    imports_path = tmp_path / "nodesets.jsonc"
    imports_path.write_text(
        json.dumps(
            _nodeset_config(
                "math.add_one",
                requires=["value.in"],
                provides=["value.out"],
                exports=["value.out"],
                pipeline=_input_add_pipeline(add={"config": {"delta": 1}}),
            )
            | {"global_config": {"config": {"delta": 4}, "allow_config_override": True}}
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        json.dumps(
            {
                "nodeset_imports": [{"path": "nodesets.jsonc"}],
                "pipeline": {
                    "inputs": [INPUT_SPEC("value.in")],
                    "nodes": [
                        _node_call("start", "test.start", "Starts the imported nodeset fixture."),
                        _node_call("flow", "math.add_one", "Calls imported add-one nodeset."),
                        _node_call("end", "test.out_end", "Consumes value.out."),
                    ],
                    "edges": _edge_chain("start", "flow", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
            }
        ),
        encoding="utf-8",
    )

    registry = _registry()
    publish_native_fixture(config_path,registry)
    result = run_checked(config_path, registry=registry, run_root=tmp_path / "runs", run_id="imported_nodeset_global", initial={"value.in": 2})

    assert result.context.get("value.out")["value"] == 6


def test_sdk_metadata_is_authoritative_and_planned_resources_skip_load(tmp_path) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "__init__.py").write_text("")
    (base_dir / "plain.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "plain_plugin.py").write_text('from vibeflow.targets.python.sdk import Plugin\ndef runtime(context):\n    return type("NativeRuntime",(),{})()\nplugin=Plugin(id="with_info",runtime=runtime,display_name="With Info",description="SDK metadata is authoritative.")\n')
    config_path = tmp_path / "workflow.json"
    config_path.write_text(json.dumps({"base_lib":{"modules":["math",{"id":"future_missing","status":"planned","description":"Future helper."}]},
        "plugins":[{"source":{"kind":"file","ref":"plain_plugin.py","export":"plugin"}},
          {"id":"future_runtime","type":"runtime","status":"planned","description":"Future policy."}],
        "pipeline":_seed_only_pipeline()}))
    registry = _registry()
    publish_native_fixture(config_path,registry)
    append_resource(tmp_path,{"kind":"base_lib","id":"math","display_name":"Math","description":"Plain source uses SDK metadata.",
        "implementations":[{"language":"python","targets":["python"],"source":{"kind":"file","ref":"base_lib/plain.py"}}]})
    result = run_checked(config_path,registry=registry,run_root=tmp_path / "runs",run_id="declared_metadata")
    assert result.context is not None
    assert not result.health.errors
    assert result.health.info["resources"]["plugins"][0]["display_name"] == "With Info"
    assert result.health.info["resources"]["plugins"][1]["status"] == "planned"





def _write_base_lib_info_module(tmp_path: Path, name: str) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir(exist_ok=True)
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    (base_dir / f"{name}.py").write_text("def helper():\n    return 1\n",encoding="utf-8")
