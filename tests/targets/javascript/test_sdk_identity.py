"""SDK direct JS code is authoritative without breaking same-object aliases."""
import json
import os
from pathlib import Path

import pytest

from vibeflow.tooling.project.descriptor_loader import DescriptorLoadError, load_workflow_plugins
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def project(tmp_path, kind, export="", other_file=False):
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (tmp_path / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    (tmp_path / "package.json").write_text('{"name":"sdk-identity","type":"module"}')
    (tmp_path / "vibeflow_config.jsonc").write_text('{"roots":[{"id":"p","path":"."}]}')
    (tmp_path / "vibeflow_project.jsonc").write_text('{"project_target":"javascript","javascript":{"package_root":"."}}')
    member = {"node":"run", "rule":"check", "base_lib":"implementation"}[kind]
    options = {"node":'type_key:"actual",contract:{}', "rule":'id:"actual"', "base_lib":'id:"actual"'}[kind]
    factory = {"node":"defineNode", "rule":"defineRule", "base_lib":"defineBaseLib"}[kind]
    if export:
        source = {"kind":"file","ref":str(tmp_path / ("wrong.ts" if other_file else "plugin.ts")), "export":export}
        options += ',implementations:' + json.dumps([{"language":"typescript", "source":source,
            **({} if kind == "rule" else {"targets":["node","browser"],"completion":"immediate"})}])
    source = f'''import {{definePlugin,{factory}}} from "@vibeflow/plugin";
export const actual={factory}({{{options},{member}(){{return {{}};}}}});
export const Alias=actual;
export const other={{ {member}(){{return {{}};}} }};
export const plugin=definePlugin({{id:"example",resources:[actual]}});
'''
    (tmp_path / "plugin.ts").write_text(source)
    (tmp_path / "wrong.ts").write_text(f'export const wrong={{ {member}(){{return {{}};}} }};\n')
    config=tmp_path / "workflow.jsonc"
    config.write_text('{"plugins":[{"source":{"kind":"file","ref":"plugin.ts"}}],"pipeline":{"nodes":[],"edges":[]}}')
    return load_workspace_config(tmp_path / "vibeflow_config.jsonc"), config, member


@pytest.mark.parametrize("kind", ["node","rule","base_lib"])
@pytest.mark.parametrize("export_kind", ["actual","alias"])
def test_direct_metadata_and_alias_canonicalize_to_same_property(tmp_path, kind, export_kind):
    member = {"node":"run", "rule":"check", "base_lib":"implementation"}[kind]
    workspace,config,_=project(tmp_path,kind,("Alias" if export_kind=="alias" else "actual")+"."+member)
    loaded=load_workflow_plugins(workspace,config)
    catalog=getattr(loaded.catalogs,{"node":"nodes","rule":"rules","base_lib":"base_libs"}[kind])
    implementation=catalog.require("actual").implementations[0]
    assert implementation.source.ref==str(tmp_path / "plugin.ts")
    assert implementation.source.export=="actual."+member
    if kind != "rule":
        assert implementation.completion=="immediate"
        assert implementation.targets==("node","browser")


@pytest.mark.parametrize("kind", ["node","rule","base_lib"])
@pytest.mark.parametrize("other_file", [False,True])
def test_different_file_or_property_is_a_structured_declaration_conflict(tmp_path, kind, other_file):
    member = {"node":"run", "rule":"check", "base_lib":"implementation"}[kind]
    workspace,config,_=project(tmp_path,kind,("wrong" if other_file else "other")+"."+member,other_file)
    with pytest.raises(DescriptorLoadError) as captured:
        load_workflow_plugins(workspace,config)
    error=captured.value
    assert error.code=="RESOURCE.IMPLEMENTATION.CONFLICT"
    assert error.details["actual"]=={"path":str(tmp_path/"plugin.ts"),"symbol":"actual."+member}
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
        plugin = root / "plugin.ts"
        plugin.write_text(plugin.read_text().replace(str(plugin), "./plugin.ts"))
    loaded = load_workflow_plugins(workspace, config)
    catalog = getattr(loaded.catalogs, {"node": "nodes", "rule": "rules", "base_lib": "base_libs"}[kind])
    source = catalog.require("actual").implementations[0].source
    assert source.ref == str(root / "plugin.ts")
    assert source.export == "actual." + member


def test_support_file_reference_preserves_literal_characters(tmp_path):
    root = tmp_path / "literal%23#space name"
    root.mkdir()
    workspace, config, _ = project(root, "node")
    helper = root / "helper%23#file.ts"
    helper.write_text("export const value = 7;\n")
    plugin = root / "plugin.ts"
    plugin.write_text(plugin.read_text().replace('type_key:"actual",',
        'type_key:"actual",implementation_files:["./helper%23#file.ts"],'))
    loaded = load_workflow_plugins(workspace, config)
    implementation = loaded.catalogs.nodes.require("actual").implementations[0]
    assert implementation.implementation_files[0].ref == str(helper)
