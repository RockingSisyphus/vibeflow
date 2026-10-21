from __future__ import annotations
from tests.fixtures.support.declarations import native_registry
from tests.fixtures.support.declarations import node_declaration, configured_declaration

import json
import re

from vibeflow.core import DataProvider, DataRequirement
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.targets.python.project import NodeRegistry
from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor
from vibeflow.targets.python.quality import validate_graph_health
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.targets.python.rules.node.policy import PurityPolicy
from vibeflow.core.rules.models import plain

from tests.fixtures.support.strict_support import INPUT_SPEC, PROV_SPEC, REQ_SPEC, _edge_chain, _node_call, _registry


def _env(inputs, data_type: str):
    return inputs[data_type]["value"]


def _req(data_type: str) -> DataRequirement:
    return DataRequirement(data_type, "exactly_one", display_name=data_type)


def _prov(key: str) -> DataProvider:
    return DataProvider(key, key, display_name=key)


GuideStart_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.start', display_name='Start', description='Starts a neutral guide flow.', version='1.0.0', flow_kind='terminal', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(examples=({'inputs': {}, 'params': {}},)), rulesets=("vibeflow.process",))

class GuideStart:

    def run_pure(self, inputs, params):
        return {}


GuardSecond_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guard.second', display_name='Guard Second', description='Requires both the original and first result for a guardrail fixture.', version='1.0.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('value.in'), _req('value.out')), provides=(DataProvider('value.final', 'value.in', display_name='Value Final'),), input_semantics={'value.in': ('original value',), 'value.out': ('first result',)}, output_semantics={'value.final': ('final value compatible with value.in',)}), rulesets=("vibeflow.process",))

class GuardSecond:

    def run_pure(self, inputs, params):
        return {"value.final": _env(inputs, "value.out")}


GuardNormalize_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guard.normalize', display_name='Guard Normalize', description='Normalizes value.out into a value.in-compatible key.', version='1.0.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('value.out'),), provides=(DataProvider('value.normalized', 'value.in', display_name='Value Normalized'),), input_semantics={'value.out': ('value to normalize',)}, output_semantics={'value.normalized': ('normalized value',)}), rulesets=("vibeflow.process",))

class GuardNormalize:

    def run_pure(self, inputs, params):
        return {"value.normalized": _env(inputs, "value.out")}


GuardConsume_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guard.consume', display_name='Guard Consume', description='Consumes a mainline and bypassed value.', version='1.0.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('value.in'), _req('value.out')), provides=(DataProvider('value.final', 'value.out', display_name='Value Final'),), input_semantics={'value.in': ('mainline normalized value',), 'value.out': ('bypassed result',)}, output_semantics={'value.final': ('combined final value',)}), rulesets=("vibeflow.process",))

class GuardConsume:

    def run_pure(self, inputs, params):
        return {"value.final": _env(inputs, "value.in")}


GuideEnd_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.end', display_name='End', description='Ends a neutral guide flow.', version='1.0.0', flow_kind='terminal', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(examples=({'inputs': {}, 'params': {}},)), rulesets=("vibeflow.process",))

class GuideEnd:

    def run_pure(self, inputs, params):
        return {}


GuideRoute_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.route', display_name='Route', description='Selects a neutral branch.', version='1.0.0', flow_kind='decision', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(provides=(_prov('flow.route'),), output_semantics={'flow.route': ('selected branch',)}, examples=({'inputs': {}, 'params': {}},)), rulesets=("vibeflow.process",))

class GuideRoute:

    def run_pure(self, inputs, params):
        return {"flow.route": "left"}


GuideSource_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.source', display_name='Source', description='Produces two neutral values.', version='1.0.0', flow_kind='io', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(provides=(_prov('record.original'), _prov('record.current')), output_semantics={'record.original': ('original record',), 'record.current': ('current record',)}, examples=({'inputs': {}, 'params': {}},)), rulesets=("vibeflow.io",))

class GuideSource:

    def run_pure(self, inputs, params):
        return {"record.original": " Alpha ", "record.current": " Alpha "}


GuideNormalize_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.normalize', display_name='Normalize', description='Normalizes one value.', version='1.0.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('record.current'),), provides=(_prov('record.normalized'),), input_semantics={'record.current': ('current record',)}, output_semantics={'record.normalized': ('normalized record',)}, examples=({'inputs': {'record.current': {'key': 'record.current', 'type': 'record.current', 'value': ' A ', 'source_node': 'example'}}, 'params': {}},)), rulesets=("vibeflow.process",))

class GuideNormalize:

    def run_pure(self, inputs, params):
        return {"record.normalized": str(_env(inputs, "record.current")).strip().lower()}


GuideCombine_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.combine', display_name='Combine', description='Combines two values.', version='1.0.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('record.original'), _req('record.normalized')), provides=(_prov('semantic.combined'),), input_semantics={'record.original': ('original record',), 'record.normalized': ('normalized record',)}, output_semantics={'semantic.combined': ('combined record',)}, examples=({'inputs': {'record.original': {'key': 'record.original', 'type': 'record.original', 'value': ' A ', 'source_node': 'example'}, 'record.normalized': {'key': 'record.normalized', 'type': 'record.normalized', 'value': 'a', 'source_node': 'example'}}, 'params': {}},)), rulesets=("vibeflow.process",))

