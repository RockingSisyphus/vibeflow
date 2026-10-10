"""Fresh-process SDK/CLI cases for cache and diagnostic isolation."""

import json
from pathlib import Path
from types import SimpleNamespace

from tests.fixtures.python.review_performance.fixtures import node_call, write_project
from tests.fixtures.python.review_performance.run_all import run_cli


PREAMBLE = '''from pathlib import Path
from vibeflow.targets.python.sdk import Plugin, node, rule, ruleset, SourceLocator
from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleRecord, RuleResult

def finding(context, code, message, severity="warning"):
    return HealthFinding(rule_id=code, severity=severity, object_type="node",
        object_id=context.subject.get("type_key", context.subject.get("owner", "pipeline")), message=message,
        source_location={"path": __file__, "line": 8, "column": 1})

@node(type_key="case.start", flow_kind="terminal", contract={}, rulesets=[])
class Start:
    def run_pure(self, inputs, params):
        return {}

@node(type_key="case.end", flow_kind="terminal", contract={}, rulesets=[])
class End:
    def run_pure(self, inputs, params):
        return {}
'''


def _project(root, body, resources, selections, *, calls=1, config=None):
    write_project(root, nodes=0, libraries=0)
    leaf = (f'@node(type_key="case.step", contract={{}}, rulesets={selections!r})\n'
            'class Step:\n'
            '    def run_pure(self, inputs, params):\n'
            '        return {}\n')
    source = PREAMBLE + body + "\n" + leaf
    source += (f'\nplugin = Plugin(id="case.resources", resources=[Start, End, Step, {resources}],\n'
               '    config_defaults={"mode": 1}, declaration_rulesets=[])\n')
    (root / "code_plugin.py").write_text(source)
    steps = [node_call(f"step{index}", "case.step") for index in range(calls)]
    _workflow(root, steps, config=config)


def _workflow(root, steps, *, config=None, filename="workflow.jsonc"):
    nodes = [node_call("start", "case.start"), *steps, node_call("end", "case.end")]
    data = {"plugins": [{"source": {"kind": "file", "ref": "code_plugin.py"},
                         "config": config or {}}], "rulesets": [],
            "pipeline": {"nodes": nodes,
                         "edges": [[left["id"], right["id"]]
                                   for left, right in zip(nodes, nodes[1:])]}}
    (root / filename).write_text(json.dumps(data, indent=2) + "\n")


def _observe(root, args, *, name="observation", config="workflow.jsonc"):
    result = run_cli(root, ["validate", "--workspace", str(root / "vibeflow_config.jsonc"),
                           "--config", str(root / config), "--json"], args, name)
    output = (root / (name + ".stdout.txt")).read_text()
    payload = json.loads(output)
    result["diagnostics"] = [item for key in ("errors", "warnings", "skipped")
                             for item in payload.get(key, [])]
    result["report_path"] = str(root / (name + ".json"))
    return result


def _count(observation, code):
    return sum(int(item.get("details", {}).get("occurrences", 1))
               for item in observation["diagnostics"]
               if item.get("rule_id", item.get("code")) == code)


def _executions(observation, rule_id):
    return sum(item["executions"] for item in observation["rules"] if item["id"] == rule_id)


def _expected(observation, *, exit_code, diagnostics, executions):
    observation["expected"] = {"exit_code": exit_code, "diagnostics": diagnostics,
                               "rule_executions": executions}
    failures = []
    if observation["error"] or observation["exit_code"] != exit_code:
        failures.append(f"CLI returned {observation['exit_code']}, expected {exit_code}: {observation['error']}")
    for code, count in diagnostics.items():
        actual = _count(observation, code)
        if actual != count:
            failures.append(f"{code}: {actual} diagnostics, expected {count}")
    for rule_id, count in executions.items():
        actual = _executions(observation, rule_id)
        if actual != count:
            failures.append(f"{rule_id}: {actual} executions, expected {count}")
    for item in observation["diagnostics"]:
        if item["severity"] == "error" and item.get("rule_id", item.get("code")) not in diagnostics:
            failures.append(f"unrelated error: {item.get('rule_id', item.get('code'))}")
        if item.get("rule_id", item.get("code")) in diagnostics:
            code = item.get("rule_id", item.get("code"))
            expected_severity = "error" if code in {"CASE.PROVIDER", "RULE.INPUT.UNAVAILABLE",
                                                    "NODE.EFFECT.CALL_FORBIDDEN"} else "warning"
            if item["severity"] != expected_severity:
                failures.append(f"{code}: severity {item['severity']}, expected {expected_severity}")
            location = item.get("source_location", {})
            if item.get("rule_id") == "RULE.INPUT.UNAVAILABLE":
                # This engine diagnostic has no syntax site; the adapter supplies
                # the subject source rather than inventing a declaration line.
                valid_location = bool(item.get("source_path"))
            else:
                valid_location = bool(location.get("path")) and isinstance(location.get("line"), int)
            if not valid_location:
                failures.append("target diagnostic lost its source location")
    return failures


