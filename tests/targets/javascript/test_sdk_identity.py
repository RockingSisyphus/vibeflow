"""SDK direct JS code is authoritative without breaking same-object aliases."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from vibeflow.tooling.project.resources import ResourcePreparationError, prepare_workflow_resources
from vibeflow.tooling.project.workspace_loader import load_workspace_config


@pytest.mark.parametrize("path", [
    "/root/literal%23#space name/library.ts",
    r"D:\root\literal%23#space name\library.ts",
    r"\\server\share\literal%23#space name\library.ts",
])
@pytest.mark.parametrize("relative", [False, True])
def test_sdk_file_references_preserve_native_paths_and_literal_characters(path, relative):
    sdk = Path(__file__).resolve().parents[3] / "src/vibeflow/targets/javascript/resources/sdk.mjs"
    reference = "./library.ts" if relative else path
    script = f'''
import {{defineBaseLib,definePlugin}} from {json.dumps(sdk.as_uri())};
import assert from 'node:assert/strict';
const path={json.dumps(path)},ref={json.dumps(reference)};
const lib=defineBaseLib({{id:'library',__origin:{{path,symbol:'library'}},
 implementation(){{}},source:{{kind:'file',ref,export:'library.implementation'}},
 implementation_files:['./helper%23#file.ts']}});
const descriptor=definePlugin({{id:'probe',resources:[lib]}}).resources[0].descriptor;
assert.equal(descriptor.implementations[0].source.ref,path);
const index=Math.max(path.lastIndexOf('/'),path.lastIndexOf(String.fromCharCode(92)));
assert.equal(descriptor.implementations[0].implementation_files[0].ref,
 path.slice(0,index+1)+'helper%23#file.ts');
'''
    result = subprocess.run(["node", "--input-type=module", "--eval", script],
                            capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stderr


def declaration_path(root, kind):
    return root / {"node":"nodes/identity.ts", "base_lib":"base_lib/identity.ts", "rule":"plugins/identity/plugin.ts"}[kind]


def project(tmp_path, kind, export="", other_file=False):
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path, "javascript")
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (tmp_path / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    (tmp_path / "package.json").write_text('{"name":"sdk-identity","type":"module"}')
    source_path = declaration_path(tmp_path, kind)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    member = {"node":"run", "rule":"check", "base_lib":"implementation"}[kind]
    options = {"node":'id:"actual",node_type:"vibeflow.node",flow_kind:"terminal",contract:{},rulesets:[]', "rule":'id:"actual"', "base_lib":'id:"actual"'}[kind]
    factory = {"node":"defineNode", "rule":"defineRule", "base_lib":"defineBaseLib"}[kind]
    if export:
        locator = {"kind":"file","ref":str(source_path.with_name("wrong.ts") if other_file else source_path), "export":export}
        options += ',implementations:' + json.dumps([{"language":"typescript", "source":locator,
            **({} if kind == "rule" else {"targets":["node","browser"],"completion":"immediate"})}])
    source = f'''import {{definePlugin,{factory}}} from "@vibeflow/plugin";
export const actual={factory}({{{options},{member}(){{return {{}};}}}});
export const Alias=actual;
export const other={{ {member}(){{return {{}};}} }};
'''
    if kind == "rule":
        source += 'export const plugin=definePlugin({id:"example",resources:[actual]});\n'
    source_path.write_text(source)
    source_path.with_name("wrong.ts").write_text(f'export const wrong={{ {member}(){{return {{}};}} }};\n')
    if kind != "node":
        (tmp_path / "nodes").mkdir(exist_ok=True)
        (tmp_path / "nodes/start.ts").write_text('import {defineNode} from "@vibeflow/plugin";export const start=defineNode({id:"start",node_type:"vibeflow.node",flow_kind:"terminal",rulesets:[],contract:{},run(){return {}}});')
    config=tmp_path / "workflow.jsonc"
    config.write_text(json.dumps({"plugins":[{"source":{"kind":"file","ref":"plugins/identity/plugin.ts"}}] if kind=="rule" else [],
        "rulesets":[], "pipeline":{"nodes":[{"id":"actual","definition_id":"actual","display_name":"Actual","description":"Exercise identity"}] if kind=="node" else [{"id":"start","definition_id":"start","display_name":"Start","description":"Start identity check"}],"edges":[]}}))
    return load_workspace_config(tmp_path.parent / "vibeflow_config.jsonc"), config, member


@pytest.mark.parametrize("kind", ["node","rule","base_lib"])
@pytest.mark.parametrize("export_kind", ["actual","alias"])
def test_direct_metadata_and_alias_canonicalize_to_same_property(tmp_path, kind, export_kind):
    member = {"node":"run", "rule":"check", "base_lib":"implementation"}[kind]
    workspace,config,_=project(tmp_path,kind,("Alias" if export_kind=="alias" else "actual")+"."+member)
    loaded=prepare_workflow_resources(workspace,config)
    catalog=getattr(loaded.catalogs,{"node":"nodes","rule":"rules","base_lib":"base_libs"}[kind])
    implementation=catalog.require("actual").implementations[0]
    assert implementation.source.ref==str(declaration_path(tmp_path, kind))
    assert implementation.source.export=="actual."+member
    if kind != "rule":
        assert implementation.completion=="immediate"
        assert implementation.targets==("node","browser")


@pytest.mark.parametrize("kind", ["node","rule","base_lib"])
@pytest.mark.parametrize("other_file", [False,True])
def test_different_file_or_property_is_a_structured_declaration_conflict(tmp_path, kind, other_file):
    member = {"node":"run", "rule":"check", "base_lib":"implementation"}[kind]
    workspace,config,_=project(tmp_path,kind,("wrong" if other_file else "other")+"."+member,other_file)
    with pytest.raises(ResourcePreparationError) as captured:
        prepare_workflow_resources(workspace,config)
    error=captured.value
    assert error.code=="RESOURCE.IMPLEMENTATION.CONFLICT"
    assert error.details["actual"]=={"path":str(declaration_path(tmp_path, kind)),"symbol":"actual."+member}
    assert error.details["declared"]["export"]==("wrong" if other_file else "other")+"."+member
    assert error.details["location"]["line"]==2


def test_fixed_js_definition_does_not_revalidate_or_reproject_resources(monkeypatch):
    from vibeflow.core.rules import RulesetDescriptor
    from vibeflow.targets.javascript.sdk.loading import JavascriptPluginDefinition
    descriptor=RulesetDescriptor("fixed")
    definition=JavascriptPluginDefinition("fixed",((descriptor,{"path":"plugin.ts","symbol":"rules"}),),{},{},"plugin.ts",{},None)
    monkeypatch.setattr(RulesetDescriptor,"to_dict",lambda _:pytest.fail("not a serialization boundary"))
    first,second=definition.contributions({"value":[1]}),definition.contributions({"value":[2]})
    assert first.resources is second.resources
    assert first.config["value"]==(1,)
    assert second.config["value"]==(2,)
    with pytest.raises(ValueError):
        definition.contributions([])


@pytest.mark.parametrize("kind", ["node", "rule", "base_lib"])
@pytest.mark.parametrize("relative", [False, True])
def test_literal_file_paths_preserve_percent_hash_and_spaces(tmp_path, kind, relative):
    root = tmp_path / "literal%23#space name"
    root.mkdir()
    member = {"node": "run", "rule": "check", "base_lib": "implementation"}[kind]
    workspace, config, _ = project(root, kind, "Alias." + member)
    if relative:
        plugin = declaration_path(root, kind)
        plugin.write_text(plugin.read_text(encoding="utf-8").replace(json.dumps(str(plugin)), json.dumps("./" + plugin.name)))
    loaded = prepare_workflow_resources(workspace, config)
    catalog = getattr(loaded.catalogs, {"node": "nodes", "rule": "rules", "base_lib": "base_libs"}[kind])
    source = catalog.require("actual").implementations[0].source
    assert source.ref == str(declaration_path(root, kind))
    assert source.export == "actual." + member


def test_support_file_reference_preserves_literal_characters(tmp_path):
    root = tmp_path / "literal%23#space name"
    root.mkdir()
    workspace, config, _ = project(root, "node")
    helper = root / "nodes/helper%23#file.ts"
    helper.write_text("export const value = 7;\n")
    plugin = declaration_path(root, "node")
    plugin.write_text(plugin.read_text().replace('id:"actual",',
        'id:"actual",implementation_files:["./helper%23#file.ts"],'))
    loaded = prepare_workflow_resources(workspace, config)
    implementation = loaded.catalogs.nodes.require("actual").implementations[0]
    assert implementation.implementation_files[0].ref == str(helper)


def test_source_load_states_exclude_kernel_sdk_and_keep_same_named_user_sources(tmp_path):
    workspace, config, _ = project(tmp_path, "node")
    directory = tmp_path / "nodes/vibeflow-js-resources-user"
    directory.mkdir()
    helper = directory / "sdk.mjs"
    helper.write_text('export const label = "User SDK helper";\n')
    plugin = declaration_path(tmp_path, "node")
    plugin.write_text('import {label} from "./vibeflow-js-resources-user/sdk.mjs";\n'
        + plugin.read_text().replace('id:"actual",', 'id:"actual",display_name:label,'))
    loaded = prepare_workflow_resources(workspace, config)
    assert dict(loaded.catalogs.source_load_states) == {
        str(plugin): "loaded",
        str(helper): "unknown",
    }
