from tests.unit.strict_support import *


def _stub_project(tmp_path: Path, source: str) -> tuple[Path, Path]:
    config_dir = tmp_path / "project" / "configs"
    stub_dir = tmp_path / "project" / "stubs"
    config_dir.mkdir(parents=True)
    stub_dir.mkdir(parents=True)
    stub_path = stub_dir / "runtime_control_stub.py"
    stub_path.write_text(source.strip() + "\n", encoding="utf-8")
    return config_dir / "workflow.json", stub_path


def _planned_stub_config(*, behavior=None, node_status: str = "planned") -> dict:
    return {
        "global_config": {"config": {"bonus": 3}, "allow_config_override": True},
        "pipeline": {
            "inputs": ["value.in"],
            "nodes": [
                {"name": "start", "type": "test.start"},
                {
                    "name": "stub",
                    "status": node_status,
                    "flow_kind": "process",
                    "requires": ["value.in"],
                    "provides": ["value.out"],
                    "config": {"delta": 4},
                    "planned_behavior": behavior
                    or {"kind": "python_stub", "stub_module": "project/stubs/runtime_control_stub.py"},
                },
                {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
            ],
            "edges": _edge_chain("start", "stub", "end"),
        },
    }


def test_planned_behavior_schema_and_parser_defaults() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "future", "status": "planned", "flow_kind": "process"},
                ]
            }
        }
    )
    assert graph.nodes[0].planned_behavior.kind == "blocking"

    findings = collect_config_schema_findings(_planned_stub_config(behavior="/tmp/stub.py"))
    assert any(finding.rule_id == "GRAPH.PLANNED.BEHAVIOR_INVALID" for finding in findings)

    implemented_findings = collect_config_schema_findings(_planned_stub_config(node_status="implemented"))
    assert any(finding.rule_id == "GRAPH.PLANNED.BEHAVIOR_IMPLEMENTED" for finding in implemented_findings)

    with pytest.raises(GraphConfigError, match="planned_behavior is only allowed"):
        parse_graph_config(_planned_stub_config(node_status="implemented"))

    bad_path = _planned_stub_config(behavior={"kind": "python_stub", "stub_module": "../stubs/runtime_control_stub.py"})
    assert any(finding.rule_id == "GRAPH.PLANNED.STUB_MODULE" for finding in collect_config_schema_findings(bad_path))


def test_transparent_planned_participates_in_flow_health() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {
                        "name": "future",
                        "status": "planned",
                        "flow_kind": "process",
                        "planned_behavior": "transparent",
                    },
                    {"name": "end", "type": "test.in_end", "requires": ["value.in"]},
                ],
                "edges": _edge_chain("start", "future", "end"),
            }
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))

    assert report.status == "CONCERNS"
    assert any(warning.rule_id == "GRAPH.PLANNED.NODE" and warning.details["planned_behavior"] == "transparent" for warning in report.warnings)
    assert not any(error.rule_id.startswith("GRAPH.FLOW.") for error in report.errors)


def test_blocking_planned_keeps_old_flow_health_behavior() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "future", "status": "planned", "flow_kind": "process"},
                    {"name": "end", "type": "test.in_end", "requires": ["value.in"]},
                ],
                "edges": _edge_chain("start", "future", "end"),
            }
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))

    assert report.status == "FAIL"
    assert any(error.rule_id in {"GRAPH.FLOW.UNREACHABLE_FROM_START", "GRAPH.FLOW.CANNOT_REACH_END", "GRAPH.FLOW.ORPHAN_NODE"} for error in report.errors)