class GuideCombine:

    def run_pure(self, inputs, params):
        return {"semantic.combined": [_env(inputs, "record.original"), _env(inputs, "record.normalized")]}


GuideOutputValue_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.output_value', display_name='Output Value', description='Adapts a combined value.', version='1.0.0', flow_kind='io', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('semantic.combined'),), provides=(_prov('response.value'),), input_semantics={'semantic.combined': ('combined record',)}, output_semantics={'response.value': ('external response',)}, examples=({'inputs': {'semantic.combined': {'key': 'semantic.combined', 'type': 'semantic.combined', 'value': ['A', 'a'], 'source_node': 'example'}}, 'params': {}},)), rulesets=("vibeflow.io",))

class GuideOutputValue:

    def run_pure(self, inputs, params):
        return {"response.value": _env(inputs, "semantic.combined")}


GuideLeft_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.left', display_name='Left', description='Produces the left branch.', version='1.0.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(provides=(_prov('branch.left'),), output_semantics={'branch.left': ('left value',)}, examples=({'inputs': {}, 'params': {}},)), rulesets=("vibeflow.process",))

class GuideLeft:

    def run_pure(self, inputs, params):
        return {"branch.left": 2}


GuideRight_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.right', display_name='Right', description='Produces the right branch.', version='1.0.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(provides=(_prov('branch.right'),), output_semantics={'branch.right': ('right value',)}, examples=({'inputs': {}, 'params': {}},)), rulesets=("vibeflow.process",))

class GuideRight:

    def run_pure(self, inputs, params):
        return {"branch.right": 3}


GuideMerge_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.merge', display_name='Merge', description='Merges two branches.', version='1.0.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('branch.left'), _req('branch.right')), provides=(_prov('semantic.merged'),), input_semantics={'branch.left': ('left value',), 'branch.right': ('right value',)}, output_semantics={'semantic.merged': ('merged value',)}, examples=({'inputs': {'branch.left': {'key': 'branch.left', 'type': 'branch.left', 'value': 2, 'source_node': 'example'}, 'branch.right': {'key': 'branch.right', 'type': 'branch.right', 'value': 3, 'source_node': 'example'}}, 'params': {}},)), rulesets=("vibeflow.process",))

class GuideMerge:

    def run_pure(self, inputs, params):
        return {"semantic.merged": _env(inputs, "branch.left") + _env(inputs, "branch.right")}


GuideOutputMerged_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.output_merged', display_name='Output Merged', description='Adapts a merged value.', version='1.0.0', flow_kind='io', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('semantic.merged'),), provides=(_prov('response.value'),), input_semantics={'semantic.merged': ('merged value',)}, output_semantics={'response.value': ('external response',)}, examples=({'inputs': {'semantic.merged': {'key': 'semantic.merged', 'type': 'semantic.merged', 'value': 5, 'source_node': 'example'}}, 'params': {}},)), rulesets=("vibeflow.io",))

class GuideOutputMerged:

    def run_pure(self, inputs, params):
        return {"response.value": _env(inputs, "semantic.merged")}


GuideInput_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.input', display_name='Input', description='Decodes an external value.', version='1.0.0', flow_kind='io', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('request.raw'),), provides=(_prov('input.text'),), input_semantics={'request.raw': ('raw request',)}, output_semantics={'input.text': ('decoded text',)}, examples=({'inputs': {'request.raw': {'key': 'request.raw', 'type': 'request.raw', 'value': '7', 'source_node': 'example'}}, 'params': {}},)), rulesets=("vibeflow.io",))

class GuideInput:

    def run_pure(self, inputs, params):
        return {"input.text": str(_env(inputs, "request.raw"))}


GuideSemantic_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.semantic', display_name='Semantic', description='Builds a typed value.', version='1.0.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('input.text'),), provides=(_prov('semantic.number'),), input_semantics={'input.text': ('decoded text',)}, output_semantics={'semantic.number': ('typed number',)}, examples=({'inputs': {'input.text': {'key': 'input.text', 'type': 'input.text', 'value': '7', 'source_node': 'example'}}, 'params': {}},)), rulesets=("vibeflow.process",))

class GuideSemantic:

    def run_pure(self, inputs, params):
        return {"semantic.number": int(_env(inputs, "input.text"))}


GuideOutputNumber_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='guide.output_number', display_name='Output Number', description='Adapts a typed number.', version='1.0.0', flow_kind='io', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(_req('semantic.number'),), provides=(_prov('response.number'),), input_semantics={'semantic.number': ('typed number',)}, output_semantics={'response.number': ('external number',)}, examples=({'inputs': {'semantic.number': {'key': 'semantic.number', 'type': 'semantic.number', 'value': 7, 'source_node': 'example'}}, 'params': {}},)), rulesets=("vibeflow.io",))

class GuideOutputNumber:

    def run_pure(self, inputs, params):
        return {"response.number": _env(inputs, "semantic.number")}


