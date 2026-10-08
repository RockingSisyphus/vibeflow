"""Formal CLI regressions for A02/A04/A06/A07; expected results describe the fix."""

from pathlib import Path

from sandbox.adaptation_regressions.common import row, run_cli, run_probe
from sandbox.adaptation_regressions.python_runtime_fixtures import compiler_project, policy_project, scope_project
from sandbox.python.review_performance.fixtures import write_project

OBSERVER = Path(__file__).with_name("python_runtime_observer.py")


def arguments(root, command, *, workspace=True, config=None):
    result = [command, "--config", str(config or root / "workflow.jsonc")]
    if workspace:
        result += ["--workspace", str(root / "vibeflow_config.jsonc")]
    if command == "validate":
        result += ["--json"]
    if command == "run":
        result += ["--input", str(root / "input.json"), "--run-root", str(root / "runs"), "--run-id", "observed"]
    return result


def health(raw):
    payload = raw.get("payload") or {}
    return payload.get("health", payload.get("validation", payload))


def findings(raw, code):
    return [item for item in health(raw).get("errors", ()) if item.get("rule_id") == code]


def observed(raw, code=None):
    report = health(raw)
    result = {"exit_code":raw["exit_code"], "status":report.get("status"),
              "error_codes":[item.get("rule_id") for item in report.get("errors", ())],
              "raw":raw}
    if code:
        result["target"] = [{key:item.get(key) for key in ("rule_id","severity","object_id","source_location","message")}
                            for item in findings(raw, code)]
    return result


def counted(root, argv, kernel):
    process = run_probe(root, OBSERVER, kernel, args=["count", "--", *argv], name="counted")
    data = process.get("payload") or {"exit_code":process["exit_code"], "error":process.get("stderr")}
    return {**data, "process":process}


def compiler_cases(work, kernel):
    rows = []
    for mode in ("success", "before-failure", "after-failure"):
        root = compiler_project(work / ("compiler-" + mode), mode)
        raw = run_cli(root, arguments(root, "validate"), kernel)
        actual = observed(raw, "GRAPH.COMPILE")
        actual["events"] = (root / "hooks.jsonl").read_text().splitlines() if (root / "hooks.jsonl").exists() else []
        expected = {"exit_code":0, "status":"PASS", "error_codes":[],
                    "events":["created","before:False","after:False","dispose","node-static","workflow:True"]}
        if mode != "success":
            expected = {"exit_code":1, "status":"FAIL", "error_codes":["GRAPH.COMPILE"],
                        "events":["created","before:False", *( ["after:False"] if mode == "after-failure" else []), "dispose"]}
            target = actual["target"]
            actual["target_exact"] = len(target) == 1 and target[0]["severity"] == "error" and (
                "AUDIT_BEFORE_FAILURE" if mode == "before-failure" else "AUDIT_AFTER_FAILURE") in target[0]["message"]
            expected["target_exact"] = True
        rows.append(row("A02.python.compiler." + mode, "A02", "One compiler stage retains its artifact and releases its instance", expected, actual, project=root))
    root = compiler_project(work / "compiler-checked-run", runnable=True)
    raw = counted(root, arguments(root, "run"), kernel)
    actual = observed(raw)
    actual["events"] = (root / "hooks.jsonl").read_text().splitlines()
    actual["runtime"] = raw.get("runtime")
    expected = {"exit_code":0,"status":"PASS","error_codes":[],
        "events":["created","before:False","after:False","dispose","node-static","workflow:True","business:7"],
        "runtime":[{"providers":{"audit.compiler":"kept","value":"leaf"},"result":7}]}
    rows.append(row("A02.python.compiler.checked-run", "A02", "Actual Runtime retains the checked compiler artifact and computes its number", expected, actual, project=root))
    return rows


def scope_cases(work, kernel):
    rows = []
    for unused, refuse, command in ((True,False,"validate"),(True,False,"run"),
                                   (False,False,"run"),(True,True,"validate"),(True,True,"run")):
        name = ("unused" if unused else "control") + ("-refused" if refuse else "") + "-" + command
        root = scope_project(work / name, unused=unused, refuse=refuse)
        raw = run_cli(root, arguments(root, command), kernel)
        actual = observed(raw, "AUDIT.IMPORT.REFUSED")
        actual.update(a_imported=(root / "a.imported").exists(), a_ran=(root / "a.ran").exists(),
                      b_imported=(root / "b.imported").exists())
        expected = {"exit_code":1 if refuse else 0, "status":"FAIL" if refuse else "PASS",
                    "error_codes":["AUDIT.IMPORT.REFUSED"] if refuse else [],
                    "a_imported":command == "run" and not refuse, "a_ran":command == "run" and not refuse,
                    "b_imported":False}
        if refuse:
            target = actual["target"]
            actual["target_exact"] = len(target) == 1 and target[0]["severity"] == "error" and target[0]["source_location"] == {"path":str(root / "a.py"),"line":1}
            expected["target_exact"] = True
        rows.append(row("A04.python.scope." + name, "A04", "Supplementary unused implementation cannot replace actual workflow scope", expected, actual, project=root))
    root = scope_project(work / "pure-source-query")
    raw = run_probe(root, OBSERVER, kernel, args=["source-query"], name="source-query")
    actual = {**(raw.get("payload") or {}), "raw":raw}
    expected = {"query":{"snapshot_unchanged":True,"session_unchanged":True,"states_unchanged":True,"query_types":["audit.b"]},
                "compile":{"snapshot_unchanged":True,"session_unchanged":True,"states_unchanged":True},
                "actual_calls":[["pipeline","a","audit.a"]], "binding_error":None,
                "a_imported":True,"b_imported":False,"business_ran":False,"a_state_after_binding":"loaded"}
    rows.append(row("A04.python.scope.pure-query", "A04", "Query and fact compilation preserve the published check scope", expected, actual, project=root))
    return rows