def test_python_stub_health_validates_entry_and_safety(tmp_path) -> None:
    config_path, _ = _stub_project(
        tmp_path,
        """
def run_stub(inputs, params):
    return {"value.out": inputs["value.in"] + params["delta"] + params["_global"]["bonus"]}
""",
    )
    graph = parse_graph_config(_planned_stub_config(), project_root=tmp_path)
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))

    assert report.status == "CONCERNS"
    assert any(warning.rule_id == "GRAPH.PLANNED.PYTHON_STUB_DEV_ONLY" for warning in report.warnings)
    assert not report.errors

    config_path.write_text(json.dumps(_planned_stub_config()), encoding="utf-8")
    result = run_checked(
        config_path,
        registry=_registry(),
        initial={"value.in": 5},
        run_root=tmp_path / "runs",
        run_id="planned_stub",
        runtime_options=RuntimeOptions(allow_planned_stub=True, trace="boundary"),
    )
    assert result.health.status == "CONCERNS"
    assert result.health.info["production_ready"] is False
    assert result.context.get("value.out") == 12
    trace = [json.loads(line) for line in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    stub_event = next(item for item in trace if item["kind"] == "planned_stub")
    assert stub_event["details"]["stub_module"] == "project/stubs/runtime_control_stub.py"
    assert stub_event["details"]["input_keys"] == ["value.in"]
    assert stub_event["details"]["output_keys"] == ["value.out"]


def test_python_stub_default_run_refuses_and_allow_flag_is_behavior_strict(tmp_path) -> None:
    config_path, _ = _stub_project(
        tmp_path,
        """
def run_stub(inputs, params):
    return {"value.out": inputs["value.in"]}
""",
    )
    config_path.write_text(json.dumps(_planned_stub_config()), encoding="utf-8")

    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), initial={"value.in": 5}, run_root=tmp_path / "runs", run_id="default_refuse")
    assert any(error.rule_id == "GRAPH.PLANNED.NODE_IN_RUN" for error in exc_info.value.result.health.errors)

    transparent = _planned_stub_config(behavior="transparent")
    config_path.write_text(json.dumps(transparent), encoding="utf-8")
    with pytest.raises(CheckedRunError) as transparent_exc:
        run_checked(
            config_path,
            registry=_registry(),
            initial={"value.in": 5},
            run_root=tmp_path / "runs",
            run_id="transparent_refuse",
            runtime_options=RuntimeOptions(allow_planned_stub=True),
        )
    assert transparent_exc.value.result.health.errors[-1].details["allow_planned_stub"] is True


def test_python_stub_return_keys_must_exactly_match_provides(tmp_path) -> None:
    config_path, _ = _stub_project(
        tmp_path,
        """
def run_stub(inputs, params):
    return {"value.out": inputs["value.in"], "extra.out": 1}
""",
    )
    config_path.write_text(json.dumps(_planned_stub_config()), encoding="utf-8")

    with pytest.raises(PipelineRuntimeError, match="output keys must exactly match"):
        run_checked(
            config_path,
            registry=_registry(),
            initial={"value.in": 5},
            run_root=tmp_path / "runs",
            run_id="bad_stub_return",
            runtime_options=RuntimeOptions(allow_planned_stub=True),
        )


def test_python_stub_missing_entry_and_unsafe_import_fail_health(tmp_path) -> None:
    _stub_project(
        tmp_path,
        """
import subprocess

def wrong(inputs, params):
    return {}
""",
    )
    graph = parse_graph_config(_planned_stub_config(), project_root=tmp_path)

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))

    rule_ids = {error.rule_id for error in report.errors}
    assert "GRAPH.PLANNED.STUB_ENTRY" in rule_ids
    assert "GRAPH.PLANNED.STUB_UNSAFE_IMPORT" in rule_ids


def test_planned_python_stub_nodeset_executes_as_single_stub(tmp_path) -> None:
    config_path, _ = _stub_project(
        tmp_path,
        """
def run_stub(inputs, params):
    return {"value.out": inputs["value.in"] + params["delta"]}
""",
    )
    config = {
        "nodesets": [
            {
                "name": "future.math",
                "status": "planned",
                "planned_behavior": {"kind": "python_stub", "stub_module": "project/stubs/runtime_control_stub.py"},
                "requires": ["value.in"],
                "provides": ["value.out"],
                "exports": ["value.out"],
            }
        ],
        "pipeline": {
            "inputs": ["value.in"],
            "nodes": [
                {"name": "start", "type": "test.start"},
                {
                    "name": "future",
                    "type": "nodeset.future.math",
                    "status": "planned",
                    "flow_kind": "predefined",
                    "requires": ["value.in"],
                    "provides": ["value.out"],
                    "config": {"delta": 8},
                },
                {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
            ],
            "edges": _edge_chain("start", "future", "end"),
        },
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_checked(
        config_path,
        registry=_registry(),
        initial={"value.in": 2},
        run_root=tmp_path / "runs",
        run_id="planned_nodeset_stub",
        runtime_options=RuntimeOptions(allow_planned_stub=True),
    )

    assert result.context.get("value.out") == 10
    assert list(result.context.get("runtime.exec_order")) == ["start", "future", "end"]