def _guide_registry() -> NodeRegistry:
    registry = native_registry()
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
        registry.register(configured_declaration(globals()[node_cls.__name__ + "_DECLARATION"]), node_cls)
    return registry


def _health(pipeline: dict):
    graph = parse_graph_config({"pipeline": pipeline})
    registry = _registry()
    for node_cls in (GuardSecond, GuardNormalize, GuardConsume):
        registry.register(configured_declaration(globals()[node_cls.__name__ + "_DECLARATION"]), node_cls)
    return validate_graph_health(
        graph,
        registry=registry,
        purity_policy=PurityPolicy(max_source_lines=1000),
    )


def test_runtime_guardrails_reject_empty_start_shortcut_and_transfer_only_all_join() -> None:
    report = _health(
        {
            "inputs": [INPUT_SPEC("value.in")],
            "nodes": [
                _node_call("start", "test.start", "Starts the sequential workflow."),
                _node_call(
                    "first",
                    "test.add",
                    "Consumes the injected input and produces the first semantic result.",

                ),
                _node_call(
                    "second",
                    "guard.second",
                    "Needs both the original input and the first result.",

                    join_policy="all",
                ),
                _node_call("end", "test.in_end", "Ends after the final value."),
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
    assert plain(unreachable.details["schedule_incoming"]) == [{"from": "first", "to": "second", "when": ""}]
    assert {edge["from"] for edge in unreachable.details["transfer_incoming"]} == {"first", "start"}
    assert plain(no_payload.details["source_provider_types"]) == []
    assert plain(no_payload.details["target_required_types"]) == ["value.in", "value.out"]
    assert plain(bad_join.details["schedule_incoming"]) == [{"source": "first", "target": "second", "when": ""}]
    assert plain(bad_join.details["transfer_only_incoming"]) == [{"source": "start", "target": "second", "when": ""}]


def test_runtime_guardrails_allow_payload_bypass_on_a_sequential_control_spine() -> None:
    report = _health(
        {
            "inputs": [INPUT_SPEC("value.in")],
            "nodes": [
                _node_call("start", "test.start", "Starts the sequential workflow."),
                _node_call(
                    "produce",
                    "test.add",
                    "Produces a value that is needed again downstream.",

                ),
                _node_call(
                    "normalize",
                    "guard.normalize",
                    "Produces the mainline value.",

                ),
                _node_call(
                    "consume",
                    "guard.consume",
                    "Consumes one mainline value and one legitimate bypassed value.",

                ),
                _node_call("end", "test.out_end", "Ends after the final value."),
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
                _node_call("seed", "test.seed", "Produces the only input."),
                _node_call(
                    "join",
                    "test.add",
                    "Has no parallel branches to join.",

                    join_policy="all",
                ),
                _node_call("end", "test.out_end", "Ends after the output."),
            ],
            "edges": _edge_chain("start", "seed", "join", "end"),
        }
    )

    warning = next(item for item in report.warnings if item.rule_id == "GRAPH.JOIN.REDUNDANT_ALL")
    assert warning.details["node"] == "join"
    assert plain(warning.details["schedule_incoming"]) == [{"source": "seed", "target": "join", "when": ""}]
    assert plain(warning.details["transfer_only_incoming"]) == []


def test_join_policy_all_with_two_parallel_schedule_branches_remains_legal() -> None:
    report = _health(
        {
            "nodes": [
                _node_call("start", "test.start", "Starts two real branches."),
                _node_call("left", "test.seed", "Produces the left value."),
                _node_call("right", "test.seed", "Produces the right value."),
                _node_call(
                    "join",
                    "test.add",
                    "Waits for both real branches.",

                    join_policy="all",
                ),
                _node_call("end", "test.out_end", "Ends after the output."),
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

                    ),
                    _node_call(
                        "left",
                        "guide.left",
                        "Produces the left branch value.",

                    ),
                    _node_call(
                        "right",
                        "guide.right",
                        "Produces the right branch value.",

                    ),
                    _node_call(
                        "merge",
                        "guide.merge",
                        "Waits for both schedule branches.",

                        join_policy="all",
                    ),
                    _node_call(
                        "output",
                        "guide.output_merged",
                        "Adapts the merged result.",

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
    assert plain(finding.details["schedule_incoming"]) == [
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
    from pathlib import Path

    repository_root = Path(__file__).resolve().parents[3]
    guide = repository_root / "distribution" / "docs" / "user" / "workflow-and-config.md"
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
    from pathlib import Path

    repository_root = Path(__file__).resolve().parents[3]
    guides = [
        repository_root / "distribution" / "prompts" / "common.md",
        repository_root / "docs" / "design" / "execution-model.md",
        repository_root / "distribution" / "docs" / "user" / "commands-and-results.md",
    ]
    contents = {path: path.read_text(encoding="utf-8") for path in guides}
    combined = "\n".join(contents.values())
    for concept in (
        "global_state",
        "execution_lock",
        "detached",
        "result_key",
        "工作流执行探针",
        "业务结果正确性",
    ):
        assert concept in combined, concept
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
