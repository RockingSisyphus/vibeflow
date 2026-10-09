"""Validate nested JSON defaults and isolation in actual reusable runtimes."""

import argparse
import json
from pathlib import Path
import sys


REPOSITORY = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY / "src"))

from tests.fixtures.python.sdk_defaults.validate_probe import write_project
from vibeflow.targets.python import PipelineRuntime
from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export
from vibeflow.tooling.project.workspace_loader import load_workspace_config


BODY = '''        value = params["cleanup_record_roots"]
        entries = value["a"]
        nested = entries[0]["b"]
        before = len(nested)
        nested.append("visited")
        return {"result": {"before": before, "after": len(nested),
                           "object_is_dict": isinstance(value, dict),
                           "array_is_list": isinstance(entries, list),
                           "nested_is_list": isinstance(nested, list)}}'''


def observe(root, mode, selection):
    defaults = {"a": [{"b": []}]}
    override = {"a": [{"b": ["configured"]}]}
    write_project(root, "object", defaults)
    source = root / "plugin.py"
    source.write_text(source.read_text().replace(
        '        value = params["cleanup_record_roots"]\n'
        '        return {"result": {"value": value, "native_type": type(value).__name__}}', BODY))
    if selection == "call_override":
        workflow = json.loads((root / "workflow.jsonc").read_text())
        workflow["pipeline"]["nodes"][1]["config"] = {"cleanup_record_roots": override}
        (root / "workflow.jsonc").write_text(json.dumps(workflow))
    workspace = load_workspace_config(root / "vibeflow_config.jsonc")
    graph, _, registry, _, health = load_workspace_graph_for_export(
        root / "workflow.jsonc", workspace=workspace, validate_health=True)
    if health is not None:
        return {"status": "FAIL", "phase": "validate", "health": health.to_dict()}
    options = {"execution": mode}
    external = {"inspect": {"cleanup_record_roots": override}} if selection == "runtime_override" else None
    runtime = PipelineRuntime(graph, registry=registry, run_dir=root / "runs",
                              node_config_overrides=external, runtime_options=options)
    first = dict(runtime.run({}).get("inspection")["value"])
    second = dict(runtime.run({}).get("inspection")["value"])
    independent = PipelineRuntime(graph, registry=registry, run_dir=root / "independent-runs",
                                  node_config_overrides=external, runtime_options=options)
    third = dict(independent.run({}).get("inspection")["value"])
    expected = {"before": 0 if selection == "defaults" else 1,
                "after": 1 if selection == "defaults" else 2,
                "object_is_dict": True, "array_is_list": True, "nested_is_list": True}
    saved = registry.get_config_spec("probe.defaults").defaults["cleanup_record_roots"]
    descriptor = registry.descriptor("probe.defaults")
    frozen = descriptor.contract.params_defaults["cleanup_record_roots"]
    readonly = isinstance(frozen["a"], tuple) and isinstance(frozen["a"][0]["b"], tuple)
    try:
        frozen["new"] = True
    except TypeError:
        pass
    else:
        readonly = False
    passed = first == second == third == expected and saved == defaults and override == {"a": [{"b": ["configured"]}]} and readonly
    return {"status": "PASS" if passed else "FAIL", "expected": expected,
            "first_run": first, "same_runtime_second_run": second, "independent_runtime": third,
            "stored_defaults": saved, "caller_override": override, "descriptor_readonly": readonly}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    cases = []
    for mode in ("plan", "block", "compiled"):
        for selection in ("defaults", "call_override", "runtime_override"):
            case_id = f"{mode}.{selection}"
            result = observe(args.work.resolve() / case_id, mode, selection)
            cases.append({"id": case_id, **result})
    report = {"schema": "vibeflow.sdk-defaults-runtime.v1", "cases": cases,
              "summary": {"cases": len(cases), "passed": sum(case["status"] == "PASS" for case in cases)}}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"]))
    return 0 if all(case["status"] == "PASS" for case in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
