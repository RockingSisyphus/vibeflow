"""Small real projects for the JavaScript public Rule/API gap sandbox.

Only standard-library modules are imported before the isolated runner chooses
the kernel. Projects contain ordinary JSONC resources and TS/JS implementations.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import traceback
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
VALUE_TYPE = "gaps.value.v1"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Project:
    root: Path

    @property
    def project(self) -> Path:
        return self.root / "project"

    @property
    def config(self) -> Path:
        return self.project / "configs/calculate.jsonc"

    @property
    def workspace(self) -> Path:
        return self.root / "vibeflow_config.jsonc"

    @property
    def marker(self) -> Path:
        return self.root / "rule-events.jsonl"

    def arguments(self) -> list[str]:
        return ["--workspace", str(self.workspace), "--config", str(self.config)]

    def events(self) -> list[dict[str, Any]]:
        if not self.marker.exists():
            return []
        return [json.loads(line) for line in self.marker.read_text().splitlines()]


def new_project(work_root: Path, name: str, toolchain_root: Path | None) -> Project:
    root = work_root / name
    shutil.copytree(ROOT / "sandbox/javascript/rule_graph", root,
                    ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc", ".artifacts", "dist", "runs"))
    result = Project(root)
    toolchain = Path(toolchain_root or os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", ROOT / "sandbox/javascript/minimal/project"))
    if not (toolchain / "node_modules/typescript").is_dir():
        raise FileNotFoundError("gap sandbox requires the pinned TypeScript/esbuild toolchain")
    (result.project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    # A source file is not assigned two different Node contracts. This keeps
    # helper/capability declarations from masking the API being tested.
    (result.project / "nodes/boundary.ts").write_text("export function boundary() { return {}; }\n")
    boundary = result.project / "bundle/nodes/boundary.jsonc"
    data = read_json(boundary)
    data["implementations"][0]["source"]["ref"] = "nodes/boundary.ts"
    write_json(boundary, data)
    (result.project / "nodes/calculation.ts").write_text(
        'export function calculate(inputs) { return {result: inputs["example.input"].value * 2 + 1}; }\n')
    for name in ("provider", "checker", "replacement", "wrong-replacement"):
        path = result.project / "bundle/rules" / (name + ".jsonc")
        data = read_json(path)
        data["params_defaults"]["marker"] = str(result.marker)
        write_json(path, data)
    data = read_json(result.project / "vibeflow_project.jsonc")
    data["quality_enabled"] = True
    data["architecture"] = {"documents": [{"workflow": "configs/calculate.jsonc", "document": "ARCHITECTURE.jsonc"}]}
    write_json(result.project / "vibeflow_project.jsonc", data)
    return result


def select_provider_and_consumer(project: Project, provider_source: str) -> None:
    (project.project / "rules/provider.ts").write_text(provider_source, encoding="utf-8")
    provider = project.project / "bundle/rules/provider.jsonc"
    data = read_json(provider)
    data["outputs"] = {"value": VALUE_TYPE}
    write_json(provider, data)
    checker = project.project / "bundle/rules/checker.jsonc"
    data = read_json(checker)
    data["inputs"] = {"value": VALUE_TYPE}
    write_json(checker, data)
    (project.project / "rules/checker.ts").write_text('''import {appendFileSync} from "node:fs";
export function check(context, inputs, params) {
  const proof = {handler:"consumer", phase:context.phase, received:inputs.value.value, type_id:inputs.value.type_id};
  appendFileSync(params.marker, JSON.stringify(proof)+"\\n");
  return {records:{proof:{type_id:"example.proof.v1",value:proof}}};
}
''', encoding="utf-8")
    path = project.project / "bundle/rulesets/graph.jsonc"
    data = read_json(path)
    data["relations"][0]["bindings"] = {"value": "value"}
    data["entrypoints"] = {"static": ["checker"], "import": [], "run": []}
    write_json(path, data)


def finding_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for item in value for row in finding_rows(item)]
    if not isinstance(value, dict):
        return []
    result = [value] if ("code" in value or "rule_id" in value) and ("message" in value or "error" in value) else []
    for item in value.values():
        if isinstance(item, (dict, list)):
            result.extend(finding_rows(item))
    return result


def actual(payload: dict[str, Any], *, exit_code: int) -> dict[str, Any]:
    rows = finding_rows(payload)
    codes, positions = [], []
    for row in rows:
        code = str(row.get("code", row.get("rule_id", "")))
        identity = {"code": code, "severity": str(row.get("severity", "error"))}
        if identity not in codes:
            codes.append(identity)
        location = dict(row.get("source_location") or {})
        if not location.get("path"):
            location["path"] = row.get("file", row.get("path", row.get("source_path", "")))
        if location.get("path"):
            positions.append({"code": code, **location})
    return {"status": payload.get("status", "ERROR" if exit_code else "PASS"), "codes": codes,
            "positions": positions, "metrics": {"exit_code": exit_code},
            "message": json.dumps(payload, ensure_ascii=False)}


def command(project: Project, name: str, *options: str, label: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    from vibeflow.tooling.application.cli import main
    output, errors = StringIO(), StringIO()
    try:
        with redirect_stdout(output), redirect_stderr(errors):
            code = main([name, *project.arguments(), *options])
        payload = json.loads(output.getvalue())
    except BaseException as error:
        code = 2
        payload = {"status": "ERROR", "code": "SANDBOX.UNCAUGHT", "message": str(error),
                   "traceback": traceback.format_exc(), "stdout": output.getvalue()}
    label = label or name
    write_json(project.root / (label + ".json"), payload)
    (project.root / (label + ".stderr")).write_text(errors.getvalue(), encoding="utf-8")
    observed = actual(payload, exit_code=code)
    consumers = [event for event in project.events() if event.get("handler") == "consumer"]
    observed["metrics"].update(consumer_executions=len(consumers))
    if consumers:
        observed["metrics"]["received"] = consumers[-1]["received"]
    return observed, payload


def execute_business(project: Project, payload: dict[str, Any], *, host: bool = False) -> dict[str, Any]:
    entry = payload.get("entry")
    if not entry or not Path(entry).is_file():
        return {"business_executed": False}
    invocation = ('const host=workflow.createWorkflowHost();await host.start();'
                  'const result=await (host.runWorkflowAsync??host.runWorkflow)({value:3});await host.stop();') if host else (
                  'const result=await (workflow.runWorkflowAsync??workflow.runWorkflow)({value:3});')
    script = ('import {pathToFileURL} from "node:url";globalThis.__gapEvents=[];'
              'const workflow=await import(pathToFileURL(' + json.dumps(entry) + '));'
              'const eventsAfterImport=[...globalThis.__gapEvents];' + invocation +
              'process.stdout.write(JSON.stringify({result,eventsAfterImport,events:globalThis.__gapEvents}));')
    process = subprocess.run(["node", "--input-type=module", "--eval", script], cwd=project.project,
                             capture_output=True, text=True, check=False, timeout=30)
    (project.root / "business.stdout").write_text(process.stdout)
    (project.root / "business.stderr").write_text(process.stderr)
    metrics = {"business_executed": process.returncode == 0, "runtime_exit_code": process.returncode}
    if process.returncode == 0:
        result = json.loads(process.stdout)
        metrics.update(business_result=result["result"]["result"], lifecycle=result["events"], import_events=result["eventsAfterImport"])
    return metrics


def add_helper(project: Project, kind: str) -> Path:
    javascript = kind == "require"
    helper = project.project / "nodes" / ("helper.js" if javascript else "helper.ts")
    helper.write_text('export function double(value' + ('' if javascript else ':number') + ') { return value * 2; }\n')
    source = project.project / "nodes" / ("calculation.js" if javascript else "calculation.ts")
    if kind == "dynamic":
        code = ('\n\n\nexport async function calculate(inputs) {\n'
                '  const helper = await import("./helper.js");\n'
                '  return {result:helper.double(inputs["example.input"].value)+1};\n}\n')
    elif javascript:
        code = ('\n\n\nconst helper = require("./helper.js");\n'
                'export function calculate(inputs) { return {result:helper.double(inputs["example.input"].value)+1}; }\n')
    else:
        code = ('\n\n\nimport {double} from "./helper.js";\n'
                'export function calculate(inputs) { return {result:double(inputs["example.input"].value)+1}; }\n')
    source.write_text(code)
    descriptor = project.project / "bundle/nodes/calculate.jsonc"
    data = read_json(descriptor)
    data["base_libs"] = ["gaps.helper"]
    implementation = data["implementations"][0]
    implementation["source"]["ref"] = source.relative_to(project.project).as_posix()
    implementation["language"] = "javascript" if javascript else "typescript"
    implementation["completion"] = "suspend" if kind == "dynamic" else "immediate"
    write_json(descriptor, data)
    config = read_json(project.config)
    config["pipeline"]["entry_mode"] = "async" if kind == "dynamic" else "sync"
    write_json(project.config, config)
    declaration = {"kind":"base_lib", "id":"gaps.helper", "display_name":"Numeric helper", "description":"Actually reached helper.",
                   "implementations":[{"language":"javascript" if javascript else "typescript", "targets":["node","browser"],
                                       "source":{"kind":"file","ref":helper.relative_to(project.project).as_posix()}}]}
    write_json(project.project / "bundle/helper.jsonc", declaration)
    bundle = project.project / "bundles/rule-graph.jsonc"
    data = read_json(bundle)
    data["resources"]["base_lib"] = ["../bundle/helper.jsonc"]
    write_json(bundle, data)
    return helper


NATIVE_GROUPS = ("base_lib", "data_schemas", "capabilities", "host_extensions", "plugins")


def bundle_native_resources(project: Project) -> dict[str, Path]:
    """Contribute all native groups through one ordinary bundle, then use them."""
    data = read_json(project.project / "vibeflow_project.jsonc")
    data["descriptors"] = {"bundles": ["bundles"]}
    write_json(project.project / "vibeflow_project.jsonc", data)
    node = project.project / "bundle/nodes/calculate.jsonc"
    data = read_json(node)
    data.update(rulesets=[], base_libs=["gaps.helper"], capabilities=[{"id":"gaps.math", "operations":["offset"]}])
    write_json(node, data)
    (project.project / "nodes/calculation.ts").write_text('''import {double} from "../base_lib/math.js";
export function calculate(inputs, params, context) {
  return {result:context.capabilities["gaps.math"].offset(double(inputs["example.input"].value))};
}
''')
    for directory in ("base_lib", "host_extensions", "plugins"):
        (project.project / directory).mkdir()
    (project.project / "base_lib/math.ts").write_text("export function double(value:number):number { return value * 2; }\n")
    (project.project / "host_extensions/math.ts").write_text('''export function createHostExtension() {
  const events=(globalThis as unknown as {__gapEvents:string[]}).__gapEvents;
  events.push("host:create");
  return {capabilities:{"gaps.math":{offset(value:number):number {
    events.push("capability:offset"); return value+1;
  }}}, start(){events.push("host:start");}, stop(){events.push("host:stop");}};
}
''')
    (project.project / "plugins/runtime.ts").write_text('''export function createPlugin(context) {
  if(context.abiVersion!=="vibeflow.plugin.v2") throw new Error("Wrong Plugin ABI");
  const events=(globalThis as unknown as {__gapEvents:string[]}).__gapEvents;
  events.push("plugin:create");
  return {beforeRun(){events.push("plugin:beforeRun");},afterRun(){events.push("plugin:afterRun");},
          dispose(){events.push("plugin:dispose");}};
}
''')
    implementation = lambda ref, export="": {"language":"typescript", "targets":["node","browser"],
                                            "source":{"kind":"file","ref":ref, **({"export":export} if export else {})}}
    resources = {
        "base_lib": {"kind":"base_lib", "id":"gaps.helper", "display_name":"Bundled numeric helper", "description":"A bundled numeric helper.",
                     "implementations":[implementation("base_lib/math.ts")]},
        "capabilities": {"kind":"capability", "id":"gaps.math", "targets":["node","browser"],
                         "operations":{"offset":{"input_type":"example.input", "output_type":"example.output", "completion":"immediate"}}},
        "host_extensions": {"kind":"host_extension", "id":"gaps.host", "targets":["node","browser"],
                            "implementations":[implementation("host_extensions/math.ts","createHostExtension")], "provides":["gaps.math"]},
        "plugins": {"kind":"plugin", "id":"gaps.runtime", "type":"runtime", "targets":["node","browser"],
                    "implementations":[implementation("plugins/runtime.ts","createPlugin")],
                    "config":{"schema":{"type":"object","additionalProperties":False},"defaults":{}}},
    }
    paths = {group: project.project / "bundle/native" / (group + ".jsonc") for group in resources}
    for group, declaration in resources.items():
        write_json(paths[group], declaration)
    schema = project.project / "bundle/native/input.jsonc"
    write_json(schema, read_json(project.project / "manifests/data/input.jsonc"))
    output = project.project / "bundle/native/output.jsonc"
    write_json(output, read_json(project.project / "manifests/data/output.jsonc"))
    paths["data_schemas"] = schema
    bundle = project.project / "bundles/rule-graph.jsonc"
    data = read_json(bundle)
    data["resources"].update({group:["../"+path.relative_to(project.project).as_posix()] for group,path in paths.items()})
    data["resources"]["data_schemas"].append("../bundle/native/output.jsonc")
    write_json(bundle, data)
    config = read_json(project.config)
    config.update(plugins=["gaps.runtime"], host_extensions=["gaps.host"])
    write_json(project.config, config)
    return paths


def loaded_native_groups(project: Project) -> dict[str, Any]:
    from vibeflow.tooling.project.descriptor_loader import load_project_descriptor_catalogs
    catalogs = load_project_descriptor_catalogs(project.project)
    checks = {"base_lib":catalogs.base_libs.get("gaps.helper"), "data_schemas":catalogs.schemas.get("example.input"),
              "capabilities":catalogs.capabilities.get("gaps.math"), "host_extensions":catalogs.host_extensions.get("gaps.host"),
              "plugins":catalogs.plugins.get("gaps.runtime")}
    return {"native_groups_loaded":all(checks.values()),
            "bundle_only":set(read_json(project.project / "vibeflow_project.jsonc")["descriptors"])=={"bundles"}}
