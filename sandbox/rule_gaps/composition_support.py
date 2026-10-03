"""Real domain project generation, formal CLI execution, and diagram evidence."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from common import cli, command, copy_project, diagnostics, row, write


def _call(name, type_key, **fields):
    return {"id": name, "type_used": type_key, "display_name": name.title(),
            "description": "Native composition of the selected domain bundle.", **fields}


def _require(type_key):
    return {"type": type_key, "cardinality": "exactly_one", "display_name": type_key}


def _provider(key, type_key):
    return {"key": key, "type": type_key, "display_name": key}


def _edge(source, target, **fields):
    return {"source": source, "target": target, **fields}


def _bundle_resource(project, group, ref):
    path = project / "bundles/domain.jsonc"
    bundle = json.loads(path.read_text())
    bundle["resources"].setdefault(group, []).append(ref)
    write(path, bundle)


def _gain(project, target):
    if target == "python":
        return
    path = project / "nodes/model.ts"
    path.write_text('type Envelope = Readonly<{value: number}>;\n'
                    'export function modelForward(value: number, gain: number): number { return value * gain; }\n'
                    'export function run(inputs: Readonly<{"example.input": Envelope}>, params: Readonly<{gain: number}>) {\n'
                    '  return {feature: modelForward(inputs["example.input"].value, params.gain)};\n}\n')
    declaration = project / "bundle/nodes/model.jsonc"
    data = json.loads(declaration.read_text())
    data["contract"].update(params_schema={"gain": {"type": "number"}}, params_defaults={"gain": 2})
    write(declaration, data)


def _choose(project, target):
    language = "python" if target == "python" else "typescript"
    ref = "choose.py" if target == "python" else "nodes/choose.ts"
    source = ('class Choose:\n    def run_pure(self, inputs, params):\n'
              '        return {"forwarded": inputs["example.choice_input"]["value"], "route.branch": params["branch"]}\n'
              if target == "python" else
              'export function run(inputs: Readonly<{"example.choice_input": Readonly<{value: number}>}>, params: Readonly<{branch: string}>) {\n'
              '  return {forwarded: inputs["example.choice_input"].value, "route.branch": params.branch};\n}\n')
    (project / ref).write_text(source)
    write(project / "bundle/nodes/choose.jsonc", {"kind": "node", "type_key": "example.choose",
          "display_name": "Choose",  "description": "Choose one native conditional branch.",
          "version": "0.15.0", "flow_kind": "decision", "rulesets": ["vibeflow.process"],
          "contract": {"requires": [_require("example.choice_input")],
              "provides": [_provider("route.branch", "route.branch"), _provider("forwarded", "example.input")],
              "input_semantics": {"example.choice_input": ["The initial numeric value."]},
              "output_semantics": {"route.branch": ["The selected conditional branch."], "forwarded": ["The numeric model input."]},
              "params_schema": {"branch": {"type": "string"}}, "params_defaults": {"branch": "left"}},
          "implementations": [{"language": language, "targets": ["python"] if target == "python" else ["node", "browser"],
              "source": {"kind": "file", "ref": ref, "export": "Choose" if target == "python" else "run"}}]})
    _bundle_resource(project, "nodes", "../bundle/nodes/choose.jsonc")
    write(project / "manifests/data/branch.jsonc", {"kind": "data_schema", "type_key": "route.branch",
          "representation": "json", "schema": {"type": "string"}})


def _branch_ports(project, target):
    for name in ("left", "right"):
        type_key = "example." + name + "_feature"
        ref = name + "_feature.py" if target == "python" else "nodes/" + name + "_feature.ts"
        source = ('class Rekey:\n    def run_pure(self, inputs, params):\n'
                  f'        return {{"{name}_feature": inputs["example.feature"]["value"]}}\n'
                  if target == "python" else
                  'export function run(inputs: Readonly<{"example.feature": Readonly<{value: number}>}>) {\n'
                  f'  return {{{name}_feature: inputs["example.feature"].value}};\n}}\n')
        (project / ref).write_text(source)
        write(project / ("bundle/nodes/" + name + "-feature.jsonc"), {"kind": "node", "type_key": type_key,
            "display_name": name.title() + " Feature",  "description": "Expose an isolated branch value.",
            "version": "0.15.0", "flow_kind": "process", "contract": {"requires": [_require("example.feature")],
                "provides": [_provider(name + "_feature", type_key)], "input_semantics": {"example.feature": ["The model result."]},
                "output_semantics": {name + "_feature": ["This branch's unique output."]}},
            "implementations": [{"language": "python" if target == "python" else "typescript",
                "targets": ["python"] if target == "python" else ["node", "browser"],
                "source": {"kind": "file", "ref": ref, "export": "Rekey" if target == "python" else "run"}}]})
        _bundle_resource(project, "nodes", "../bundle/nodes/" + name + "-feature.jsonc")
        write(project / ("manifests/data/" + name + "-feature.jsonc"), {"kind": "data_schema", "type_key": type_key,
              "representation": "json", "schema": {"type": "number"}})
    write(project / "manifests/data/choice-input.jsonc", {"kind": "data_schema", "type_key": "example.choice_input",
          "representation": "json", "schema": {"type": "number"}})
    path = project / "bundle/nodes/transform.jsonc"
    declaration = json.loads(path.read_text())
    declaration["contract"]["requires"] = [{**_require("example." + name + "_feature"), "cardinality": "optional_one"} for name in ("left", "right")]
    declaration["contract"]["input_semantics"] = {"example." + name + "_feature": ["The one active branch result."] for name in ("left", "right")}
    declaration["contract"]["examples"] = []
    write(path, declaration)
    if target == "python":
        path = project / "domain_nodes.py"
        path.write_text(path.read_text().replace('value = inputs["example.feature"]["value"]',
            'packet = inputs.get("example.left_feature") or inputs.get("example.right_feature")\n        value = packet["value"]'))
    else:
        (project / "nodes/transform.ts").write_text('type Envelope = Readonly<{value: number}>;\n'
            'export function run(inputs: Readonly<{"example.left_feature": Envelope | null; "example.right_feature": Envelope | null}>) {\n'
            '  const packet = inputs["example.left_feature"] ?? inputs["example.right_feature"];\n'
            '  return {output: packet!.value + 1};\n}\n')


def _flow(project, spec):
    path = project / "configs/model.jsonc"
    data = json.loads(path.read_text())
    original = deepcopy(data["pipeline"])
    if spec["form"] == "branch":
        _choose(project, spec["target"])
        _branch_ports(project, spec["target"])
        data["pipeline"]["inputs"][0]["type"] = "example.choice_input"
        data["nodeset_imports"] = []
        for name, gain in (("left", 2), ("right", 3)):
            branch_body = {"type_key": "example." + name + "_model", "display_name": name.title() + " Model",
                "description": "An isolated native invocation of the same model Node type.",
                "requires": [_require("example.input")], "provides": [_provider(name + "_feature", "example." + name + "_feature")],
                "pipeline": {"inputs": deepcopy(original["inputs"]),
                    "nodes": [_call("start", "example.boundary"), _call("model", "example.model", gain=gain),
                              _call("rekey", "example." + name + "_feature"), _call("end", "example.boundary")],
                    "edges": [_edge("start", "model"), _edge("model", "rekey"), _edge("rekey", "end")],
                    "outputs": [{**_require("example." + name + "_feature"), "as": name + "_feature"}]}}
            write(project / ("configs/nodesets/" + name + ".jsonc"), branch_body)
            data["nodeset_imports"].append({"path": "nodesets/" + name + ".jsonc"})
        data["pipeline"]["nodes"] = [_call("start", "example.boundary"),
            _call("choose", "example.choose", branch=spec["branch"]),
            _call("left", "example.left_model"), _call("right", "example.right_model"),
            _call("transform", "example.transform", join_policy="any_active"), _call("end", "example.boundary")]
        data["pipeline"]["edges"] = [_edge("start", "choose"),
            _edge("choose", "left", when="route.branch == 'left'"),
            _edge("choose", "right", when="route.branch == 'right'"),
            _edge("left", "transform"), _edge("right", "transform"), _edge("transform", "end")]
    else:
        if spec["form"] == "loop":
            original["inputs"][0]["key"] = "example.input"
        body = {"type_key": "example.domain_stage", "display_name": "Domain Stage",
                "description": "Reusable native domain pipeline.", "rulesets": ["vibeflow.workflow"],
                "requires": [_require("example.input")], "provides": [_provider("result", "example.output")],
                "pipeline": original}
        write(project / "configs/nodesets/stage.jsonc", body)
        data["nodeset_imports"] = [{"path": "nodesets/stage.jsonc"}]
        if spec["form"] == "nodeset":
            middle = _call("stage", "example.domain_stage")
        else:
            middle = _call("loop", "vibeflow.loop.while", requires=[_require("example.input")],
                provides=[_provider("result", "example.output")], loop={"body": "example.domain_stage",
                    "max_iterations": 1, "stop_after": 1,
                    "carry": [{"from": "example.input", "as": "example.input", "update": "result"}],
                    "outputs": [{"from": "result", "as": "result"}]})
        data["pipeline"]["nodes"] = [_call("start", "example.boundary"), middle, _call("end", "example.boundary")]
        data["pipeline"]["edges"] = [_edge("start", middle["id"]), _edge(middle["id"], "end")]
    write(path, data)
    config_path = project / "vibeflow_project.jsonc"
    config = json.loads(config_path.read_text())
    # The normal case generates its registered document before formal checking.
    if spec["variant"] == "normal":
        config["architecture"] = {"documents": [{"workflow": "configs/model.jsonc", "document": "Architecture.jsonc"}]}
        write(config_path, config)


def _invalid(project, spec):
    target = spec["target"]
    if spec["variant"] == "missing_model":
        path = project / ("domain_nodes.py" if target == "python" else "nodes/model.ts")
        marker = "model_forward" if target == "python" else "modelForward"
        path.write_text(path.read_text().replace(marker, "_forward"))
    elif spec["variant"] == "helper_model":
        if target == "python":
            helper = project / "domain_helpers/illegal_model.py"
            helper.write_text('def model_forward(value):\n    return value + 1\n')
            path = project / "domain_nodes.py"
            source = path.read_text().replace("from domain_helpers.arithmetic import scale",
                "from domain_helpers.arithmetic import scale\nfrom domain_helpers.illegal_model import model_forward")
            path.write_text(source.replace('value + params["offset"]', 'model_forward(value) + params["offset"]'))
        else:
            (project / "nodes/transform_helper.ts").write_text('export function modelForward(value: number) { return value + 1; }\n')
            source = (project / "nodes/transform.ts").read_text()
            source = source.replace('packet!.value + 1', 'modelForward(packet!.value)').replace('inputs["example.feature"].value + 1', 'modelForward(inputs["example.feature"].value)')
            (project / "nodes/transform.ts").write_text('import {modelForward} from "./transform_helper.ts";\n' + source)
            path = project / "bundle/nodes/transform.jsonc"
            data = json.loads(path.read_text()); data["base_libs"] = ["example.transform_helper"]
            write(path, data)
            write(project / "bundle/base_lib/helper.jsonc", {"kind": "base_lib", "id": "example.transform_helper",
                "display_name": "Transform helper", "description": "A helper owned by the transform.",
                "implementations": [{"language": "typescript", "targets": ["node", "browser"],
                    "source": {"kind": "file", "ref": "nodes/transform_helper.ts"}}]})
            _bundle_resource(project, "base_lib", "../bundle/base_lib/helper.jsonc")


PYTHON_RUN = '''import json,sys
from pathlib import Path
from vibeflow.tooling.application.cli import main
import vibeflow.tooling.application.python.workspace_service as service
original=service.run_workspace_checked
def observed(*args,**kwargs):
    result=original(*args,**kwargs)
    context=result.context
    order=list(context.get('runtime.qualified_exec_order'))
    value={'numeric_result':context.get('result')['value'],'runtime_order':order,
           'runtime_model_count':sum(path.rsplit('.',1)[-1]=='model' for path in order)}
    Path(sys.argv[1]).write_text(json.dumps(value))
    return result
service.run_workspace_checked=observed
raise SystemExit(main(sys.argv[2:]))
'''


def _runtime(project, target):
    output = project.parent / "runtime-values.json"
    if target == "python":
        result = command(project, [output, "run", "--workspace", project.parent / "vibeflow_config.jsonc",
            "--config", project / "configs/model.jsonc", "--input", project.parent / "input.json",
            "--run-root", project.parent / "runs", "--run-id", "composition"], name="run",
            executable=[sys.executable, "-c", PYTHON_RUN])
    else:
        result = cli(project, "build", name="build", extra=["--target", "node", "--profile", "single-esm",
                     "--out-dir", project.parent / "dist"])
        if result["metrics"]["exit_code"] == 0:
            entry = result["payload"]["entry"]
            script = ('import {pathToFileURL} from "node:url";\n'
                      f'const workflow=await import(pathToFileURL({json.dumps(entry)}));\n'
                      'const values=await workflow.runWorkflow({value:3});\n'
                      'console.log(JSON.stringify(values));\n')
            executed = command(project, ["--input-type=module", "--eval", script], name="node-run", executable=["node"])
            result["node_execution"] = executed
            if executed["metrics"]["exit_code"] == 0:
                write(output, {"numeric_result": executed["payload"]["result"]})
            else:
                result["metrics"]["exit_code"] = executed["metrics"]["exit_code"]
                result["status"] = "ERROR"
    values = json.loads(output.read_text()) if output.exists() else {}
    return result, {"runtime_exit_code": result["metrics"]["exit_code"], "runtime_values_written": output.exists(), **values}


def _walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _documents(project):
    architecture = project / "Architecture.jsonc"
    mermaid = project.parent / "composition.mmd"
    svg = project.parent / "composition.svg"
    steps = [cli(project, name, name=name, extra=["--output", output, *flags])
             for name, output, flags in (("export-architecture", architecture, []),
                 ("export-mermaid", mermaid, ["--expand-nodesets"]),
                 ("export-svg", svg, ["--expand-nodesets"]))]
    architecture_text = architecture.read_text() if architecture.exists() else ""
    document = json.loads(architecture_text[architecture_text.index("{"):]) if "{" in architecture_text else {}
    descriptor = document.get("node_types", {}).get("example.model", {})
    tags = descriptor.get("tags", descriptor.get("info", {}).get("tags", []))
    models = [item for item in _walk(document) if item.get("type_used") == "example.model"]
    fills = {item.get("presentation", {}).get("values", {}).get("fill", "") for item in models}
    svg_text = svg.read_text() if svg.exists() else ""
    model_fills = []
    try:
        svg_root = ET.fromstring(svg_text)
        svg_valid = svg_root.tag == "{http://www.w3.org/2000/svg}svg"
        for group in svg_root.iter():
            text = " ".join(" ".join(group.itertext()).split())
            if "node" not in group.attrib.get("class", "").split() or "type_used: example.model " not in text:
                continue
            geometry = [child for child in group if child.tag.rsplit("}", 1)[-1] in {"rect", "polygon", "circle", "ellipse", "path"}]
            for element in geometry:
                styles = {key.strip(): value.strip().removesuffix(" !important").strip()
                          for declaration in element.attrib.get("style", "").split(";") if ":" in declaration
                          for key, value in [declaration.split(":", 1)]}
                model_fills.append(styles.get("fill", element.attrib.get("fill", "")).lower())
    except ET.ParseError:
        svg_valid = False
    metrics = {"diagram_exit_codes": [item["metrics"]["exit_code"] for item in steps],
        "architecture_tags": tags, "architecture_fill": next(iter(fills)) if len(fills) == 1 else "",
        "mermaid_light_blue": mermaid.exists() and "#cceeff" in mermaid.read_text().lower(),
        "svg_valid": svg_valid, "svg_light_blue": "#cceeff" in svg_text.lower() or "rgb(204, 238, 255)" in svg_text,
        "svg_model_count": len(model_fills), "svg_model_fills": model_fills,
        "diagram_files": [str(path) for path in (architecture, mermaid, svg)]}
    return steps, metrics


SOURCE_SCOPE = '''import json,sys
from pathlib import Path
from vibeflow.tooling.application.python.project.declarations import declared_python_registry,collect_workflow_source_context
from vibeflow.tooling.project.workspace_loader import load_workspace_config
from vibeflow.tooling.project.config_loader import load_workspace_config_document
from vibeflow.tooling.project.graph_config import parse_graph_config
root=Path(sys.argv[1]);workspace=load_workspace_config(root.parent/'vibeflow_config.jsonc')
document=load_workspace_config_document(root/'configs/model.jsonc',workspace=workspace)
graph=parse_graph_config(document.data,project_root=root,source_path=root/'configs/model.jsonc')
if sys.argv[2]=='python':
    registry=declared_python_registry(workspace,config_path=root/'configs/model.jsonc')
    sources=collect_workflow_source_context(registry,graph)
    paths=[list(call.call_path) for call in sources.calls if call.type_key=='example.model']
else:
    from vibeflow.targets.javascript.build.rule_session import node_type_calls
    paths=[list(path) for path in node_type_calls(graph).get('example.model',())]
print(json.dumps({'selected_model_paths':paths}))
'''


def _scope(project, spec, validation):
    result = command(project, [str(project), spec["target"]], name="source-scope",
                     executable=[sys.executable, "-c", SOURCE_SCOPE])
    return result["payload"].get("selected_model_paths", []), result


def _domain_metrics(project, spec, validation):
    findings = [item for item in diagnostics(validation["payload"]) if item.get("code", item.get("rule_id")) == spec["domain_code"] and item.get("severity") == "error"]
    paths = set()
    for item in findings:
        details = item.get("details", {})
        paths.update(tuple(path) for path in details.get("call_paths", []))
        paths.update(tuple(call["node"].split("/")) for call in details.get("calls", []))
    return {"domain_definition_ids": sorted({item.get("definition_id", "") for item in findings}),
            "domain_owner_types": sorted({item.get("object_id", "") for item in findings}),
            "domain_call_paths": [list(path) for path in sorted(paths)],
            "domain_source_files": sorted({str(Path(item["source_location"]["path"]).relative_to(project)) for item in findings
                                           if item.get("source_location", {}).get("path")}),
            "domain_findings": findings}


def observe(work_root, spec, toolchain):
    work = Path(work_root) / spec["id"].replace(".", "_")
    example, project = copy_project(work, spec["target"], toolchain=toolchain)
    _gain(project, spec["target"])
    _flow(project, spec)
    _invalid(project, spec)
    if spec["variant"] == "normal":
        documents, document_metrics = _documents(project)
    validation = cli(project, "validate", name="validate")
    paths, scope = _scope(project, spec, validation)
    runtime, metrics = _runtime(project, spec["target"])
    actual = deepcopy(validation)
    actual["metrics"].update(metrics, selected_model_paths=paths, **_domain_metrics(project, spec, validation))
    actual["payload"] = {"validation": validation["payload"], "runtime": runtime["payload"], "source_scope": scope}
    if spec["variant"] == "normal":
        actual["metrics"].update(document_metrics)
        actual["payload"]["documents"] = documents
        if runtime["metrics"]["exit_code"] or any(item["metrics"]["exit_code"] for item in documents):
            actual["status"] = "FAIL"
    result = row(spec["id"], spec["title"], spec["family"], actual, spec["expected"])
    result["notes"] = spec.get("notes", "")
    result["evidence"] = {"project": str(project), "initial": {"value": 3}, "bundle": "example.domain",
                          "composition": spec["form"], "entrypoints": ["validate", "run" if spec["target"] == "python" else "build+node"]}
    return result
