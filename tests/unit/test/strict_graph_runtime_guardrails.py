from __future__ import annotations

import json
import re
from pathlib import Path

from vibeflow import (
    DataProvider,
    DataRequirement,
    NodeContract,
    NodeInfo,
    NodeRegistry,
    PipelineRuntime,
    RuntimeOptions,
    parse_graph_config,
    validate_graph_health,
)
from vibeflow.purity.types import PurityPolicy

from tests.unit.strict_support import PROV_SPEC, REQ_SPEC, _edge_chain, _node_call, _registry


def _env(inputs, data_type: str):
    return inputs[data_type]["value"]


def _req(data_type: str) -> DataRequirement:
    return DataRequirement(data_type, "exactly_one")


def _prov(key: str) -> DataProvider:
    return DataProvider(key, key)


class GuideStart:
    NODE_INFO = NodeInfo("guide.start", "Start", "guide", "Starts a neutral guide flow.", "1.0.0", "terminal")
    CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}},))

    def run_pure(self, inputs, params):
        return {}


class GuideEnd:
    NODE_INFO = NodeInfo("guide.end", "End", "guide", "Ends a neutral guide flow.", "1.0.0", "terminal")
    CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}},))

    def run_pure(self, inputs, params):
        return {}


class GuideRoute:
    NODE_INFO = NodeInfo("guide.route", "Route", "guide", "Selects a neutral branch.", "1.0.0", "decision")
    CONTRACT = NodeContract(
        provides=(_prov("flow.route"),),
        output_semantics={"flow.route": ("selected branch",)},
        output_schema={"flow.route": {"type": "string"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"flow.route": "left"}


class GuideSource:
    NODE_INFO = NodeInfo("guide.source", "Source", "guide", "Produces two neutral values.", "1.0.0", "io")
    CONTRACT = NodeContract(
        provides=(_prov("record.original"), _prov("record.current")),
        output_semantics={"record.original": ("original record",), "record.current": ("current record",)},
        output_schema={"record.original": {"type": "string"}, "record.current": {"type": "string"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"record.original": " Alpha ", "record.current": " Alpha "}


class GuideNormalize:
    NODE_INFO = NodeInfo("guide.normalize", "Normalize", "guide", "Normalizes one value.", "1.0.0", "process")
    CONTRACT = NodeContract(
        requires=(_req("record.current"),),
        provides=(_prov("record.normalized"),),
        input_semantics={"record.current": ("current record",)},
        output_semantics={"record.normalized": ("normalized record",)},
        output_schema={"record.normalized": {"type": "string"}},
        examples=({"inputs": {"record.current": {"key": "record.current", "type": "record.current", "value": " A ", "source_node": "example"}}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"record.normalized": str(_env(inputs, "record.current")).strip().lower()}


class GuideCombine:
    NODE_INFO = NodeInfo("guide.combine", "Combine", "guide", "Combines two values.", "1.0.0", "process")
    CONTRACT = NodeContract(
        requires=(_req("record.original"), _req("record.normalized")),
        provides=(_prov("semantic.combined"),),
        input_semantics={"record.original": ("original record",), "record.normalized": ("normalized record",)},
        output_semantics={"semantic.combined": ("combined record",)},
        output_schema={"semantic.combined": {"type": "array"}},
        examples=({"inputs": {"record.original": {"key": "record.original", "type": "record.original", "value": " A ", "source_node": "example"}, "record.normalized": {"key": "record.normalized", "type": "record.normalized", "value": "a", "source_node": "example"}}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"semantic.combined": [_env(inputs, "record.original"), _env(inputs, "record.normalized")]}


class GuideOutputValue:
    NODE_INFO = NodeInfo("guide.output_value", "Output Value", "guide", "Adapts a combined value.", "1.0.0", "io")
    CONTRACT = NodeContract(
        requires=(_req("semantic.combined"),),
        provides=(_prov("response.value"),),
        input_semantics={"semantic.combined": ("combined record",)},
        output_semantics={"response.value": ("external response",)},
        output_schema={"response.value": {"type": "array"}},
        examples=({"inputs": {"semantic.combined": {"key": "semantic.combined", "type": "semantic.combined", "value": ["A", "a"], "source_node": "example"}}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"response.value": _env(inputs, "semantic.combined")}


class GuideLeft:
    NODE_INFO = NodeInfo("guide.left", "Left", "guide", "Produces the left branch.", "1.0.0", "process")
    CONTRACT = NodeContract(provides=(_prov("branch.left"),), output_semantics={"branch.left": ("left value",)}, output_schema={"branch.left": {"type": "number"}}, examples=({"inputs": {}, "params": {}},))

    def run_pure(self, inputs, params):
        return {"branch.left": 2}


class GuideRight:
    NODE_INFO = NodeInfo("guide.right", "Right", "guide", "Produces the right branch.", "1.0.0", "process")
    CONTRACT = NodeContract(provides=(_prov("branch.right"),), output_semantics={"branch.right": ("right value",)}, output_schema={"branch.right": {"type": "number"}}, examples=({"inputs": {}, "params": {}},))

    def run_pure(self, inputs, params):
        return {"branch.right": 3}


class GuideMerge:
    NODE_INFO = NodeInfo("guide.merge", "Merge", "guide", "Merges two branches.", "1.0.0", "process")
    CONTRACT = NodeContract(
        requires=(_req("branch.left"), _req("branch.right")),
        provides=(_prov("semantic.merged"),),
        input_semantics={"branch.left": ("left value",), "branch.right": ("right value",)},
        output_semantics={"semantic.merged": ("merged value",)},
        output_schema={"semantic.merged": {"type": "number"}},
        examples=({"inputs": {"branch.left": {"key": "branch.left", "type": "branch.left", "value": 2, "source_node": "example"}, "branch.right": {"key": "branch.right", "type": "branch.right", "value": 3, "source_node": "example"}}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"semantic.merged": _env(inputs, "branch.left") + _env(inputs, "branch.right")}


class GuideOutputMerged:
    NODE_INFO = NodeInfo("guide.output_merged", "Output Merged", "guide", "Adapts a merged value.", "1.0.0", "io")
    CONTRACT = NodeContract(
        requires=(_req("semantic.merged"),),
        provides=(_prov("response.value"),),
        input_semantics={"semantic.merged": ("merged value",)},
        output_semantics={"response.value": ("external response",)},
        output_schema={"response.value": {"type": "number"}},
        examples=({"inputs": {"semantic.merged": {"key": "semantic.merged", "type": "semantic.merged", "value": 5, "source_node": "example"}}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"response.value": _env(inputs, "semantic.merged")}


class GuideInput:
    NODE_INFO = NodeInfo("guide.input", "Input", "guide", "Decodes an external value.", "1.0.0", "io")
    CONTRACT = NodeContract(
        requires=(_req("request.raw"),),
        provides=(_prov("input.text"),),
        input_semantics={"request.raw": ("raw request",)},
        output_semantics={"input.text": ("decoded text",)},
        output_schema={"input.text": {"type": "string"}},
        examples=({"inputs": {"request.raw": {"key": "request.raw", "type": "request.raw", "value": "7", "source_node": "example"}}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"input.text": str(_env(inputs, "request.raw"))}


class GuideSemantic:
    NODE_INFO = NodeInfo("guide.semantic", "Semantic", "guide", "Builds a typed value.", "1.0.0", "process")
    CONTRACT = NodeContract(
        requires=(_req("input.text"),),
        provides=(_prov("semantic.number"),),
        input_semantics={"input.text": ("decoded text",)},
        output_semantics={"semantic.number": ("typed number",)},
        output_schema={"semantic.number": {"type": "integer"}},
        examples=({"inputs": {"input.text": {"key": "input.text", "type": "input.text", "value": "7", "source_node": "example"}}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"semantic.number": int(_env(inputs, "input.text"))}


class GuideOutputNumber:
    NODE_INFO = NodeInfo("guide.output_number", "Output Number", "guide", "Adapts a typed number.", "1.0.0", "io")
    CONTRACT = NodeContract(
        requires=(_req("semantic.number"),),
        provides=(_prov("response.number"),),
        input_semantics={"semantic.number": ("typed number",)},
        output_semantics={"response.number": ("external number",)},
        output_schema={"response.number": {"type": "integer"}},
        examples=({"inputs": {"semantic.number": {"key": "semantic.number", "type": "semantic.number", "value": 7, "source_node": "example"}}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"response.number": _env(inputs, "semantic.number")}


def _guide_registry() -> NodeRegistry:
    registry = NodeRegistry()
    for node_cls in (
        GuideStart,
        GuideEnd,
        GuideRoute,
        GuideSource,
        GuideNormalize,
        GuideCombine,
        GuideOutputValue,
        GuideLeft,
        GuideRight,
        GuideMerge,
        GuideOutputMerged,
        GuideInput,
        GuideSemantic,
        GuideOutputNumber,
    ):
        registry.register(node_cls.NODE_INFO.type_key, node_cls, config_schema={}, config_defaults={})
    return registry


def _health(pipeline: dict):
    graph = parse_graph_config({"pipeline": pipeline})
    return validate_graph_health(
        graph,
        registry=_registry(),
        purity_policy=PurityPolicy(max_source_lines=1000),
    )


def test_runtime_guardrails_reject_empty_start_shortcut_and_transfer_only_all_join() -> None:
    report = _health(
        {
            "inputs": [PROV_SPEC("value.in")],
            "nodes": [
                _node_call("start", "test.start", "Starts the sequential workflow."),
                _node_call(
                    "first",
                    "test.add",
                    "Consumes the injected input and produces the first semantic result.",
                    requires=[REQ_SPEC("value.in")],
                    provides=[PROV_SPEC("value.out")],
                ),
                _node_call(
                    "second",
                    "test.copy",
                    "Needs both the original input and the first result.",
                    requires=[REQ_SPEC("value.in"), REQ_SPEC("value.out")],
                    provides=[PROV_SPEC("value.final", "value.in")],
                    join_policy="all",
                ),
                _node_call("end", "test.in_end", "Ends after the final value.", requires=[REQ_SPEC("value.in")]),
            ],
            "edges": [
                {"from": "start", "to": "first"},
                {"from": "first", "to": "second"},
                {"from": "start", "to": "second"},
                {"from": "second", "to": "end"},
            ],
        }
    )

    unreachable = next(item for item in report.errors if item.rule_id == "GRAPH.DATA.RUNTIME_REQUIREMENT_UNREACHABLE")
    no_payload = next(item for item in report.errors if item.rule_id == "GRAPH.DATA.NO_PAYLOAD_BYPASS")
    bad_join = next(item for item in report.errors if item.rule_id == "GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY")

    assert unreachable.details["node"] == "second"
    assert unreachable.details["required_type"] == "value.in"
    assert unreachable.details["accepts_initial_input"] is False
    assert unreachable.details["schedule_incoming"] == [{"from": "first", "to": "second", "when": ""}]
    assert {edge["from"] for edge in unreachable.details["transfer_incoming"]} == {"first", "start"}
    assert no_payload.details["source_provider_types"] == []
    assert no_payload.details["target_required_types"] == ["value.in", "value.out"]
    assert bad_join.details["schedule_incoming"] == [{"source": "first", "target": "second", "when": ""}]
    assert bad_join.details["transfer_only_incoming"] == [{"source": "start", "target": "second", "when": ""}]


def test_runtime_guardrails_allow_payload_bypass_on_a_sequential_control_spine() -> None:
    report = _health(
        {
            "inputs": [PROV_SPEC("value.in")],
            "nodes": [
                _node_call("start", "test.start", "Starts the sequential workflow."),
                _node_call(
                    "produce",
                    "test.add",
                    "Produces a value that is needed again downstream.",
                    requires=[REQ_SPEC("value.in")],
                    provides=[PROV_SPEC("value.out")],
                ),
                _node_call(
                    "normalize",
                    "test.copy",
                    "Produces the mainline value.",
                    requires=[REQ_SPEC("value.out")],
                    provides=[PROV_SPEC("value.normalized", "value.in")],
                ),
                _node_call(
                    "consume",
                    "test.add",
                    "Consumes one mainline value and one legitimate bypassed value.",
                    requires=[REQ_SPEC("value.in"), REQ_SPEC("value.out")],
                    provides=[PROV_SPEC("value.final", "value.out")],
                ),
                _node_call("end", "test.out_end", "Ends after the final value.", requires=[REQ_SPEC("value.out")]),
            ],
            "edges": [
                *_edge_chain("start", "produce", "normalize", "consume", "end"),
                {"from": "produce", "to": "consume"},
            ],
        }
    )

    guarded = {
        "GRAPH.DATA.RUNTIME_REQUIREMENT_UNREACHABLE",
        "GRAPH.DATA.NO_PAYLOAD_BYPASS",
        "GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY",
    }
    assert not any(item.rule_id in guarded for item in (*report.errors, *report.warnings))


def test_join_policy_all_with_one_real_predecessor_is_redundant() -> None:
    report = _health(
        {
            "nodes": [
                _node_call("start", "test.start", "Starts the single-predecessor workflow."),
                _node_call("seed", "test.seed", "Produces the only input.", provides=[PROV_SPEC("value.in")]),
                _node_call(
                    "join",
                    "test.add",
                    "Has no parallel branches to join.",
                    requires=[REQ_SPEC("value.in")],
                    provides=[PROV_SPEC("value.out")],
                    join_policy="all",
                ),
                _node_call("end", "test.out_end", "Ends after the output.", requires=[REQ_SPEC("value.out")]),
            ],
            "edges": _edge_chain("start", "seed", "join", "end"),
        }
    )

    warning = next(item for item in report.warnings if item.rule_id == "GRAPH.JOIN.REDUNDANT_ALL")
    assert warning.details["node"] == "join"
    assert warning.details["schedule_incoming"] == [{"source": "seed", "target": "join", "when": ""}]
    assert warning.details["transfer_only_incoming"] == []


def test_join_policy_all_with_two_parallel_schedule_branches_remains_legal() -> None:
    report = _health(
        {
            "nodes": [
                _node_call("start", "test.start", "Starts two real branches."),
                _node_call("left", "test.seed", "Produces the left value.", provides=[PROV_SPEC("value.left", "value.in")]),
                _node_call("right", "test.seed", "Produces the right value.", provides=[PROV_SPEC("value.right", "value.out")]),
                _node_call(
                    "join",
                    "test.add",
                    "Waits for both real branches.",
                    requires=[REQ_SPEC("value.in"), REQ_SPEC("value.out")],
                    provides=[PROV_SPEC("value.final", "value.out")],
                    join_policy="all",
                ),
                _node_call("end", "test.out_end", "Ends after the output.", requires=[REQ_SPEC("value.out")]),
            ],
            "edges": [
                {"from": "start", "to": "left"},
                {"from": "start", "to": "right"},
                {"from": "left", "to": "join"},
                {"from": "right", "to": "join"},
                {"from": "join", "to": "end"},
            ],
        }
    )

    join_findings = {
        "GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY",
        "GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE",
        "GRAPH.JOIN.REDUNDANT_ALL",
    }
    assert not any(item.rule_id in join_findings for item in (*report.errors, *report.warnings))


def _guide_decision_join_health(*, left_when: str, right_when: str):
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "guide.start", "Starts the decision flow."),
                    _node_call(
                        "route",
                        "guide.route",
                        "Selects one or more branches.",
                        provides=[PROV_SPEC("flow.route")],
                    ),
                    _node_call(
                        "left",
                        "guide.left",
                        "Produces the left branch value.",
                        provides=[PROV_SPEC("branch.left")],
                    ),
                    _node_call(
                        "right",
                        "guide.right",
                        "Produces the right branch value.",
                        provides=[PROV_SPEC("branch.right")],
                    ),
                    _node_call(
                        "merge",
                        "guide.merge",
                        "Waits for both schedule branches.",
                        requires=[REQ_SPEC("branch.left"), REQ_SPEC("branch.right")],
                        provides=[PROV_SPEC("semantic.merged")],
                        join_policy="all",
                    ),
                    _node_call(
                        "output",
                        "guide.output_merged",
                        "Adapts the merged result.",
                        requires=[REQ_SPEC("semantic.merged")],
                        provides=[PROV_SPEC("response.value")],
                    ),
                    _node_call("end", "guide.end", "Ends after output adaptation."),
                ],
                "edges": [
                    ["start", "route"],
                    {"from": "route", "to": "left", "when": left_when},
                    {"from": "route", "to": "right", "when": right_when},
                    ["left", "merge"],
                    ["right", "merge"],
                    ["merge", "output"],
                    ["output", "end"],
                ],
                "outputs": [REQ_SPEC("response.value")],
            }
        }
    )
    return validate_graph_health(
        graph,
        registry=_guide_registry(),
        purity_policy=PurityPolicy(max_source_lines=1000, allowed_import_roots=("pathlib",)),
    )


def test_join_policy_all_rejects_mutually_exclusive_decision_branches() -> None:
    report = _guide_decision_join_health(
        left_when="flow.route == 'left'",
        right_when="flow.route == 'right'",
    )

    finding = next(
        item
        for item in report.errors
        if item.rule_id == "GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE"
    )
    assert finding.details["node"] == "merge"
    assert finding.details["schedule_incoming"] == [
        {"source": "left", "target": "merge", "when": ""},
        {"source": "right", "target": "merge", "when": ""},
    ]
    pair = finding.details["exclusive_branch_pairs"][0]
    assert pair["decision"] == "route"
    assert pair["condition_key"] == "flow.route"
    assert pair["left_predecessor"] == "left"
    assert pair["right_predecessor"] == "right"
    assert pair["left_conditions"][0]["value"] == "left"
    assert pair["right_conditions"][0]["value"] == "right"


def test_join_policy_all_allows_same_condition_decision_fanout() -> None:
    report = _guide_decision_join_health(
        left_when="flow.route == 'both'",
        right_when="flow.route == 'both'",
    )

    assert not any(
        item.rule_id == "GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE"
        for item in (*report.errors, *report.warnings)
    )


def test_documented_neutral_topologies_are_extracted_validated_and_executed(tmp_path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    guide = repository_root / "distribution" / "kernel_development_pack" / "docs" / "03_Config与Pipeline规范.md"
    pattern = re.compile(
        r"<!-- vibeflow-executable-example: ([a-z0-9-]+) -->\s*```jsonc\n(.*?)\n```",
        re.DOTALL,
    )
    examples = {name: json.loads(payload) for name, payload in pattern.findall(guide.read_text(encoding="utf-8"))}

    assert set(examples) == {"sequential-bypass", "parallel-all-join", "typed-io-boundaries"}
    expected_outputs = {
        "sequential-bypass": ("response.value", [" Alpha ", "alpha"], list),
        "parallel-all-join": ("response.value", 5, int),
        "typed-io-boundaries": ("response.number", 7, int),
    }
    registry = _guide_registry()
    guarded = {
        "GRAPH.DATA.RUNTIME_REQUIREMENT_UNREACHABLE",
        "GRAPH.DATA.NO_PAYLOAD_BYPASS",
        "GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY",
        "GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE",
        "GRAPH.JOIN.REDUNDANT_ALL",
    }

    for name, payload in examples.items():
        graph = parse_graph_config(payload)
        report = validate_graph_health(
            graph,
            registry=registry,
            purity_policy=PurityPolicy(max_source_lines=1000, allowed_import_roots=("pathlib",)),
        )
        assert report.status == "PASS", (name, report.to_dict())
        assert not any(item.rule_id in guarded for item in (*report.errors, *report.warnings)), name
        initial = {"request.raw": "7"} if name == "typed-io-boundaries" else {}
        result = PipelineRuntime(
            graph,
            registry=registry,
            run_dir=tmp_path / name,
            runtime_options=RuntimeOptions(trace="boundary", execution="plan"),
        ).run(initial)
        output_key, expected_value, expected_type = expected_outputs[name]
        envelope = result.get(output_key)
        assert envelope is not None
        assert envelope["value"] == expected_value
        assert type(envelope["value"]) is expected_type
        assert result.get("runtime.stop_reason") == "completed"
        assert result.get("runtime.qualified_exec_order")


def test_ai_guidance_is_generic_and_contains_required_runtime_guardrails() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    guides = [
        repository_root / "distribution" / "kernel_development_pack" / "project_template" / "AGENTS.md",
        repository_root / "distribution" / "kernel_development_pack" / "docs" / "03_Config与Pipeline规范.md",
        repository_root / "distribution" / "kernel_development_pack" / "docs" / "04_Nodeset规范与用法.md",
        repository_root / "distribution" / "kernel_development_pack" / "docs" / "08_给AI开发者的约束清单.md",
        repository_root / "docs" / "developer_guide.md",
    ]
    required_per_file = {
        guides[0]: ("terminal", "input I/O", "output I/O", "runtime probe", "qualified_exec_order", "tagged value"),
        guides[1]: ("terminal", "input I/O", "output I/O", "qualified_exec_order", "tag"),
        guides[2]: ("terminal", "input I/O", "output I/O", "runtime probe", "qualified_exec_order", "tagged value"),
        guides[3]: ("terminal", "input I/O", "output I/O", "runtime probe", "qualified_exec_order", "tagged value"),
        guides[4]: ("terminal", "input I/O", "output I/O", "runtime probe", "qualified_exec_order", "tagged value"),
    }
    diagnostic_ids = (
        "GRAPH.DATA.RUNTIME_REQUIREMENT_UNREACHABLE",
        "GRAPH.DATA.NO_PAYLOAD_BYPASS",
        "GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY",
        "GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE",
        "GRAPH.JOIN.REDUNDANT_ALL",
    )
    contents = {path: path.read_text(encoding="utf-8") for path in guides}
    for path, concepts in required_per_file.items():
        for concept in (*concepts, *diagnostic_ids):
            assert concept in contents[path], (path, concept)
    combined = "\n".join(contents.values())
    forbidden = (
        "NITR-",
        "SCBench",
        "filter.parse_result",
        "submission.eligible",
        "session.report",
        "config.request",
        "hidden fixture",
        "reference implementation",
        "candidate workspace",
    )
    for path, content in contents.items():
        assert not any(fragment in content for fragment in forbidden), path
