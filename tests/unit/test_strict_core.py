from tests.unit.strict_support import *

def test_pure_node_metadata_and_static_check() -> None:
    assert validate_node_class(SeedNode, policy=PurityPolicy(max_source_lines=1000)) == []
    violations = validate_node_class(BadIoNode, policy=PurityPolicy(max_source_lines=1000))
    assert any(item.code == "banned_call" for item in violations)

def test_source_size_limit_is_enforced() -> None:
    violations = validate_node_class(SeedNode, policy=PurityPolicy(max_source_lines=1))
    assert any(item.code == "source_too_large" for item in violations)

def test_requires_provides_data_edges_are_inferred_and_runtime_runs() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": 4},
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 3},
                ],
                "edges": [],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert ("seed", "add") in [edge.pair for edge in compiled.data_edges]
    context = PipelineRuntime(graph, registry=_registry()).run()
    assert context.get("value.out") == 7

def test_undeclared_cycle_is_rejected() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "edges": [
                    {"from": "add", "to": "copy", "max_executions": 3},
                    {"from": "copy", "to": "add", "max_executions": 3},
                ],
            }
        }
    )
    with pytest.raises(GraphCompileError):
        GraphCompiler().compile(graph)

def test_declared_bounded_loop_compiles_and_runs() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 1},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "edges": [
                    {"from": "add", "to": "copy", "max_executions": 4},
                    {"from": "copy", "to": "add", "max_executions": 3, "loop": "counter_loop"},
                ],
                "loops": [
                    {
                        "name": "counter_loop",
                        "edges": [["copy", "add"]],
                        "nodes": ["add", "copy"],
                        "max_iterations": 3,
                    }
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert ("copy", "add") in [edge.pair for edge in compiled.loop_edges]
    assert compiled.loop_orders["counter_loop"] == ("add", "copy")
    assert compiled.edge_execution_limits[("add", "copy")] == 4
    assert compiled.edge_execution_limits[("copy", "add")] == 3
    context = PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 0}})
    assert context.get("value.in") == 4
    assert context.get("runtime.edge_executions") == {"add->copy": 4, "copy->add": 3}
    assert context.get("runtime.loop_iterations") == {"counter_loop": 3}
    assert context.get("runtime.loop_stop_reasons") == {"counter_loop": "max_iterations"}
    assert context.get("runtime.loop_orders") == {"counter_loop": ["add", "copy"]}

def test_loop_edge_inherits_loop_limit_when_edge_has_no_explicit_max() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "loops": [
                    {
                        "name": "counter_loop",
                        "edges": [["copy", "add"]],
                        "max_iterations": 2,
                    }
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert compiled.edge_execution_limits[("copy", "add")] == 2
    context = PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 0}})
    assert context.get("runtime.edge_executions") == {"add->copy": 3, "copy->add": 2}

def test_loop_until_stops_before_iteration_and_is_traced() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in", "stop.now"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "loops": [
                    {
                        "name": "counter_loop",
                        "edges": [["copy", "add"]],
                        "max_iterations": 5,
                        "until": "stop.now",
                    }
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert compiled.loop_orders["counter_loop"] == ("add", "copy")
    context = PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 0}, "stop": {"now": True}})
    assert context.get("runtime.loop_iterations") == {"counter_loop": 0}
    assert context.get("runtime.loop_stop_reasons") == {"counter_loop": "until"}
    assert context.get("runtime.edge_executions") == {"add->copy": 1}

def test_loop_compile_rejects_unresolved_until_and_missing_max_iterations() -> None:
    with pytest.raises(ValueError, match="requires max_iterations"):
        parse_graph_config(
            {
                "pipeline": {
                    "inputs": ["value.in"],
                    "nodes": [
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                        {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                    ],
                    "loops": [{"name": "counter_loop", "edges": [["copy", "add"]]}],
                }
            }
        )

    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "loops": [
                    {
                        "name": "counter_loop",
                        "edges": [["copy", "add"]],
                        "max_iterations": 2,
                        "until": "missing.stop",
                    }
                ],
            }
        }
    )
    with pytest.raises(GraphCompileError, match="until key is not resolvable"):
        GraphCompiler().compile(graph)