def inspect_config_cases(work, kernel):
    rows = []
    for workspace in (True, False):
        for violation in (False, True):
            name = ("workspace" if workspace else "project") + ("-invalid" if violation else "-valid")
            root = work / name
            write_project(root, nodes=8, libraries=1, violation=violation)
            data = counted(root, arguments(root, "inspect-config", workspace=workspace), kernel)
            actual = observed(data, "BASE_LIB.SIDE_EFFECT_CALL")
            actual["counters"] = {key:data.get("calls",{}).get(key,0) for key in ("environment","prepare","health","compile")}
            actual["call_checks"] = sum(item["executions"] for item in data.get("rules",()) if item["id"] == "perf.call")
            parsed = {name:count for name,count in data.get("parsing_counts",{}).items()
                      if str(root) in name and name.endswith(".py")}
            actual["parsing_counts"] = parsed
            actual["all_source_parsed_once"] = bool(parsed) and all(count == 1 for count in parsed.values())
            expected = {"exit_code":1 if violation else 0, "status":"FAIL" if violation else "PASS"}
            if violation:
                target = [item for item in actual["target"] if item["object_id"] == "perf.library.0"]
                actual["target_exact"] = len(target) == 1 and target[0]["severity"] == "error" and target[0]["source_location"] == {"path":str(root / "base_lib/lib0.py"),"line":4,"column":5}
                actual["no_unrelated_errors"] = all(code in {"NODE.EFFECT.CALL_FORBIDDEN", "BASE_LIB.SIDE_EFFECT_CALL", "NODE.BASE_LIB.INDIRECT_VIOLATION"} for code in actual["error_codes"])
                expected["target_exact"] = True
                expected["no_unrelated_errors"] = True
            else:
                expected["status"] = "CONCERNS"
                expected.update(counters={"environment":1,"prepare":1,"health":1},call_checks=8,all_source_parsed_once=True,error_codes=[])
                actual["effective_edges"] = data.get("payload",{}).get("config",{}).get("effective_edges")
                expected["effective_edges"] = [{"from":left,"to":right,"when":""} for left,right in zip(
                    ["start", *(f"step{i}" for i in range(8))], [*(f"step{i}" for i in range(8)), "end"])]
            rows.append(row("A06.python.inspect-config." + name, "A06", "Inspect config consumes one checked result", expected, actual, project=root))
    return rows


def inspect_node_cases(work, kernel):
    rows = []
    variants = {"inline-denied":({"inline":10},True), "inline-allowed":({"inline":500},False),
        "discovered-denied":({"discovered":10},True),
        "explicit-wins":({"discovered":10,"explicit":40},False),
        "inline-wins":({"discovered":50,"explicit":40,"inline":10},True),
        "nested-discovery":({"discovered":10,"nested":True},True),
        "rule-params-win":({"inline":10,"override":True},False),
        "unrelated-node":({"inline":500,"unrelated":True},False)}
    for name, (options, denied) in variants.items():
        root, config = policy_project(work / name, **options)
        for command in ("validate", "inspect-node"):
            argv = arguments(root, command, workspace=False, config=config)
            if command == "inspect-node":
                argv += ["--type","audit.leaf"]
            if "explicit" in options:
                argv += ["--policy",str(root / "explicit.jsonc")]
            raw = run_cli(root, argv, kernel, name=command)
            actual = observed(raw, "NODE.PURITY.SOURCE_TOO_LARGE")
            expected = {"exit_code":1 if denied else 0,"status":"FAIL" if denied else "PASS",
                        "error_codes":["NODE.PURITY.SOURCE_TOO_LARGE"] if denied else []}
            if denied:
                target = actual["target"]
                actual["target_exact"] = len(target) == 1 and target[0]["severity"] == "error" and target[0]["source_location"] == {"path":str(root / "leaf.py"),"line":1,"column":1} and "28 lines > 10" in target[0]["message"]
                expected["target_exact"] = True
            rows.append(row("A07.python.policy." + name + "." + command, "A07", "Inspect Node preserves workflow policy precedence and its own scope", expected, actual, project=root))
    return rows


def observe(work: Path, kernel: Path, toolchain: Path | None = None, renderer: Path | None = None) -> list[dict]:
    work.mkdir(parents=True, exist_ok=True)
    return [*compiler_cases(work / "compiler", kernel), *scope_cases(work / "scope", kernel),
            *inspect_config_cases(work / "inspect-config", kernel), *inspect_node_cases(work / "inspect-node", kernel)]