def _params_case(root, args):
    body = '''
@rule(id="case.equal", scope="source", params_schema={"limit":{"type":"integer"}}, params_defaults={"limit":0})
def check_equal(context, inputs, params):
    return RuleResult(findings=(finding(context, "CASE.EQUAL", "same warning"),))
checks = ruleset(id="case.params", calls=[
    {"id":"low", "rule_id":"case.equal", "params":{"limit":1}},
    {"id":"high", "rule_id":"case.equal", "params":{"limit":2}}],
    entrypoints={"static":["low", "high"]})
'''
    _project(root, body, "check_equal, checks", ["case.params"])
    observation = _observe(root, args)
    return observation, _expected(observation, exit_code=0,
        diagnostics={"CASE.EQUAL": 2}, executions={"case.equal": 2})


def _calls_case(root, args):
    body = '''
@rule(id="case.equal", scope="call")
def check_equal(context, inputs, params):
    return RuleResult(findings=(finding(context, "CASE.EQUAL", "same warning"),))
left = ruleset(id="case.left", calls=[{"id":"check", "rule_id":"case.equal"}], entrypoints={"static":["check"]})
right = ruleset(id="case.right", calls=[{"id":"check", "rule_id":"case.equal"}], entrypoints={"static":["check"]})
'''
    _project(root, body, "check_equal, left, right", ["case.left", "case.right"], calls=2)
    observation = _observe(root, args)
    return observation, _expected(observation, exit_code=0,
        diagnostics={"CASE.EQUAL": 4}, executions={"case.equal": 4})


def _records_case(root, args, state):
    body = f'''
@rule(id="case.provider", outputs={{"data":"case.data.v1"}})
def provide(context, inputs, params):
    return RuleResult(state={state!r}, records={{"data":RuleRecord("case.data.v1", {{"value":7}})}},
        findings=(finding(context, "CASE.PROVIDER", "provider health error", "error"),))
@rule(id="case.consumer", inputs={{"data":"case.data.v1"}})
def consume(context, inputs, params):
    value = inputs["data"].value["value"]
    Path(__file__).with_name("consumer.marker").write_text(str(value))
    return RuleResult(findings=(finding(context, "CASE.CONSUMED", f"consumed {{value}}"),))
checks = ruleset(id="case.records", calls=[
    {{"id":"provide", "rule_id":"case.provider"}}, {{"id":"consume", "rule_id":"case.consumer"}}],
    relations=[{{"source":"consume", "target":"provide", "kind":"requires", "bindings":{{"data":"data"}}}}],
    entrypoints={{"static":["consume"]}})
'''
    _project(root, body, "provide, consume, checks", ["case.records"])
    observation = _observe(root, args)
    available = state == "completed"
    diagnostics = {"CASE.PROVIDER": 1, "CASE.CONSUMED": int(available)}
    if not available:
        diagnostics["RULE.INPUT.UNAVAILABLE"] = 1
    failures = _expected(observation, exit_code=1, diagnostics=diagnostics,
        executions={"case.provider": 1, "case.consumer": int(available)})
    marker = root / "consumer.marker"
    observation["expected"]["consumer_marker"] = "7" if available else None
    if marker.exists() != available or (available and marker.read_text() != "7"):
        failures.append("consumer did not preserve provider state/records")
    return observation, failures


