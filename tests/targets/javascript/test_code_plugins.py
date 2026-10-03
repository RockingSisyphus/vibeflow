"""Real JS/TS SDK contribution, bootstrap, checks and native AOT execution."""
import json
import os
from pathlib import Path
import subprocess
import shutil

import pytest

from vibeflow.tooling.application.cli import main
from vibeflow.tooling.application.rule_review import effective_rule_plans
from vibeflow.tooling.project.workspace_loader import load_workspace_config
from vibeflow.tooling.project.descriptor_loader import load_workflow_plugins


SOURCE = '''import {definePlugin,defineNode,defineRule,defineRuleset,defineDataSchema} from "@vibeflow/plugin";
export const calculation=defineNode({type_key:"demo.calculate",contract:{provides:[{key:"result",type:"number",display_name:"Result"}],output_semantics:{result:["computed value"]}},rulesets:["vibeflow.process","demo.checks"],presentation:{fill:"#add8e6",shape:"rect"},run(inputs,params){return {result:7};}});
export const start=defineNode({type_key:"demo.start",flow_kind:"terminal",contract:{},rulesets:[],run(inputs,params){return {};}});
export const health=defineRule({id:"demo.health",check(context,inputs,params){return {records:{},findings:[]};}});
export const checks=defineRuleset({id:"demo.checks",calls:[{id:"health",rule_id:"demo.health"}],entrypoints:{static:["health"]}});
export const number=defineDataSchema({type_key:"number",schema:{type:"number"}});
export const plugin=definePlugin({id:"demo",resources:[start,calculation,health,checks,number],config_schema:{type:"object",properties:{value:{type:"integer"}},additionalProperties:false},config_defaults:{value:1}});
'''