def test_compiler_can_check_registry_node_types() -> None:
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "missing", "type": "test.missing"}]}})
    with pytest.raises(GraphCompileError, match="unknown type"):
        GraphCompiler().compile(graph, registry=_registry())

def test_boundary_lifecycle_updates_context_and_writes_trace(tmp_path) -> None:
    DemoBoundary.calls = []
    boundary_registry = BoundaryRegistry()
    boundary_registry.register("test.boundary", DemoBoundary)
    run_dir = tmp_path / "run"
    graph = parse_graph_config(
        {
            "boundary": {
                "type": "test.boundary",
                "config": {"run_dir": str(run_dir)},
                "consumes": ["effects.request"],
                "provides": ["io.result"],
            },
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "effect",
                        "type": "test.effect_request",
                        "requires": ["value.in"],
                        "provides": ["effects.request"],
                    }
                ],
                "edges": [{"from": "effect", "to": "effect", "loop": "effect_loop"}],
                "loops": [{"name": "effect_loop", "edges": [["effect", "effect"]], "max_iterations": 2}],
            },
        }
    )
    context = PipelineRuntime(graph, registry=_registry(), boundary_registry=boundary_registry).run({"value": {"in": 10}})
    assert context.get("io.result") == 12
    assert context.get("runtime.loop_stop_reasons") == {"effect_loop": "max_iterations"}
    assert DemoBoundary.calls == [
        "before_run",
        "before_iteration:0",
        "after_iteration:0",
        "before_iteration:1",
        "after_iteration:1",
        "after_run",
    ]
    trace_path = run_dir / "boundary_trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [event["stage"] for event in events] == [
        "before_run",
        "before_iteration",
        "after_iteration",
        "before_iteration",
        "after_iteration",
        "after_run",
    ]

def test_boundary_health_resolves_type_and_suppresses_consumed_effect_warning() -> None:
    boundary_registry = BoundaryRegistry()
    boundary_registry.register("test.boundary", DemoBoundary)
    graph = parse_graph_config(
        {
            "boundary": {
                "type": "test.boundary",
                "consumes": ["effects.request"],
                "provides": ["io.result"],
            },
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "effect",
                        "type": "test.effect_request",
                        "requires": ["value.in"],
                        "provides": ["effects.request"],
                    }
                ],
            },
        }
    )
    unresolved = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(error.rule_id == "BOUNDARY.TYPE.UNRESOLVED" for error in unresolved.errors)
    report = validate_graph_health(
        graph,
        registry=_registry(),
        boundary_registry=boundary_registry,
        purity_policy=PurityPolicy(max_source_lines=1000),
    )
    assert not any(warning.object_id == "effects.request" for warning in report.warnings)
    assert report.info["boundary"]["type"] == "test.boundary"

def test_boundary_runtime_rejects_unknown_type_undeclared_key_and_escaped_artifact(tmp_path) -> None:
    graph = parse_graph_config(
        {
            "boundary": {"type": "missing.boundary", "consumes": ["effects.request"], "provides": ["io.result"]},
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
        }
    )
    with pytest.raises(PipelineRuntimeError, match="unknown boundary key"):
        PipelineRuntime(graph, registry=_registry(), boundary_registry=BoundaryRegistry())

    class BadKeyBoundary(DemoBoundary):
        def before_run(self, run_config):
            return {"unsafe.key": 1}

    boundary_registry = BoundaryRegistry()
    boundary_registry.register("bad.key", BadKeyBoundary)
    graph = parse_graph_config(
        {
            "boundary": {"type": "bad.key", "provides": ["io.result"]},
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
        }
    )
    with pytest.raises(PipelineRuntimeError, match="undeclared key"):
        PipelineRuntime(graph, registry=_registry(), boundary_registry=boundary_registry, run_dir=tmp_path / "run").run()

    class EscapedArtifactBoundary(DemoBoundary):
        def before_run(self, run_config):
            return {"artifacts": [str(tmp_path / "outside.txt")]}

    boundary_registry = BoundaryRegistry()
    boundary_registry.register("bad.artifact", EscapedArtifactBoundary)
    graph = parse_graph_config(
        {
            "boundary": {"type": "bad.artifact", "provides": ["io.result"]},
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
        }
    )
    with pytest.raises(PipelineRuntimeError, match="outside controlled paths"):
        PipelineRuntime(graph, registry=_registry(), boundary_registry=boundary_registry, run_dir=tmp_path / "run").run()

