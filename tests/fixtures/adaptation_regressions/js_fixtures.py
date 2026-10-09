"""Fresh public-SDK projects and original CLI evidence for JavaScript cases."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]

COMPILER_IO_RULESET_SOURCE = '''export const compilerIO=defineRuleset({id:"audit.compiler_io",calls:[{id:"native",ruleset_id:"vibeflow.plugin"}],relations:[{source:"$self",target:"native/effects",kind:"overrides",params:{effect_scope:"python_io"}},{source:"$self",target:"native/imports",kind:"overrides",params:{effect_scope:"python_io"}}],entrypoints:{import:["native"],static:["native"],run:[]}});\n'''


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def project(path: Path, toolchain: Path | None) -> Path:
    shutil.copytree(ROOT / "sandbox/javascript/multifile_resources", path,
        ignore=shutil.ignore_patterns("node_modules", "__pycache__", "ARCHITECTURE*", "*.svg", "*.png"))
    if toolchain is None:
        raise ValueError("JavaScript cases require an explicit locked toolchain")
    (path / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    src = path / "src"
    src.mkdir()
    for member in tuple(path.glob("*.ts")):
        member.rename(src / member.name)
    data = json.loads((path / "workflow.jsonc").read_text())
    data["plugins"][0]["source"]["ref"] = "src/plugin.ts"
    write(path / "workflow.jsonc", data)
    settings = json.loads((path / "vibeflow_project.jsonc").read_text())
    settings.pop("architecture", None)
    write(path / "vibeflow_project.jsonc", settings)
    return path


def edit(path: Path, before: str, after: str):
    source = path.read_text()
    if before not in source:
        raise ValueError(f"fixture marker missing in {path}: {before!r}")
    path.write_text(source.replace(before, after), encoding="utf-8")


def config(path: Path, change):
    data = json.loads((path / "workflow.jsonc").read_text())
    change(data)
    write(path / "workflow.jsonc", data)


def cli_args(project: Path, command: str, *extra, config_name="workflow.jsonc"):
    args = [command, "--workspace", str(project / "vibeflow_config.jsonc")]
    if command != "quality-check":
        args += ["--config", str(project / config_name)]
    if command in {"validate", "quality-check", "review-rules", "inspect-resources"}:
        args.append("--json")
    return [*args, *map(str, extra)]


def diagnostic_rows(payload):
    rows = []
    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get("code", value.get("rule_id")), str) and (
                "severity" in value or "source_location" in value or "file" in value):
                if value not in rows:
                    rows.append(value)
            for key, item in value.items():
                if key not in {"expected", "definitions", "resources", "descriptors", "rule_graphs"}:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(payload)
    return rows


def cli_summary(result):
    payload = result.get("payload", {})
    if not payload:
        raw = result.get("stdout", "")
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            payload = {}
    exit_code = result.get("exit_code", result.get("returncode", result.get("metrics", {}).get("exit_code")))
    diagnostics = diagnostic_rows(payload)
    return {"exit_code": exit_code, "status": payload.get("status"), "code": payload.get("code"),
            "diagnostics": diagnostics, "payload": payload,
            "codes": sorted({str(item.get("code", item.get("rule_id"))) for item in diagnostics})}


def check_cli(observed, *, accepted=True, code=None, owner=None, require_status=True):
    failures = []
    expected_exit = 0 if accepted else 1
    if observed.get("exit_code") != expected_exit:
        failures.append(f"exit_code expected {expected_exit}, got {observed.get('exit_code')}")
    if accepted and require_status and observed.get("status") not in {"PASS", "CONCERNS"}:
        failures.append(f"accepted CLI must report PASS/CONCERNS, got {observed.get('status')}")
    if code:
        rows = [item for item in observed.get("diagnostics", ()) if item.get("code", item.get("rule_id")) == code]
        if not rows:
            failures.append(f"missing target diagnostic {code}; observed {observed.get('codes')}")
        if any(item.get("severity") != "error" for item in rows):
            failures.append(f"target {code} severity must be error")
        if any(not item.get("source_location", {}).get("path", item.get("file", "")) for item in rows):
            failures.append(f"target {code} must retain file position")
        if owner and not any(owner == item.get("object_id", item.get("subject_id")) for item in rows):
            failures.append(f"target {code} must belong to {owner}")
    return failures


def native_shape(project: Path, variant: str):
    data = json.loads((project / "workflow.jsonc").read_text())
    if variant == "serial":
        return
    body = deepcopy(data["pipeline"])
    body["outputs"][0]["as"] = "result"
    write(project / "body.jsonc", {"type_key": "audit.body", "display_name": "Body",
        "description": "Native model composition", "rulesets": ["vibeflow.workflow"],
        "requires": [], "provides": [{"key":"result", "type":"number", "display_name":"Result"}],
        "pipeline": body})
    middle = {"id":"stage", "type_used":"audit.body", "display_name":"Stage", "description":"Native Nodeset"}
    data["nodeset_imports"] = [{"path":"body.jsonc"}]
    if variant == "nested":
        outer = deepcopy(body)
        outer["nodes"][1]["type_used"] = "audit.body"
        write(project / "outer.jsonc", {"type_key":"audit.outer", "display_name":"Outer", "description":"Nested native composition",
            "requires":[], "provides":[{"key":"result", "type":"number", "display_name":"Result"}], "pipeline":outer})
        data["nodeset_imports"].append({"path":"outer.jsonc"})
        middle["type_used"] = "audit.outer"
    if variant == "loop":
        body["inputs"] = [{"key":"number", "type":"number", "display_name":"Initial", "required":True}]
        edit(project / "src/node.ts", "contract:{provides:", 'contract:{requires:[{type:"number",cardinality:"exactly_one",display_name:"Input"}],input_semantics:{number:["Incoming value"]},provides:')
        edit(project / "src/node.ts", 'run(){return {result:multiply(library.implementation(2),2)};}', 'run(inputs){return {result:multiply(library.implementation(inputs.number.value),2)};}')
        write(project / "body.jsonc", {"type_key":"audit.body", "display_name":"Body", "description":"Native loop body",
            "requires":[{"type":"number", "cardinality":"exactly_one", "display_name":"Input"}],
            "provides":[{"key":"result", "type":"number", "display_name":"Result"}], "pipeline":body})
        middle.update(type_used="vibeflow.loop.while", requires=[{"type":"number", "cardinality":"exactly_one", "display_name":"Input"}],
            provides=[{"key":"result", "type":"number", "display_name":"Result"}],
            loop={"body":"audit.body", "max_iterations":1, "stop_after":1,
                "carry":[{"from":"number", "as":"number", "update":"result"}], "outputs":[{"from":"result", "as":"result"}]})
        data["pipeline"]["inputs"] = [{**body["inputs"][0], "key":"value"}]
    data["pipeline"]["nodes"] = [data["pipeline"]["nodes"][0], middle, data["pipeline"]["nodes"][-1]]
    data["pipeline"]["edges"] = [["start","stage"],["stage","end"]]
    if variant == "shared":
        body["outputs"] = []
        write(project / "body.jsonc", {"type_key":"audit.body", "display_name":"Body", "description":"Shared native composition",
            "requires":[], "provides":[], "pipeline":body})
        second = {**middle, "id":"again"}
        data["pipeline"]["nodes"].insert(2, second)
        final = {"id":"final", "type_used":"demo.model", "display_name":"Final", "description":"Exports one numerical result"}
        data["pipeline"]["nodes"].insert(3, final)
        data["pipeline"]["edges"] = [["start","stage"],["stage","again"],["again","final"],["final","end"]]
    write(project / "workflow.jsonc", data)


def compiler(project: Path, variant="valid"):
    marker = json.dumps(str(project / "hooks.jsonl"))
    imports = 'import {appendFileSync} from "node:fs";\n'
    factory = f'''compiler(){{appendFileSync({marker},JSON.stringify({{event:"factory"}})+"\\n");return {{
 beforeCompile(payload){{appendFileSync({marker},JSON.stringify({{event:"before",definitions:Object.keys(payload.graph.nodesets||{{}})}})+"\\n");
   const definitions=payload.graph.nodesets||{{}};for(const item of Object.values(definitions)){{if(!item.graph.nodeset_refs.every(id=>id in definitions))throw Error("invalid finite refs");}}
   return {{annotation:{{stage:"before",definitions:Object.keys(definitions)}}}};
 }},
 afterCompile(payload){{appendFileSync({marker},JSON.stringify({{event:"after",order:payload.compiled.order}})+"\\n");return {{annotation:{{stage:"after",order:payload.compiled.order}}}};}},
 dispose(){{appendFileSync({marker},JSON.stringify({{event:"dispose"}})+"\\n");}}
 }};}},'''
    if variant == "mutation":
        factory = factory.replace('return {annotation:{stage:"before",definitions:Object.keys(definitions)}};', 'return {graph:{nodes:[]}};')
    if variant == "void":
        factory = factory.replace('return {annotation:{stage:"before",definitions:Object.keys(definitions)}};', 'return;')
        factory = factory.replace('return {annotation:{stage:"after",order:payload.compiled.order}};', 'return;')
    if variant == "root_and_dispose":
        factory = factory.replace('return {annotation:{stage:"after",order:payload.compiled.order}};', 'throw Error("ROOT_HOOK_FAILURE");')
        factory = factory.replace('event:"dispose"})+"\\n");}', 'event:"dispose"})+"\\n");throw Error("SECONDARY_DISPOSE_FAILURE");}')
    if variant == "dispose":
        factory = factory.replace('event:"dispose"})+"\\n");}', 'event:"dispose"})+"\\n");throw Error("DISPOSE_FAILURE");}')
    source = project / "src/plugin.ts"
    text = source.read_text().replace('runtime(){return lifecycle();},', factory)
    text = text.replace('import {definePlugin,defineCapability,defineDataSchema}', 'import {definePlugin,defineCapability,defineDataSchema,defineRuleset}')
    text = text.replace('export const plugin=', COMPILER_IO_RULESET_SOURCE + 'export const plugin=')
    text = text.replace('resources:[start,model,library,host,session,number]', 'resources:[start,model,library,host,session,number,compilerIO]')
    text = text.replace('rulesets:["vibeflow.plugin"]', 'rulesets:["audit.compiler_io"]')
    source.write_text(imports + text)


def marker_events(project: Path):
    marker = project / "hooks.jsonl"
    return [json.loads(line) for line in marker.read_text().splitlines() if line.strip()] if marker.exists() else []