def _changing_records_case(root, args):
    body = '''
@rule(id="case.changing_provider", scope="call", outputs={"data":"case.data.v1"})
def provide(context, inputs, params):
    value = context.require("call").params["record"]
    return RuleResult(records={"data":RuleRecord("case.data.v1", {"value":value})})
@rule(id="case.source_consumer", scope="source", inputs={"data":"case.data.v1"})
def consume(context, inputs, params):
    value = inputs["data"].value["value"]
    with Path(__file__).with_name("consumer.marker").open("a") as stream:
        stream.write(str(value) + "\\n")
    return RuleResult(findings=(finding(context, "CASE.CHANGING_RECORD", f"consumed {value}"),))
checks = ruleset(id="case.changing_records", calls=[
    {"id":"provide", "rule_id":"case.changing_provider"}, {"id":"consume", "rule_id":"case.source_consumer"}],
    relations=[{"source":"consume", "target":"provide", "kind":"requires", "bindings":{"data":"data"}}],
    entrypoints={"static":["consume"]})
'''
    _project(root, body, "provide, consume, checks", ["case.changing_records"], calls=3)
    source = root / "code_plugin.py"
    source.write_text(source.read_text().replace('type_key="case.step", contract={}',
        'type_key="case.step", contract={"params_schema":{"record":{"type":"integer"}},"params_defaults":{"record":0}}'))
    steps = [{**node_call(f"step{index}","case.step"),"config":{"record":value}}
             for index,value in enumerate((1,2,2))]
    _workflow(root, steps)
    observation = _observe(root, args)
    failures = _expected(observation, exit_code=0,
        diagnostics={"CASE.CHANGING_RECORD":2},
        executions={"case.changing_provider":3,"case.source_consumer":2})
    marker = root / "consumer.marker"
    observation["expected"]["consumer_marker"] = ["1","2"]
    if not marker.exists() or marker.read_text().splitlines() != ["1","2"]:
        failures.append("source consumer reused changed records or reran identical records")
    diagnostics = [item for item in observation["diagnostics"] if item.get("rule_id") == "CASE.CHANGING_RECORD"]
    if any({call["node"] for call in item.get("details",{}).get("calls",())} != ({"step0"} if item["message"] == "consumed 1" else {"step1","step2"})
           for item in diagnostics):
        failures.append("source diagnostic lost repeated-call associations")
    return observation, failures


def _native_records_case(root, args, variant):
    body = f'''
from dataclasses import make_dataclass
First = make_dataclass("Payload", [("value",int)], frozen=True)
Second = make_dataclass("Payload", [("value",int)], frozen=True)
@rule(id="case.native_provider", scope="call", outputs={{"data":"case.data.v1"}})
def provide(context, inputs, params):
    kind = context.require("call").params["record_kind"]
    if {variant!r} == "dataclass":
        value = First(7) if kind == "first" else Second(7) if kind == "second" else {{"value":7}}
    else:
        value = [7] if kind == "tuple" else frozenset({{7}})
    return RuleResult(records={{"data":RuleRecord("case.data.v1",value)}})
@rule(id="case.native_consumer", scope="source", inputs={{"data":"case.data.v1"}})
def consume(context, inputs, params):
    value = inputs["data"].value
    label = "first" if type(value) is First else "second" if type(value) is Second else "tuple" if type(value) is tuple else "frozenset" if type(value) is frozenset else "mapping"
    with Path(__file__).with_name("consumer.marker").open("a") as stream:
        stream.write(label + "\\n")
    return RuleResult(findings=(finding(context,"CASE.NATIVE_RECORD","same warning"),))
checks = ruleset(id="case.native_records", calls=[
    {{"id":"provide","rule_id":"case.native_provider"}},{{"id":"consume","rule_id":"case.native_consumer"}}],
    relations=[{{"source":"consume","target":"provide","kind":"requires","bindings":{{"data":"data"}}}}],
    entrypoints={{"static":["consume"]}})
'''
    kinds = ("first","second","mapping") if variant == "dataclass" else ("tuple","frozenset")
    _project(root,body,"provide, consume, checks",["case.native_records"],calls=len(kinds))
    source = root / "code_plugin.py"
    source.write_text(source.read_text().replace('type_key="case.step", contract={}',
        'type_key="case.step", contract={"params_schema":{"record_kind":{"type":"string"}},"params_defaults":{"record_kind":"mapping"}}'))
    steps = [{**node_call(f"step{index}","case.step"),"config":{"record_kind":kind}}
             for index,kind in enumerate(kinds)]
    _workflow(root,steps)
    observation = _observe(root,args)
    failures = _expected(observation,exit_code=0,diagnostics={"CASE.NATIVE_RECORD":len(kinds)},
        executions={"case.native_provider":len(kinds),"case.native_consumer":len(kinds)})
    marker = root / "consumer.marker"
    observation["expected"]["consumer_marker"] = list(kinds)
    if not marker.exists() or marker.read_text().splitlines() != list(kinds):
        failures.append("source consumer lost the actual native input record type")
    diagnostics = [item for item in observation["diagnostics"] if item.get("rule_id") == "CASE.NATIVE_RECORD"]
    actual_calls = [{call["node"] for call in item.get("details",{}).get("calls",())} for item in diagnostics]
    if sorted(sorted(calls) for calls in actual_calls) != [[f"step{index}"] for index in range(len(kinds))]:
        failures.append("native record diagnostic lost its call associations")
    return observation,failures


