"""Actual JS callable properties and their declared implementation locators agree."""
import json
from pathlib import Path

from .common import run_cli, row
from .js_fixtures import project, config, cli_args, cli_summary, check_cli


CONFLICT = "RESOURCE.IMPLEMENTATION.CONFLICT"
VARIANTS = ("auto", "other_file", "other_symbol", "same_source", "alias", "delayed",
            "path_auto", "path_same_source", "path_alias")
CONTRACT = '{provides:[{key:"result",type:"number",display_name:"Result"}],output_semantics:{result:["Actual result"]}}'


def fixture(root, kind, variant):
    if variant.startswith("path_"):
        variant = variant.removeprefix("path_")
    import shutil
    for name in ("nodes","base_lib","plugins"):
        shutil.rmtree(root/name)
        (root/name).mkdir()
    package = root / "plugins/demo"
    package.mkdir()
    config(root, lambda data: data.update(rulesets=[]))
    source_path = root / {"node":"nodes/identity.ts", "base_lib":"base_lib/identity.ts", "rule":"plugins/demo/identity.ts"}[kind]
    member = {"node": "run", "rule": "check", "base_lib": "implementation"}[kind]
    symbol = {"node": "model", "rule": "policy", "base_lib": "library"}[kind]
    safe = ('export const safe={run(){return {result:7};}};\n' if kind == "node" else
            'export function safeCheck(){return {findings:[]};}\n' if kind == "rule" else
            'export function safeImplementation(){return 7;}\n')
    safe_symbol = {"node": "safe.run", "rule": "safeCheck", "base_lib": "safeImplementation"}[kind]
    source_path.with_name("safe.ts").write_text(safe)
    export = "Alias." + member if variant == "alias" else symbol + "." + member
    ref = str(source_path.with_name("safe.ts") if variant in {"other_file", "delayed"} else source_path)
    if variant in {"other_file", "delayed", "other_symbol"}:
        export = safe_symbol
    locator = {"kind": "file", "ref": ref, "export": export}
    explicit = "" if variant == "auto" else ",implementations:" + json.dumps([
        {"language": "typescript", "source": locator,
         **({} if kind == "rule" else {"targets": ["node", "browser"], "completion": "immediate"})}])
    source = 'import {definePlugin,defineNode,defineRule,defineRuleset,defineBaseLib,defineDataSchema} from "@vibeflow/plugin";\n'
    source += safe if variant == "other_symbol" else ""
    (root / "nodes/start.ts").write_text('import {defineNode} from "@vibeflow/plugin";\nexport const start=defineNode({node_type:"vibeflow.node",id:"demo.start",flow_kind:"terminal",rulesets:[],contract:{},run(){return {};}});\n')
    callable = "" if variant == "delayed" else (
        ',run(){return {result:7};}' if kind == "node" else
        ',check(){return {findings:[]};}' if kind == "rule" else
        ',implementation(){return 7;}')
    resources = ["number"]
    if kind == "node":
        source += 'export const model=defineNode({node_type:"vibeflow.node",id:"demo.model",rulesets:[],contract:' + CONTRACT + explicit + callable + '});\n'
    elif kind == "rule":
        source += 'export const policy=defineRule({id:"audit.policy",scope:"source"' + explicit + callable + '});\n'
        source += 'export const checks=defineRuleset({id:"audit.checks",calls:[{id:"check",rule_id:"audit.policy"}],entrypoints:{static:["check"]}});\n'
        source += 'export const model=defineNode({node_type:"vibeflow.node",id:"demo.model",rulesets:["audit.checks"],contract:' + CONTRACT + ',run(){return {result:7};}});\n'
        resources += ["policy", "checks"]
    else:
        source += 'export const library=defineBaseLib({id:"audit.library",rulesets:[]' + explicit + callable + '});\n'
        # Delayed libraries have no direct property; their native binding is still valid.
        source += 'export const model=defineNode({node_type:"vibeflow.node",id:"demo.model",rulesets:[],base_libs:["audit.library"],contract:' + CONTRACT + ',run(){return {result:7};}});\n'
        resources.append("library")
    if variant == "alias":
        source += 'export const Alias=' + symbol + ';\n'
    if kind != "node":
        model_start = source.index('export const model=')
        model_end = source.index('\n',model_start)+1
        (root / "nodes/model.ts").write_text('import {defineNode} from "@vibeflow/plugin";\n'+source[model_start:model_end])
        source = source[:model_start]+source[model_end:]
    source_path.write_text(source)
    imported = 'import {policy,checks} from "./identity.ts";\n' if kind == "rule" else ''
    plugin = 'import {definePlugin,defineDataSchema} from "@vibeflow/plugin";\n' + imported
    plugin += 'export const number=defineDataSchema({type_key:"number",schema:{type:"number"}});\n'
    plugin += 'export const plugin=definePlugin({id:"demo",resources:[' + ','.join(r for r in resources if r != "library") + ']});\n'
    (package / "plugin.ts").write_text(plugin)


def observe(work: Path, kernel: Path, toolchain: Path | None, renderer: Path | None):
    rows = []
    for kind in ("node", "rule", "base_lib"):
        for variant in VARIANTS:
            identifier = f"js.A01.{kind}.{variant}"
            location = work / identifier
            if variant.startswith("path_"):
                location /= "literal%23#space name"
            root = project(location, toolchain)
            fixture(root, kind, variant)
            observed = cli_summary(run_cli(root, cli_args(root, "validate"), kernel,
                                           name="validate", toolchain=toolchain))
            # A top-level load error describes the command, while its formal
            # diagnostics carry severity and the source declaration position.
            if observed["payload"].get("diagnostics"):
                observed["diagnostics"] = observed["payload"]["diagnostics"]
            rejected = variant in {"other_file", "other_symbol"}
            failures = check_cli(observed, accepted=not rejected,
                                 code=CONFLICT if rejected else None)
            rows.append(row(identifier, "A01", "JS actual callable source authority: " + kind + "/" + variant,
                            {"exit_code": 1 if rejected else 0}, observed, failures, root))
    return rows
