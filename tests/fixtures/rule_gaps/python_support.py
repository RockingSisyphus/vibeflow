"""Generate independent projects and retain CLI, source, and runtime evidence."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from tests.fixtures.support.plugins import resource


def _fixture():
    location = Path(__file__).parents[1] / "rule_parity/python/fixture.py"
    specification = importlib.util.spec_from_file_location("rule_gaps_parity_fixture", location)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _write_project(root, spec, fixture):
    fixture._write_project(root, "current", {"entrypoint": "cli.run", "rulesets": spec.get("rulesets", []),
                                             "source": spec.get("source", fixture.DEFAULT_SOURCE)})
    node_path = resource(root, "node", "parity.node")
    node = json.loads(node_path.read_text(encoding="utf-8"))
    node["rulesets"] = spec.get("rulesets", [])
    if "start_source" in spec:
        (root / "start.py").write_text(spec["start_source"], encoding="utf-8")
    start_path = resource(root, "node", "parity.start")
    start = json.loads(start_path.read_text(encoding="utf-8"))
    start["rulesets"] = spec.get("start_rulesets", [])
    start_path.write_text(json.dumps(start), encoding="utf-8")
    if "helper_source" in spec:
        _write_source(root / "helper.py", root, spec["helper_source"])
        node["implementations"][0]["implementation_files"] = [{"kind": "file", "ref": "helper.py"}]
        if "start_source" in spec:
            start["implementations"][0]["implementation_files"] = [{"kind": "file", "ref": "helper.py"}]
            start_path.write_text(json.dumps(start), encoding="utf-8")
    node_path.write_text(json.dumps(node), encoding="utf-8")
    if "stub_source" in spec:
        workflow_path = root / "workflow.jsonc"
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        workflow["pipeline"]["nodes"][1].update(
            flow_kind="process", requires=[], provides=deepcopy(fixture.DEFAULT_CONTRACT["provides"]),
            input_semantics={}, output_semantics=deepcopy(fixture.DEFAULT_CONTRACT["output_semantics"]),
            status="planned", planned_behavior={"kind": "python_stub", "stub_module": "stubs/work.py"})
        workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
        _write_source(root / "stubs/__init__.py", root, "")
        _write_source(root / "stubs/work.py", root, spec["stub_source"])
        if "stub_helper_source" in spec:
            _write_source(root / "stubs/helper.py", root, spec["stub_helper_source"])


def _write_source(path, root, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source.replace("__MARKER__", repr(str(root / "marker.txt"))), encoding="utf-8")


SOURCE_SCRIPT = '''import json,sys
from pathlib import Path
from vibeflow.tooling.application.python.project.declarations import declared_python_registry,collect_workflow_source_context
from vibeflow.tooling.project.workspace_loader import load_workspace_config
from vibeflow.tooling.project.config_loader import load_config_document
from vibeflow.tooling.project.graph_config import parse_graph_config
root=Path(sys.argv[1])
registry=declared_python_registry(load_workspace_config(root.parent/'vibeflow_config.jsonc'),config_path=root/'workflow.jsonc')
graph=parse_graph_config(load_config_document(root/'workflow.jsonc').data,project_root=root)
context=collect_workflow_source_context(registry,graph)
relative=lambda path: str(Path(path).relative_to(root)) if path else ''
proof={'node_paths':{node.definition_id:relative(node.path) for node in context.nodes},
       'node_rulesets':{node.definition_id:list(registry.rulesets(node.definition_id)) for node in context.nodes},
       'source_files':[relative(source.path) for source in context.files],
       'physical_imports':[{'path':relative(item.path),'resolved_path':relative(item.resolved_path),
                           'module':item.module,'symbol':item.symbol,'alias':item.alias,'line':item.line}
                          for item in context.imports],
       'helper_owners':sorted({item.definition_id for item in context.ownership
                              if item.symbol_id==str(root/'helper.py')+':transform'}),
       'calls':[{'type':item.definition_id,'owner':item.owner,'path':list(item.call_path)} for item in context.calls]}
print(json.dumps(proof))
'''


def _source_proof(root, environment):
    command = [sys.executable, "-c", SOURCE_SCRIPT, str(root)]
    result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("source-context observation failed: " + result.stderr)
    return json.loads(result.stdout)


def _runtime_proof(root):
    trace = root / "runs/import-marker/runtime_trace.jsonl"
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()] if trace.exists() else []
    summary = next((item for item in reversed(events) if item.get("kind") == "runtime_summary"), {})
    demo = next((item for item in events if item.get("kind") in {"node", "planned_stub"} and item.get("node") == "demo"), {})
    return {"runtime_completed": summary.get("stop_reason") == "completed",
            "runtime_exec_order": summary.get("exec_order", []),
            "runtime_output_keys": sorted(demo.get("output_summary", {})),
            "runtime_demo": demo, "runtime_summary": summary}


def _health_findings(actual):
    health = actual["payload"].get("health", {})
    return [*health.get("errors", []), *health.get("warnings", [])]


def _finding_proof(actual, root):
    errors = [item for item in _health_findings(actual) if item.get("severity") == "error"]
    source_files = set()
    associations = []
    for item in errors:
        path = item.get("source_location", {}).get("path", "")
        if path:
            source_files.add(str(Path(path).relative_to(root)))
        associations.append({"code": item.get("code", item.get("rule_id", "")),
                             "definition_id": item.get("definition_id", ""),
                             "type": item.get("details", {}).get("node_type", item.get("object_id", "")),
                             "calls": item.get("details", {}).get("calls", []),
                             "location": item.get("source_location", {})})
    return {"error_owner_types": sorted({item["type"] for item in associations}),
            "error_source_files": sorted(source_files), "error_associations": associations}


def observe(work_root, spec):
    root = Path(work_root) / spec["id"].replace(".", "_")
    root.mkdir(parents=True, exist_ok=False)
    fixture = _fixture()
    _write_project(root, spec, fixture)
    command = fixture._command(root, "current", {"entrypoint": "cli.run"})
    if "stub_source" in spec:
        command.append("--allow-planned-stub")
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    scope = _source_proof(root, environment)
    result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True, timeout=30)
    (root / "command.stdout").write_text(result.stdout, encoding="utf-8")
    (root / "command.stderr").write_text(result.stderr, encoding="utf-8")
    # Successful CLI output is compact; consume its actual saved health report.
    health_path = root / "runs/import-marker/health_report.json"
    if health_path.exists():
        payload = json.loads(result.stdout)
        payload["health"] = json.loads(health_path.read_text(encoding="utf-8"))
        result = subprocess.CompletedProcess(command, result.returncode, json.dumps(payload), result.stderr)
    actual = fixture._actual(result, root)
    actual["metrics"].update(scope, **_runtime_proof(root), **_finding_proof(actual, root))
    return {"id": spec["id"], "title": spec["title"], "family": spec["family"],
            "classification": spec["classification"], "expected": deepcopy(spec["expected"]),
            "actual": actual, "notes": spec.get("notes", ""),
            "evidence": {"entrypoint": "cli.run", "project": str(root), "command": command,
                         "initial": {}, "source_observer": "collect_workflow_source_context"}}