def _permissions_case(root, args):
    write_project(root, nodes=0, libraries=0)
    (root / "shared.py").write_text('class Shared:\n    def run_pure(self, inputs, params):\n        print("shared output")\n        return {}\n')
    body = '''
allowed = ruleset(id="case.allowed", calls=[{"id":"effect", "rule_id":"vibeflow.no_side_effects", "params":{"effect_scope":"terminal"}}], entrypoints={"static":["effect"]})
restricted = ruleset(id="case.restricted", calls=[{"id":"effect", "rule_id":"vibeflow.no_side_effects", "params":{"effect_scope":"none"}}], entrypoints={"static":["effect"]})
shared = SourceLocator("file", str(Path(__file__).with_name("shared.py")), "Shared")
wide = node(type_key="case.wide", contract={}, source=shared, rulesets=["case.allowed"])
narrow = node(type_key="case.narrow", contract={}, source=shared, rulesets=["case.restricted"])
plugin = Plugin(id="case.resources", resources=[Start, End, wide, narrow, allowed, restricted], declaration_rulesets=[])
'''
    (root / "code_plugin.py").write_text(PREAMBLE + body)
    _workflow(root, [node_call("wide", "case.wide"), node_call("narrow", "case.narrow")])
    observation = _observe(root, args)
    target = [item for item in observation["diagnostics"] if "print" in item.get("message", "")]
    failures = _expected(observation, exit_code=1, diagnostics={"NODE.EFFECT.CALL_FORBIDDEN": 1},
                         executions={"vibeflow.no_side_effects": 2})
    observation["expected"]["forbidden_node"] = "case.narrow"
    if len(target) != 1 or target[0].get("object_id") != "case.narrow":
        failures.append("shared implementation inherited the other Node's wider permissions")
    return observation, failures


def _configuration_case(root, args):
    body = '''
@rule(id="case.config", scope="source")
def check_config(context, inputs, params):
    value = context.facts["plugins"]["case.resources"]["mode"]
    return RuleResult(findings=(finding(context, "CASE.CONFIG", f"mode {value}"),))
checks = ruleset(id="case.config", workflow_default=True, calls=[{"id":"check", "rule_id":"case.config"}], entrypoints={"static":["check"]})
'''
    _project(root, body, "check_config, checks", [])
    _workflow(root, [node_call("step0", "case.step")], config={"mode": 2}, filename="second.jsonc")
    for filename in ("workflow.jsonc", "second.jsonc"):
        path = root / filename
        data = json.loads(path.read_text())
        data["rulesets"] = ["case.config"]
        path.write_text(json.dumps(data))
    observations, failures = [], []
    for index, config in enumerate(("workflow.jsonc", "second.jsonc"), 1):
        observation = _observe(root, args, name=f"configuration{index}", config=config)
        failures += _expected(observation, exit_code=0,
            diagnostics={"CASE.CONFIG": 1}, executions={"case.config": 1})
        target = [item for item in observation["diagnostics"] if item.get("rule_id") == "CASE.CONFIG"]
        if len(target) != 1 or target[0]["message"] != f"mode {index}":
            failures.append(f"workflow {index} used another workflow's plugin config")
        observations.append(observation)
    return {"observations": observations,
            "seconds": sum(item["seconds"] for item in observations)}, failures


def observe_cases(work: Path, kernel: Path, renderer: Path | None, *, installed=False):
    """Return machine cases; every observation uses a new formal CLI process."""
    args = SimpleNamespace(kernel=kernel, renderer=renderer, installed=installed)
    cases = [("cache-params-diagnostics", _params_case),
             ("cache-ruleset-local-call-diagnostics", _calls_case),
             ("cache-error-records", lambda root, args: _records_case(root, args, "completed")),
             ("cache-failed-records", lambda root, args: _records_case(root, args, "failed")),
             ("cache-unavailable-records", lambda root, args: _records_case(root, args, "unavailable")),
             ("cache-changing-input-records", _changing_records_case),
             ("cache-native-dataclass-records", lambda root,args: _native_records_case(root,args,"dataclass")),
             ("cache-native-set-records", lambda root,args: _native_records_case(root,args,"set")),
             ("cache-shared-symbol-permissions", _permissions_case),
             ("cache-workflow-plugin-config", _configuration_case)]
    results = []
    for identifier, observe in cases:
        root = work / identifier
        try:
            observation, failures = observe(root, args)
            results.append({"id": identifier, "command": "validate", "matched": not failures,
                            "failures": failures, "artifact_root": str(root), **observation})
        except Exception as error:
            results.append({"id": identifier, "command": "validate", "matched": False,
                            "failures": [repr(error)], "artifact_root": str(root),
                            "seconds": 0,
                            "observation_error": repr(error)})
    return results