def test_boundary_failure_stops_loop_with_boundary_failed_reason(tmp_path) -> None:
    boundary_registry = BoundaryRegistry()
    boundary_registry.register("test.failing_boundary", FailingBoundary)
    graph = parse_graph_config(
        {
            "boundary": {
                "type": "test.failing_boundary",
                "config": {"run_dir": str(tmp_path / "run")},
                "consumes": ["effects.request"],
                "provides": ["io.result"],
            },
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "effect",
                        "type": "test.effect_request",
                        "requires": ["value.in"],
                        "provides": ["effects.request"],
                    }
                ],
                "edges": [{"from": "effect", "to": "effect", "loop": "effect_loop"}],
                "loops": [{"name": "effect_loop", "edges": [["effect", "effect"]], "max_iterations": 2}],
            },
        }
    )
    runtime = PipelineRuntime(graph, registry=_registry(), boundary_registry=boundary_registry)
    with pytest.raises(PipelineRuntimeError, match="boundary after_iteration failed"):
        runtime.run({"value": {"in": 10}})
    assert runtime.trace.loop_stop_reasons == {"effect_loop": "boundary_failed", "runtime": "boundary_failed"}

def test_boundary_schema_and_node_registry_isolation() -> None:
    findings = collect_config_schema_findings(
        {
            "boundary": {
                "type": "test.boundary",
                "config": [],
                "consumes": ["bad.request"],
                "provides": ["bad.result"],
                "allowed_paths": "runs",
            },
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    assert "CONFIG.SCHEMA.BOUNDARY_CONFIG" in rule_ids
    assert "CONFIG.SCHEMA.BOUNDARY_STRING_LIST" in rule_ids
    assert "CONFIG.SCHEMA.BOUNDARY_CONSUMES_KEY" in rule_ids
    assert "CONFIG.SCHEMA.BOUNDARY_PROVIDES_KEY" in rule_ids

    boundary_registry = BoundaryRegistry()
    boundary_registry.register("test.boundary", DemoBoundary)
    with pytest.raises(Exception, match="boundary class cannot be registered as a node"):
        NodeRegistry().register("test.boundary", DemoBoundary, config_schema={}, config_defaults={})

def test_checked_run_writes_reproducible_artifacts_without_raw_inputs(tmp_path) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": 4},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 3},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(
        config_path,
        registry=_registry(),
        initial={"secret": "top-secret-value"},
        run_root=tmp_path / "runs",
        run_id="run_001",
    )
    assert result.run_id == "run_001"
    assert result.context.get("value.out") == 7
    expected_files = {
        "input_summary.json",
        "effective_policy.json",
        "compiled_graph.json",
        "health_report.json",
        "graph.mmd",
        "runtime_trace.jsonl",
        "boundary_trace.jsonl",
        "output_summary.json",
    }
    assert expected_files <= {path.name for path in result.run_dir.iterdir()}
    input_summary = json.loads((result.run_dir / "input_summary.json").read_text(encoding="utf-8"))
    assert input_summary["secret"] == {"size": 16, "type": "str"}
    assert "top-secret-value" not in (result.run_dir / "input_summary.json").read_text(encoding="utf-8")
    compiled = json.loads((result.run_dir / "compiled_graph.json").read_text(encoding="utf-8"))
    assert compiled["data_edges"] == [["seed", "add"]]
    graph_mmd = (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    for edge in compiled["effective_edges"]:
        assert f'{edge["from"]} -->|max={edge["max_executions"]}| {edge["to"]}' in graph_mmd
    assert "provides: value.out" in graph_mmd
    trace_lines = [json.loads(line) for line in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["kind"] for event in trace_lines[:2]] == ["node", "node"]
    assert trace_lines[-1]["kind"] == "runtime_summary"
    assert "top-secret-value" not in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8")
    assert (result.run_dir / "boundary_trace.jsonl").read_text(encoding="utf-8") == ""
