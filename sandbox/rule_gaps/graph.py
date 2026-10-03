"""Finite, durable Rule graph gaps through Python and TS plugin boundaries.

The desired contracts remain strict when today's implementation is deficient.
No production monkeypatch, fabricated source metric, xfail, or skipped Target is
used. ``review-rules`` intentionally previews static and executes no handler.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import traceback


def _support():
    spec = importlib.util.spec_from_file_location("rule_gaps_graph_support", Path(__file__).with_name("graph_support.py"))
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _replacement(s, case, target, explicit):
    replacement = case.read(case.rule("replacement"))
    replacement["params_schema"]["bonus"] = {"type": "integer"}
    replacement["params_defaults"].update(value=20, bonus=2)
    case.write(case.rule("replacement"), replacement)
    source = case.source("provider")
    text = source.read_text()
    if target == "python":
        text = text.replace('params["value"] + 10', 'params["value"] + params["bonus"]')
    else:
        text = text.replace('params.value+10', 'params.value+params.bonus')
    source.write_text(text)
    overrides = {"source": "$self", "target": "provider", "kind": "overrides", "replace_rule": "example.replacement_provider"}
    if explicit:
        overrides["params"] = {"value": 5}
    s.graph(case, [{"id": "provider", "rule_id": "example.number_provider"},
                   {"id": "checker", "rule_id": "example.number_checker"}],
            [s.pair(), overrides], entrypoints={"static": ["checker"]})
    code, payload = case.command()
    events = case.events()
    checks = [event for event in events if event["handler"] == "checker"]
    actual = s.observation(code, payload, metrics={"total": checks[-1]["total"] if checks else None})
    mode = "override" if explicit else "defaults"
    rows = [s.row("replacement." + mode + ".validate", target,
                  "替换 Rule 的不同默认值与新增参数真正进入 handler", "replacement",
                  s.acceptance(total=7 if explicit else 22), actual)]
    executions = payload.get("info", {}).get("rule_executions", ())
    if target == "javascript":
        def execution_plans(value):
            if isinstance(value, dict):
                if "plan" in value and "results" in value:
                    yield value
                for child in value.values():
                    yield from execution_plans(child)
            elif isinstance(value, list):
                for child in value:
                    yield from execution_plans(child)
        executions = list(execution_plans(payload))
    runtime_provider = next((call for execution in executions for call in execution["plan"]["calls"] if call["id"] == "provider"), {})
    runtime_sources = runtime_provider.get("parameter_sources", {})
    rows.append(s.row("replacement." + mode + ".formal_sources", target,
        "正式 validate 的有效计划也保留替换后的参数来源", "replacement",
        s.acceptance(value_source="override:$self" if explicit else "default:example.replacement_provider",
                     bonus_source="default:example.replacement_provider"),
        s.observation(code, payload, metrics={"value_source": runtime_sources.get("value"), "bonus_source": runtime_sources.get("bonus")})))
    before = len(events)
    code, payload = case.command("review-rules", "--node", "calculate")
    calls = [call for node in payload.get("nodes", []) for plan in node["plans"] for call in plan["calls"]]
    provider = next((call for call in calls if call["id"] == "provider"), {})
    metrics = {"value": provider.get("params", {}).get("value"), "bonus": provider.get("params", {}).get("bonus"),
               "value_source": provider.get("parameter_sources", {}).get("value"),
               "bonus_source": provider.get("parameter_sources", {}).get("bonus"),
               "original_rule": provider.get("original_rule_id"), "actual_rule": provider.get("rule_id"),
               "new_handler_events": len(case.events()) - before}
    rows.append(s.row("replacement." + mode + ".preview", target,
        "正式规则预览按替换后声明标明全部有效参数来源", "replacement",
        s.acceptance(value=5 if explicit else 20, bonus=2,
                     value_source="override:$self" if explicit else "default:example.replacement_provider",
                     bonus_source="default:example.replacement_provider", original_rule="example.number_provider",
                     actual_rule="example.replacement_provider", new_handler_events=0),
        s.observation(code, payload, metrics=metrics)))
    return rows


def _includes(s, case, target, bad):
    calls = [{"id": name, "rule_id": "example.number_provider", "params": {"mode": "error" if name == "bad" else "valid"}}
             for name in ("anchor", "good", "bad")]
    included = "bad" if bad else "good"
    s.graph(case, calls, [{"source": "$self", "target": included, "kind": "includes"}])
    code, payload = case.command()
    metrics = {"executed_calls": sorted(event["call"] for event in case.events())}
    expected = s.rejection("EXAMPLE.PROVIDER.FINDING", located=True, metrics=metrics) if bad else s.acceptance(executed_calls=["good"])
    if bad:
        expected["metrics"]["executed_calls"] = ["bad"]
    return [s.row("includes." + ("bad" if bad else "good"), target,
                  "显式 includes 选择真实好/坏 handler，未选择的坏 handler 不执行", "includes",
                  expected, s.observation(code, payload, metrics=metrics))]


def _invalid_graph(s, case, target, mode):
    calls = [{"id": "provider", "rule_id": "example.number_provider"}, {"id": "checker", "rule_id": "example.number_checker"}]
    relations = [s.pair()]
    if mode == "input_conflict":
        calls.append({"id": "peer", "rule_id": "example.number_provider"})
        relations.append(s.pair(provider="peer"))
        wanted = "RULE.INPUT.CONFLICT"
    elif mode == "input_unbound":
        relations = []
        wanted = "RULE.INPUT.UNBOUND"
    else:
        calls[0]["params"] = {"value": "not an integer"} if mode == "params_type" else {"unknown": 1}
        wanted = "RULE.PARAMS.SCHEMA"
    s.graph(case, calls, relations, entrypoints={"static": ["checker"]})
    code, payload = case.command()
    positions = [item for item in s.findings(payload) if item.get("code") == wanted]
    metrics = {"handler_events": len(case.events()),
               "resource_path": next((item.get("source_location", {}).get("path") for item in positions if item.get("source_location", {}).get("path")), None)}
    return [s.row("invalid." + mode, target, "图编译错误在正式命令中保留诊断、资源位置且先于 handler", "invalid_graph",
                  s.rejection(wanted, located=True, metrics={"handler_events": 0, "resource_path": str(case.graph)}),
                  s.observation(code, payload, metrics=metrics))]


def _cache_handlers(case):
    if case.target == "python":
        case.source("provider").write_text('''import json
from pathlib import Path
def check(context, inputs, params):
    call = context.facts["call"]
    value = call.params["value"]
    with Path(params["marker"]).open("a") as stream:
        stream.write(json.dumps({"handler":"provider", "value":value})+"\\n")
    return {"records":{"numbers":{"type_id":"example.numbers.v1", "value":[value]}}}
def replacement(context, inputs, params):
    return check(context, inputs, params)
''')
        case.source("checker").write_text('''import json
from pathlib import Path
def check(context, inputs, params):
    values = list(inputs["numbers"].value)
    proof = {"handler":"consumer", "values":values, "factor":params["factor"], "total":sum(values)*params["factor"],
             "single_call_visible":any(key in context.subject for key in ("owner","call_id","rule_call_id")) or "call" in context.facts}
    with Path(params["marker"]).open("a") as stream:
        stream.write(json.dumps(proof)+"\\n")
    node = next(node for node in context.facts["source_context"].nodes if node.type_key == context.subject["type_key"])
    finding = {"code":"GAPS.SOURCE.CACHE", "severity":"warning", "message":"Cached source proof remains associated with all real calls.",
               "source_location":{"path":node.path,"line":1,"column":1}, "details":{"proof":proof}}
    return {"records":{"proof":{"type_id":"example.proof.v1", "value":proof}}, "findings":[finding]}
''')
    else:
        case.source("provider").write_text('''import {appendFileSync} from "node:fs";
export function check(context, inputs, params) {
  const value=context.subject.call_spec.params.value;
  appendFileSync(params.marker,JSON.stringify({handler:"provider",value})+"\\n");
  return {records:{numbers:{type_id:"example.numbers.v1",value:[value]}}};
}
export function replacement(context,inputs,params) {return check(context,inputs,params);}
''')
        case.source("checker").write_text('''import {appendFileSync} from "node:fs";
export function check(context,inputs,params) {
  const values=inputs.numbers.value;
  const proof={handler:"consumer", values,factor:params.factor,total:values.reduce((a,b)=>a+b,0)*params.factor,
    single_call_visible:["call_spec","call_path","rule_call_id"].some(key=>key in context.subject) || "call" in context.facts};
  appendFileSync(params.marker,JSON.stringify(proof)+"\\n");
  const finding={code:"GAPS.SOURCE.CACHE",severity:"warning",message:"Cached source proof remains associated with all real calls.",
    source_location:{path:context.facts.source_files[0],line:1,column:1},details:{proof}};
  return {records:{proof:{type_id:"example.proof.v1",value:proof}},findings:[finding]};
}
''')


def _cache(s, case, target, mode):
    _cache_handlers(case)
    checker = case.read(case.rule("checker"))
    checker["scope"] = "source"
    checker["params_schema"]["factor"] = {"type": "integer"}
    checker["params_defaults"]["factor"] = 1
    case.write(case.rule("checker"), checker)
    node = case.read(case.node)
    node["contract"]["params_schema"] = {"value": {"type": "integer"}}
    node["contract"]["params_defaults"] = {"value": 3}
    node["contract"]["provides"] = []
    node["contract"]["output_semantics"] = {}
    case.write(case.node, node)
    # An audit subject may legitimately have no outputs. Both calls share one
    # real implementation and avoid a native duplicate global data-key failure.
    node_file = case.project / ("rule_graph_nodes.py" if target == "python" else "nodes/calculation.ts")
    text = node_file.read_text()
    text = text.replace('return {"result": inputs["example.input"]["value"] * 2 + 1}', 'return {}') if target == "python" else text.replace('return {result: inputs["example.input"].value * 2 + 1}', 'return {}')
    node_file.write_text(text)
    config = case.read(case.config)
    first = config["pipeline"]["nodes"][1]
    first.update(id="first", config={"value": 3})
    second = {**first, "id": "second", "config": {"value": 4 if mode == "inputs" else 3}}
    config["pipeline"]["nodes"].insert(2, second)
    config["pipeline"]["edges"] = [{"source": "start", "target": "first"}, {"source": "first", "target": "second"}, {"source": "second", "target": "end"}]
    config["pipeline"]["outputs"] = []
    case.write(case.config, config)
    calls = [{"id": "provider", "rule_id": "example.number_provider"},
             {"id": "a", "rule_id": "example.number_checker"},
             {"id": "b", "rule_id": "example.number_checker", "params": {"factor": 2 if mode == "params" else 1}}]
    s.graph(case, calls, [s.pair("a"), s.pair("b")], entrypoints={"static": ["a", "b"]})
    expected_proofs = [[3, 1, 3], [4, 1, 4]] if mode == "inputs" else [[3, 1, 3], [3, 2, 6]] if mode == "params" else [[3, 1, 3]]
    rows = []
    for session in (1, 2):
        before = len(case.events())
        code, payload = case.command()
        events = case.events()[before:]
        consumers = [event for event in events if event["handler"] == "consumer"]
        diagnostics = [item for item in s.findings(payload) if item.get("code") == "GAPS.SOURCE.CACHE"]
        associated = {str(call["node"]) for item in diagnostics for call in item.get("details", {}).get("calls", ()) if isinstance(call, dict) and "node" in call}
        associated.update("/".join(path) for item in diagnostics for path in item.get("details", {}).get("call_paths", ()))
        finding_proofs = sorted({(proof["values"][0], proof["factor"], proof["total"]) for item in diagnostics
                                if (proof := item.get("details", {}).get("proof")) is not None})
        metrics = {"providers": sum(event["handler"] == "provider" for event in events),
                   "consumers": len(consumers),
                   "proofs": sorted([event["values"][0], event["factor"], event["total"]] for event in consumers),
                   "single_call_visible": any(event["single_call_visible"] for event in consumers),
                   "associated_calls": sorted(associated), "finding_proofs": [list(proof) for proof in finding_proofs]}
        expected = s.acceptance(providers=2, consumers=len(expected_proofs), proofs=expected_proofs, single_call_visible=False,
                                associated_calls=["first", "second"], finding_proofs=expected_proofs)
        expected["codes"] = [{"code": "GAPS.SOURCE.CACHE", "severity": "warning"}]
        expected["located_codes"] = ["GAPS.SOURCE.CACHE"]
        rows.append(s.row("source_cache." + mode + ".session" + str(session), target,
            "源码 consumer 根据真实 typed inputs/params 复用，新的正式 session 重新执行", "source_cache",
            expected,
            s.observation(code, payload, metrics=metrics)))
    return rows


def _finding_source(case, kind):
    value = 123 if kind == "number" else "wrong finding" if kind == "string" else {
        "code": "GAPS.FINDING", "definition_id": "spoofed.definition", "severity": None if kind == "null" else kind,
        "message": "The handler emitted the requested finding boundary.",
        "source_location": {"path": str(case.source("provider")), "line": 5, "column": 1}}
    if case.target == "python":
        text = 'import json\nfrom pathlib import Path\ndef check(context, inputs, params):\n    with Path(params["marker"]).open("a") as stream:\n        stream.write(json.dumps({"handler":"provider"})+"\\n")\n    return {"records":{"numbers":{"type_id":"example.numbers.v1","value":[3]}},"findings": [' + repr(value) + ']}\ndef replacement(context, inputs, params):\n    return check(context,inputs,params)\n'
    else:
        text = 'import {appendFileSync} from "node:fs";\nexport function check(context,inputs,params) {\n  appendFileSync(params.marker,JSON.stringify({handler:"provider"})+"\\n");\n  return {records:{numbers:{type_id:"example.numbers.v1",value:[3]}},findings:[' + json.dumps(value) + ']};\n}\nexport function replacement(context,inputs,params) {return check(context,inputs,params);}\n'
    case.source("provider").write_text(text)
    rule = case.read(case.rule("provider"))
    case.write(case.rule("provider"), rule)
    return value


def _finding(s, case, target, kind):
    _finding_source(case, kind)
    s.graph(case, [{"id": "emit", "rule_id": "example.number_provider"},
                   {"id": "consumer", "rule_id": "example.number_checker"}], [s.pair("consumer", "emit")],
            entrypoints={"static": ["consumer"]})
    code, payload = case.command()
    events = case.events()
    states = s.javascript_states(case) if target == "javascript" else dict(s.result_states(payload))
    items = [item for item in s.findings(payload) if item.get("code") == "GAPS.FINDING"]
    definitions = sorted({item["definition_id"] for item in items if item.get("definition_id")})
    error_definitions = sorted({item["definition_id"] for item in s.findings(payload) if item.get("code") == "RULE.EXECUTION" and item.get("definition_id")})
    consumers = [event for event in events if event["handler"] == "checker"]
    actual = s.observation(code, payload, metrics={"handler_executed": any(event["handler"] == "provider" for event in events),
        "definition_ids": definitions, "error_definition_ids": error_definitions,
        "provider_state": states.get("emit"), "consumer_state": states.get("consumer"),
        "formal_consumers": len(consumers), "formal_consumer_totals": [event["total"] for event in consumers]})
    if kind in {"error", "warning", "info"}:
        expected = {"should_accept": kind != "error", "exact_codes": True,
                    "codes": [{"code": "GAPS.FINDING", "severity": kind}], "located_codes": ["GAPS.FINDING"],
                    "metrics": {"exit_code": 1 if kind == "error" else 0, "handler_executed": True,
                                "definition_ids": ["example.number_provider"], "provider_state": "completed", "consumer_state": "completed",
                                "formal_consumers": 1, "formal_consumer_totals": [3]}}
    else:
        expected = s.rejection("RULE.EXECUTION", metrics={"handler_executed": True, "error_definition_ids": ["example.number_provider"],
            "provider_state": "failed", "consumer_state": "unavailable", "formal_consumers": 0, "formal_consumer_totals": []})
        expected["codes"].append({"code": "RULE.INPUT.UNAVAILABLE", "severity": "error"})
    return [s.row("finding." + kind, target, "合法 findings 不阻断事实；非法 finding 使 provider failed 并阻断真实 requires consumer", "finding_boundary", expected, actual,
                  evidence={"command": "validate", "states": "public Javascript Target report in a separate process" if target == "javascript" else "formal validate info.rule_executions",
                            "consumer": "first formal CLI handler JSONL events, before the state probe"})]


def _source_fixture(case, topic, oversized):
    node_file = case.project / ("rule_graph_nodes.py" if case.target == "python" else "nodes/calculation.ts")
    if topic == "node":
        if oversized:
            text = node_file.read_text()
            needle = '        return {"result"' if case.target == "python" else '  return {result'
            comments = ('        # actual source line\n' if case.target == "python" else '  // actual source line\n') * 501
            node_file.write_text(text.replace(needle, comments + needle))
        return
    count = 6 if topic == "dependency_chain" and oversized else 2 if topic == "dependency_chain" else 1
    if case.target == "javascript":
        # The original example shares a file between boundary and calculate.
        # Once only calculate owns BaseLib dependencies, split the genuine
        # implementations so that ownership compatibility cannot mask metrics.
        (case.project / "nodes/boundary.ts").write_text("export function boundary(inputs,params) {return {};}\n")
        boundary = case.project / "bundle/nodes/boundary.jsonc"
        descriptor = case.read(boundary)
        descriptor["implementations"][0]["source"]["ref"] = "nodes/boundary.ts"
        case.write(boundary, descriptor)
    library = case.project / "base_lib"
    library.mkdir()
    (library / "__init__.py").write_text("") if case.target == "python" else None
    bundle_path = case.project / "bundles/rule-graph.jsonc"
    bundle = case.read(bundle_path)
    bundle["resources"]["base_lib"] = []
    for index in range(count):
        following = index + 1 < count
        if case.target == "python":
            text = (f'from base_lib.step{index+1} import step as next_step\n' if following else '') + 'def step(value):\n    return ' + ('next_step(value)' if following else 'value') + '\n'
            file = library / f"step{index}.py"
        else:
            text = (f'import {{step as nextStep}} from "./step{index+1}.ts";\n' if following else '') + 'export function step(value: number): number {return ' + ('nextStep(value)' if following else 'value') + ';}\n'
            file = library / f"step{index}.ts"
        if topic == "base_lib" and oversized:
            text += ('# measured file line\n' if case.target == "python" else '// measured file line\n') * (501 - len(text.splitlines()))
        file.write_text(text)
        manifest = case.project / "bundle/base_libs" / f"step{index}.jsonc"
        case.write(manifest, {"kind": "base_lib", "id": f"gaps.step{index}", "display_name": "Step", "description": "Actual pure helper source.",
                             "dependencies": [f"gaps.step{index+1}"] if following else [], "external_packages": [],
                             "implementations": [{"language": "python" if case.target == "python" else "typescript", "targets": ["python"] if case.target == "python" else ["node", "browser"],
                                 "source": {"kind": "file", "ref": str(file.relative_to(case.project))}}]})
        bundle["resources"]["base_lib"].append("../bundle/base_libs/" + manifest.name)
    case.write(bundle_path, bundle)
    text = node_file.read_text()
    if case.target == "python":
        text = 'from base_lib.step0 import step\n' + text.replace('inputs["example.input"]["value"] * 2 + 1', 'step(inputs["example.input"]["value"]) * 2 + 1')
    else:
        text = 'import {step} from "../base_lib/step0.ts";\n' + text.replace('inputs["example.input"].value * 2 + 1', 'step(inputs["example.input"].value) * 2 + 1')
    node_file.write_text(text)
    node = case.read(case.node)
    node["base_libs"] = ["gaps.step0"]
    case.write(case.node, node)


def _leaf(s, case, target, topic, oversized):
    _source_fixture(case, topic, oversized)
    wanted = {"node": "NODE.PURITY.SOURCE_TOO_LARGE", "base_lib": "BASE_LIB.SOURCE.MAX_LINES", "dependency_chain": "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"}[topic]
    control = s.builtin_control(case)
    control_codes = control["codes"]
    control_expected = [{"code": wanted, "severity": "error"}] if oversized else []
    key = "leaf." + topic + (".oversized" if oversized else ".normal")
    rows = [s.row(key + ".control", target, "既有适配器从真实源码提取同一主题的正常/超限事实", "implementation_leaf_control",
                  {"should_accept": not oversized, "exact_codes": True, "codes": control_expected,
                   "metrics": {"exit_code": 1 if oversized else 0}}, control)]
    s.graph(case, [{"id": "metrics", "rule_id": "vibeflow.maintainability"},
                   {"id": "leaf", "rule_id": "vibeflow.implementation." + topic}])
    code, payload = case.command()
    leaf_codes = sorted({(item.get("code"), item.get("severity", "error")) for item in s.findings(payload)
                         if item.get("definition_id") == "vibeflow.implementation." + topic})
    actual = s.observation(code, payload, metrics={"control_codes": control_codes, "control_status": control["status"],
                                                  "leaf_codes": [{"code": code, "severity": severity} for code, severity in leaf_codes]})
    expected = s.rejection(wanted) if oversized else s.acceptance()
    expected["exact_codes"] = True
    expected["metrics"].update(control_codes=control_expected, leaf_codes=control_expected)
    rows.append(s.row(key, target, "公开 implementation leaf 在正式 Node Rule 选集中消费真实实现闭包", "implementation_leaf",
                      expected, actual, supported_scope={"subject": "selected Node implementation", "facts": "Target source and registered BaseLib closure", "topic": topic},
                      notes="Control proves the source branch is reachable. The desired leaf result cannot be satisfied by missing metrics/handler errors."))
    return rows


def _core_findings(s):
    from vibeflow.core.findings import HealthFinding
    from vibeflow.core.rules import RuleCall, RuleContext, RuleDescriptor, RuleRecord, RuleRelation, RuleResult, RulesetDescriptor, compile_ruleset, execute_rule_plan
    rule = RuleDescriptor("gaps.core_finding", outputs={"numbers": "gaps.numbers.v1"})
    consumer = RuleDescriptor("gaps.consumer", inputs={"numbers": "gaps.numbers.v1"}, outputs={"proof": "gaps.proof.v1"})
    plan = compile_ruleset(RulesetDescriptor("gaps.core", (RuleCall("emit", rule.id), RuleCall("consumer", consumer.id)),
        (RuleRelation("consumer", "emit", "requires", {"numbers": "numbers"}),), entrypoints={"static": ("consumer",)}), rules={rule.id: rule, consumer.id: consumer})
    rows = []
    for kind in ("info", "warning", "error", "fatal", "null", "number", "string"):
        item = 123 if kind == "number" else "wrong" if kind == "string" else {
            "code": "GAPS.FINDING", "severity": None if kind == "null" else kind,
            "definition_id": "spoofed.definition", "message": "Core finding boundary control."}
        modes = []
        for typed in (False, True):
            seen = []
            def handler(context, inputs, params):
                record = RuleRecord("gaps.numbers.v1", [3])
                if not typed:
                    return {"records": {"numbers": record}, "findings": [item]}
                finding = item if kind in {"number", "string"} else HealthFinding(rule_id="GAPS.FINDING", severity=item["severity"],
                    message=item["message"], definition_id="spoofed.definition")
                return RuleResult(records={"numbers": record}, findings=(finding,))
            def consume(context, inputs, params):
                total = sum(inputs["numbers"].value)
                seen.append(total)
                return RuleResult({"proof": RuleRecord("gaps.proof.v1", {"total": total})})
            result = execute_rule_plan(plan, RuleContext(), handlers={rule.id: handler, consumer.id: consume})
            modes.append((result, list(seen)))
        result = modes[0][0]
        payload = {"raw": result.to_dict(), "typed": modes[1][0].to_dict(), "status": result.status}
        definitions = sorted({value.get("definition_id") for value in s.findings(payload) if value.get("code") == "GAPS.FINDING"})
        error_definitions = sorted({value["definition_id"] for value in s.findings(payload) if value.get("code") == "RULE.EXECUTION" and value.get("definition_id")})
        actual = s.observation(1 if result.status in {"FAIL", "ERROR"} else 0, payload, metrics={"definition_ids": definitions,
            "error_definition_ids": error_definitions, **{name: {"provider_state": result.results["emit"].state,
                "consumer_state": result.results["consumer"].state, "consumer_totals": totals}
                for name, (result, totals) in zip(("raw", "typed"), modes)}})
        states = {name: {"provider_state": "completed" if kind in {"info", "warning", "error"} else "failed",
                         "consumer_state": "completed" if kind in {"info", "warning", "error"} else "unavailable",
                         "consumer_totals": [3] if kind in {"info", "warning", "error"} else []} for name in ("raw", "typed")}
        if kind in {"info", "warning", "error"}:
            expected = {"should_accept": kind != "error", "exact_codes": True, "codes": [{"code": "GAPS.FINDING", "severity": kind}],
                        "metrics": {"exit_code": 1 if kind == "error" else 0, "definition_ids": [rule.id], **states}}
        else:
            expected = s.rejection("RULE.EXECUTION", metrics={"error_definition_ids": [rule.id], **states})
            expected["codes"].append({"code": "RULE.INPUT.UNAVAILABLE", "severity": "error"})
        rows.append(s.row("finding." + kind, "core", "Core raw/typed RuleResult 的 finding 与 requires 事实可用性边界", "finding_boundary", expected, actual))
    return rows


def run_cases(work_root: Path, variant="current", toolchain_root: Path | None = None):
    if variant != "current":
        raise ValueError("The second Rule gap suite validates the current public mechanism only")
    s = _support()
    rows = _core_findings(s)
    factories = [("replacement.defaults", lambda case, target: _replacement(s, case, target, False)),
                 ("replacement.override", lambda case, target: _replacement(s, case, target, True))]
    factories += [("includes." + name, lambda case, target, bad=bad: _includes(s, case, target, bad)) for name, bad in (("good", False), ("bad", True))]
    factories += [("invalid." + name, lambda case, target, name=name: _invalid_graph(s, case, target, name)) for name in ("input_conflict", "input_unbound", "params_type", "params_unknown")]
    factories += [("source_cache." + name, lambda case, target, name=name: _cache(s, case, target, name)) for name in ("equal", "inputs", "params")]
    factories += [("finding." + name, lambda case, target, name=name: _finding(s, case, target, name)) for name in ("info", "warning", "error", "fatal", "null", "number", "string")]
    factories += [("leaf." + topic + (".oversized" if oversized else ".normal"), lambda case, target, topic=topic, oversized=oversized: _leaf(s, case, target, topic, oversized))
                  for topic in ("node", "base_lib", "dependency_chain") for oversized in (False, True)]
    for target in ("python", "javascript"):
        for name, factory in factories:
            case = s.create(work_root, target, name, toolchain_root)
            try:
                rows.extend(factory(case, target))
            except Exception as exc:
                (case.root / "fixture-exception.log").write_text(traceback.format_exc())
                rows.append(s.row(name, target, "Case could not produce the intended formal observation", "fixture",
                                  s.acceptance(), s.measured_error(exc)))
    return rows
