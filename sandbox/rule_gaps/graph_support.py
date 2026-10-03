"""Real, isolated CLI fixtures for the second Rule sandbox audit.

Only the child CLI imports VibeFlow.  The handlers are ordinary trusted plugin
sources; their event files measure invocation rather than assuming it occurred.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Sandbox:
    target: str
    root: Path

    @property
    def project(self):
        return self.root / "project"

    @property
    def graph(self):
        return self.project / "bundle/rulesets/graph.jsonc"

    @property
    def node(self):
        return self.project / "bundle/nodes/calculate.jsonc"

    @property
    def config(self):
        return self.project / "configs/calculate.jsonc"

    @property
    def marker(self):
        return self.root / "rule-events.jsonl"

    def read(self, path):
        return json.loads(path.read_text())

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n")

    def events(self):
        return [json.loads(line) for line in self.marker.read_text().splitlines()] if self.marker.exists() else []

    def rule(self, name):
        return self.project / "bundle/rules" / (name + ".jsonc")

    def source(self, name):
        return self.project / "rules" / (name + (".py" if self.target == "python" else ".ts"))

    def command(self, command="validate", *options):
        arguments = [sys.executable, "-m", "vibeflow", command,
                     "--workspace", str(self.root / "vibeflow_config.jsonc"),
                     "--config", str(self.config), *options, "--json"]
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        process = subprocess.run(arguments, cwd=self.root, env=environment,
                                 capture_output=True, text=True, timeout=120)
        (self.root / (command + "-stdout.json")).write_text(process.stdout)
        (self.root / (command + "-stderr.log")).write_text(process.stderr)
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError:
            payload = {"status": "ERROR", "message": process.stdout + process.stderr}
        return process.returncode, payload


def create(work_root, target, case_id, toolchain_root=None):
    root = work_root / case_id.replace(".", "-") / target
    shutil.copytree(ROOT / "sandbox" / target / "rule_graph", root)
    case = Sandbox(target, root)
    if target == "javascript":
        toolchain = Path(toolchain_root or os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", ""))
        if not (toolchain / "node_modules").is_dir():
            raise FileNotFoundError("Real TS Rule cases require toolchain_root/node_modules")
        (case.project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    for name in ("provider", "checker", "replacement", "wrong-replacement"):
        value = case.read(case.rule(name))
        value["params_defaults"]["marker"] = str(case.marker)
        if name != "checker":
            value["params_defaults"]["source"] = str(case.source("provider"))
        case.write(case.rule(name), value)
    return case


def findings(payload):
    if isinstance(payload, dict):
        if ("message" in payload or "error" in payload) and ("code" in payload or "rule_id" in payload):
            yield payload
        for value in payload.values():
            yield from findings(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from findings(value)


def observation(code, payload, *, metrics=None):
    diagnostics = list(findings(payload))
    unique = {(str(item.get("code", item.get("rule_id"))), str(item.get("severity", "error"))) for item in diagnostics}
    status = payload.get("status", "FAIL" if code else "PASS")
    if status not in {"PASS", "CONCERNS", "FAIL", "ERROR"}:
        status = "FAIL" if code else "PASS"
    positions = []
    for item in diagnostics:
        location = item.get("source_location", {})
        positions.append({"code": item.get("code", item.get("rule_id")), **location,
                          "definition_id": item.get("definition_id", ""),
                          "object_id": item.get("object_id", item.get("subject_id", "")),
                          "calls": item.get("details", {}).get("calls", [])})
    return {"status": status, "codes": [{"code": name, "severity": severity} for name, severity in sorted(unique)],
            "positions": positions, "metrics": {"exit_code": code, **(metrics or {})},
            "message": json.dumps(payload, ensure_ascii=False)}


def row(case_id, target, title, family, expected, actual, **extra):
    return {"id": "gaps.graph." + target + "." + case_id, "title": title,
            "family": "rule_graph." + family, "classification": "new_feature",
            "expected": expected, "actual": actual, **extra}


def rejection(code, *, located=False, message="", metrics=None):
    value = {"should_accept": False, "codes": [{"code": code, "severity": "error"}],
             "metrics": {"exit_code": 1, **(metrics or {})}}
    if located:
        value["located_codes"] = [code]
    if message:
        value["message_contains"] = message
    return value


def acceptance(**metrics):
    return {"should_accept": True, "exact_codes": True, "codes": [],
            "metrics": {"exit_code": 0, **metrics}}


def graph(case, calls, relations=(), *, entrypoints=None):
    value = {"kind": "ruleset", "id": "example.rule_graph", "calls": list(calls), "relations": list(relations)}
    if entrypoints is not None:
        value["entrypoints"] = entrypoints
    case.write(case.graph, value)


def pair(consumer="checker", provider="provider"):
    return {"source": consumer, "target": provider, "kind": "requires", "bindings": {"numbers": "numbers"}}


def formal(case):
    code, payload = case.command()
    return code, payload, observation(code, payload)


def builtin_control(case):
    """Control uses the existing Target adapter; it supplies actual AST metrics."""
    graph(case, [{"id": "metrics", "rule_id": "vibeflow.maintainability"}])
    code, payload = case.command()
    return observation(code, payload)


def result_states(payload):
    """Read actual engine states, never infer them from findings or markers."""
    if isinstance(payload, dict):
        if isinstance(payload.get("results"), dict):
            for key, value in payload["results"].items():
                if isinstance(value, dict) and "state" in value:
                    yield key, value["state"]
        for value in payload.values():
            yield from result_states(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from result_states(value)


def javascript_states(case):
    """Supplement negative CLI diagnostics with the public Target result API.

    A failed JS CLI currently serializes diagnostics without execution states.
    This second real worker run is explicitly separate; its states do not stand
    in for the first command's exit, findings, or measured consumer execution.
    """
    script = '''import json
from pathlib import Path
from vibeflow.core.rules.models import plain
from vibeflow.targets.javascript.quality.rules import run_javascript_rules
from vibeflow.tooling.project.descriptor_loader import load_project_descriptor_catalogs
from vibeflow.tooling.project.graph_config import parse_graph_config
project=Path(PROJECT)
catalogs=load_project_descriptor_catalogs(project)
graph=parse_graph_config(json.loads(Path(CONFIG).read_text()),project_root=project)
report=run_javascript_rules(graph,catalogs,project_root=project,package_root=project,target="node",phase="static")
print(json.dumps(report.to_dict()))
'''.replace("PROJECT", repr(str(case.project))).replace("CONFIG", repr(str(case.config)))
    process = subprocess.run([sys.executable, "-c", script], cwd=case.root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True, timeout=120)
    (case.root / "target-state-stdout.json").write_text(process.stdout)
    (case.root / "target-state-stderr.log").write_text(process.stderr)
    if process.returncode:
        raise RuntimeError("public Target state probe failed: " + process.stderr)
    return dict(result_states(json.loads(process.stdout)))


def measured_error(exc):
    return {"status": "ERROR", "codes": [], "positions": [], "metrics": {},
            "message": f"{type(exc).__name__}: {exc}"}