def project(tmp_path, source=SOURCE, selections=None):
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (tmp_path / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    (tmp_path / "vibeflow_config.jsonc").write_text(json.dumps({"roots":[{"id":"p","path":"."}]}))
    (tmp_path / "vibeflow_project.jsonc").write_text(json.dumps({"project_target":"javascript","javascript":{"package_root":"."}}))
    (tmp_path / "plugin.ts").write_text(source)
    (tmp_path / "package.json").write_text('{"name":"sdk-test","type":"module","private":true}')
    shutil.copy2(Path(__file__).parents[3] / "sandbox/javascript/minimal/project/package-lock.json", tmp_path / "package-lock.json")
    config = tmp_path / "workflow.jsonc"
    config.write_text(json.dumps({"plugins": selections if selections is not None else [{"source":{"kind":"file","ref":"plugin.ts"}}],"rulesets":[],"pipeline":{"nodes":[{"id":"start","type_used":"demo.start","display_name":"Start","description":"Starts the calculation"},{"id":"calculate","type_used":"demo.calculate","display_name":"Calculate","description":"Perform the calculation"}],"edges":[["start","calculate"]],"outputs":[{"type":"number","display_name":"Result","cardinality":"exactly_one"}]}}))
    return load_workspace_config(tmp_path / "vibeflow_config.jsonc"), config


def test_same_file_sdk_node_and_rule_validate_and_execute(tmp_path, capsys):
    workspace, config = project(tmp_path)
    code = main(["validate","--workspace",str(workspace.path),"--config",str(config),"--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0, report
    out = tmp_path / "build"
    code = main(["build","--workspace",str(workspace.path),"--config",str(config),"--target","node","--profile","single-esm","--out-dir",str(out)])
    built = json.loads(capsys.readouterr().out)
    assert code == 0, built
    entry = Path(built["entry"])
    script = f'import {{runWorkflow}} from {json.dumps(entry.as_uri())}; const result=await runWorkflow({{}}); console.log(JSON.stringify(result));'
    result = subprocess.run(["node","--input-type=module","-e",script],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout) == {"number":7}


def test_shorthand_callback_keeps_its_function_and_helpers_in_aot(tmp_path, capsys):
    source = SOURCE.replace('export const calculation=', '''const offset=3;
function add(value){return value+offset;}
function run(inputs,params){return {result:add(4)};}
export const calculation=''').replace('run(inputs,params){return {result:7};}', 'run')
    workspace, config = project(tmp_path, source)
    out = tmp_path / "build"
    assert main(["build", "--workspace", str(workspace.path), "--config", str(config),
                 "--target", "node", "--profile", "single-esm", "--out-dir", str(out)]) == 0
    built = json.loads(capsys.readouterr().out)
    entry = Path(built["entry"])
    script = f'import {{runWorkflow}} from {json.dumps(entry.as_uri())}; console.log(JSON.stringify(runWorkflow({{}})));'
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {"number": 7}


def test_preview_invokes_no_callbacks_or_lifecycle_factory(tmp_path):
    source = SOURCE.replace('return {result:7};','throw Error("business invoked");').replace('return {records:{},findings:[]};','throw Error("Rule invoked");').replace('resources:[start,calculation,health,checks,number],','resources:[start,calculation,health,checks,number],compiler(){throw Error("compiler invoked");},runtime(){throw Error("runtime invoked");},')
    workspace, config = project(tmp_path, source)
    result = effective_rule_plans(config, workspace=workspace)
    assert result["nodes"][1]["rulesets"] == ["vibeflow.process","demo.checks"]
    loaded = load_workflow_plugins(workspace, config)
    assert loaded.catalogs.origins[("nodes","demo.calculate")].line == 2


@pytest.mark.parametrize("selections",[[],[{"enabled":False,"source":{"kind":"file","ref":"plugin.ts"}}],[{"id":"demo","status":"planned","source":{"kind":"file","ref":"plugin.ts"}}]])
def test_unselected_plugin_has_no_bootstrap_effects(tmp_path, selections):
    workspace, config = project(tmp_path,'throw Error("unselected entry loaded");', selections)
    assert not load_workflow_plugins(workspace, config).catalogs.nodes.available()


def test_fixed_resource_definitions_and_parameter_isolation(tmp_path):
    workspace, config = project(tmp_path)
    first = load_workflow_plugins(workspace,config)
    data = json.loads(config.read_text());data["plugins"][0]["config"]={"value":9};config.write_text(json.dumps(data))
    second = load_workflow_plugins(workspace,config)
    assert first.catalogs.nodes.to_dict() == second.catalogs.nodes.to_dict()
    assert first.catalogs.plugin_settings["demo"]["value"] == 1
    assert second.catalogs.plugin_settings["demo"]["value"] == 9


def test_definition_import_does_not_select_resource(tmp_path):
    workspace, config = project(tmp_path, SOURCE.replace('resources:[start,calculation,health,checks,number]', 'resources:[start,health,checks,number]'))
    assert "demo.calculate" not in load_workflow_plugins(workspace,config).catalogs.nodes.available()


def test_trusted_bootstrap_and_rule_use_the_same_function_binding(tmp_path, capsys):
    marker = tmp_path / "events.txt"
    source = 'import {appendFileSync} from "node:fs";\n' + SOURCE.replace(
        'rulesets:["vibeflow.process","demo.checks"]', 'rulesets:["demo.checks"]')
    source = source.replace('export const calculation=', f'appendFileSync({json.dumps(str(marker))},"bootstrap\\n");\nexport const calculation=')
    source = source.replace('return {records:{},findings:[]};', f'appendFileSync({json.dumps(str(marker))},"check\\n"); return {{records:{{}},findings:[]}};')
    workspace, config = project(tmp_path, source)
    assert main(["validate","--workspace",str(workspace.path),"--config",str(config),"--json"]) == 0
    capsys.readouterr()
    assert marker.read_text().splitlines() == ["bootstrap", "check"]


def test_browser_execution_does_not_bundle_node_only_rule_code(tmp_path, capsys):
    source = 'import {readFileSync} from "node:fs";\n' + SOURCE.replace(
        'return {records:{},findings:[]};', f'const text=readFileSync({json.dumps(str(tmp_path / "package.json"))},"utf8"); return {{records:{{}},findings:text ? [] : []}};')
    workspace, config = project(tmp_path, source)
    assert main(["build","--workspace",str(workspace.path),"--config",str(config),"--target","browser","--profile","single-esm","--out-dir",str(tmp_path / "build")]) == 0
    built = json.loads(capsys.readouterr().out)
    entry = Path(built["entry"])
    text = entry.read_text()
    assert "readFileSync" not in text and "node:fs" not in text
    assert "demo.health" not in text
    result = subprocess.run(["node","--input-type=module","-e",f'import {{runWorkflow}} from {json.dumps(entry.as_uri())}; console.log(JSON.stringify(runWorkflow({{}})));'],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout) == {"number":7}


def test_code_sdk_browser_artifact_in_real_chromium(tmp_path, capsys):
    renderer = os.environ.get("VIBEFLOW_MERMAID_RENDERER_ROOT")
    if not renderer:
        pytest.skip("full verification supplies the locked Puppeteer runtime")
    from sandbox.javascript.integration.sandbox_support import run_browser
    source = 'import {readFileSync} from "node:fs";\n' + SOURCE.replace(
        'return {records:{},findings:[]};',
        f'readFileSync({json.dumps(str(tmp_path / "package.json"))},"utf8"); return {{records:{{}},findings:[]}};')
    workspace, config = project(tmp_path,source)
    assert main(["build","--config",str(config),"--workspace",str(workspace.path),
                 "--target","browser","--profile","single-esm","--out-dir",str(tmp_path/"web")]) == 0
    built=json.loads(capsys.readouterr().out)
    web=Path(built["entry"]).parent
    (web/"index.html").write_text(f'''<button id="run">Run</button><output id="output"></output>
<script type="module">
import {{runWorkflow}} from "./{Path(built["entry"]).name}";
document.querySelector("#run").addEventListener("click",()=>{{
  document.querySelector("#output").textContent=String(runWorkflow({{}}).number);
}});
</script>''')
    assert run_browser(web,puppeteer_root=Path(renderer),expected="7") == {"before":"","after":"7"}


def test_same_file_rule_effects_do_not_grant_node_permissions(tmp_path, capsys):
    source = SOURCE.replace('return {records:{},findings:[]};', 'console.log("rule context"); return {records:{},findings:[]};')
    workspace, config = project(tmp_path, source)
    assert main(["validate","--workspace",str(workspace.path),"--config",str(config),"--json"]) == 0
    capsys.readouterr()
    (tmp_path / "plugin.ts").write_text(source.replace('return {result:7};', 'console.log("node effect"); return {result:7};'))
    assert main(["validate","--workspace",str(workspace.path),"--config",str(config),"--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert any(item["code"] == "VF_BASE_LIB_HOST_IO" for item in report["diagnostics"])


def test_colocated_import_is_bound_by_symbol_when_node_shadows_its_name(tmp_path, capsys):
    source = 'import {readFileSync} from "node:fs";\n' + SOURCE.replace(
        'return {records:{},findings:[]};', f'readFileSync({json.dumps(str(tmp_path/"package.json"))},"utf8"); return {{findings:[]}};')
    source = source.replace('return {result:7};', 'const readFileSync=()=>7; return {result:readFileSync()};')
    workspace,config=project(tmp_path,source)
    assert main(["validate","--workspace",str(workspace.path),"--config",str(config),"--json"]) == 0, capsys.readouterr().out


def test_sdk_runtime_factories_create_and_dispose_independent_instances(tmp_path, capsys):
    factory = '''runtime(context){
      let calls=0;
      return {beforeRun(){calls++;},afterRun(){
        if(calls!==1 || context.config.value!==1 || !Object.isFrozen(context.config)) throw Error("shared runtime instance");
      },dispose(){if(calls!==1) throw Error("invalid disposal");}};
    },'''
    workspace,config=project(tmp_path,SOURCE.replace('resources:[start,calculation,health,checks,number],',factory+'resources:[start,calculation,health,checks,number],'))
    assert main(["build","--config",str(config),"--workspace",str(workspace.path),"--target","node","--profile","single-esm","--out-dir",str(tmp_path/"dist")]) == 0, capsys.readouterr().out
    built=json.loads(capsys.readouterr().out)
    script=f'import {{runWorkflow}} from {json.dumps(Path(built["entry"]).as_uri())}; console.log(JSON.stringify([runWorkflow({{}}),runWorkflow({{}})]));'
    result=subprocess.run(["node","--input-type=module","-e",script],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==[{"number":7},{"number":7}]


@pytest.mark.parametrize("kind",["module","package"])
def test_installed_package_explicit_source_loads_fixed_sdk_export(tmp_path,kind):
    workspace,config=project(tmp_path,selections=[{"source":{"kind":kind,"ref":"./installed"}}])
    installed=tmp_path/"installed";installed.mkdir()
    (installed/"package.json").write_text('{"type":"module","main":"plugin.js"}')
    (installed/"plugin.js").write_text(SOURCE)
    loaded=load_workflow_plugins(workspace,config)
    assert loaded.catalogs.nodes.available()==("demo.calculate","demo.start")
    assert loaded.catalogs.origins[("nodes","demo.calculate")].path==str(installed/"plugin.js")


@pytest.mark.parametrize("kind",["module","package"])
def test_installed_esm_package_resolves_its_import_export(tmp_path, kind):
    workspace, config = project(tmp_path, selections=[{"source":{"kind":kind,"ref":"demo-plugin"}}])
    modules = tmp_path / "node_modules"
    dependencies = modules.resolve()
    modules.unlink()
    modules.mkdir()
    for item in dependencies.iterdir():
        (modules / item.name).symlink_to(item, target_is_directory=item.is_dir())
    installed = modules / "demo-plugin"
    installed.mkdir()
    (installed / "package.json").write_text('{"name":"demo-plugin","type":"module","exports":{"import":"./plugin.js"}}')
    (installed / "plugin.js").write_text(SOURCE)
    loaded = load_workflow_plugins(workspace, config)
    assert loaded.catalogs.nodes.available() == ("demo.calculate", "demo.start")
    assert loaded.catalogs.origins[("nodes", "demo.calculate")].path == str(installed / "plugin.js")


def test_sdk_capability_and_inline_host_use_the_native_protocol(tmp_path,capsys):
    source=SOURCE.replace('defineDataSchema}', 'defineDataSchema,defineCapability,defineHostExtension}')
    source=source.replace('rulesets:["vibeflow.process","demo.checks"]','rulesets:[],capabilities:[{id:"demo.clock",operations:["now"]}]')
    source=source.replace('run(inputs,params){return {result:7};}', 'run(inputs,params,context){return {result:context.capabilities["demo.clock"].now(6)};}')
    source=source.replace('export const plugin=', '''export const clock=defineCapability({id:"demo.clock",targets:["node","browser"],operations:{now:{input_type:"number",output_type:"number",completion:"immediate"}}});
export const host=defineHostExtension({id:"demo.host",targets:["node","browser"],provides:["demo.clock"],createHost(context){return {capabilities:{"demo.clock":{now(value){return value+1;}}},start(){},stop(){}};}});
export const plugin=''')
    source=source.replace('resources:[start,calculation,health,checks,number]', 'resources:[start,calculation,health,checks,number,clock,host]')
    workspace,config=project(tmp_path,source)
    data=json.loads(config.read_text());data["host_extensions"]=[{"id":"demo.host"}];config.write_text(json.dumps(data))
    assert main(["build","--config",str(config),"--workspace",str(workspace.path),"--target","node","--profile","single-esm","--out-dir",str(tmp_path/"dist")]) == 0, capsys.readouterr().out
    built=json.loads(capsys.readouterr().out)
    result=subprocess.run(["node","--input-type=module","-e",f'import {{createWorkflowHost}} from {json.dumps(Path(built["entry"]).as_uri())}; const host=createWorkflowHost(); await host.start(); console.log(JSON.stringify(host.runWorkflow({{}}))); await host.stop();'],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)=={"number":7}


def test_sdk_library_and_rule_in_one_file_keep_separate_effect_scopes(tmp_path,capsys):
    source=SOURCE.replace('defineDataSchema}', 'defineDataSchema,defineBaseLib}')
    source=source.replace('rulesets:["vibeflow.process","demo.checks"]', 'rulesets:["vibeflow.process","demo.checks"],base_libs:["demo.math"]')
    source=source.replace('return {result:7};', 'return {result:math.implementation()};')
    source=source.replace('export const plugin=', 'export const math=defineBaseLib({id:"demo.math",rulesets:["vibeflow.base_lib"],implementation(){return 7;}});\nexport const plugin=')
    source=source.replace('return {records:{},findings:[]};','console.log("rule context"); return {findings:[]};')
    source=source.replace('resources:[start,calculation,health,checks,number]', 'resources:[start,calculation,health,checks,number,math]')
    workspace,config=project(tmp_path,source)
    assert main(["validate","--config",str(config),"--workspace",str(workspace.path),"--json"]) == 0, capsys.readouterr().out
    capsys.readouterr()
    (tmp_path/"plugin.ts").write_text(source.replace('implementation(){return 7;}','implementation(){console.log("library effect"); return 7;}'))
    assert main(["validate","--config",str(config),"--workspace",str(workspace.path),"--json"]) == 1
    report=json.loads(capsys.readouterr().out)
    assert any(item["code"]=="VF_BASE_LIB_HOST_IO" for item in report["diagnostics"])
