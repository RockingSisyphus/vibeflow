"""Shared JS syntax remains separate from ownership decisions and public views."""
import json
import os
from pathlib import Path
import shutil

import pytest

from vibeflow.targets.javascript.build.driver_session import DriverScope
from vibeflow.targets.javascript.build.plugin_session import JavascriptPluginSession
from vibeflow.targets.javascript.build.toolchain import run_quality_facts_driver,run_rule_check_driver


@pytest.fixture
def package(tmp_path):
    fallback=Path(__file__).resolve().parents[3]/"sandbox/javascript/minimal/project"
    tools=Path(os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT",fallback))
    if not (tools/"node_modules/typescript").is_dir():pytest.skip("requires pinned JS toolchain")
    root=tmp_path/"package";root.mkdir()
    for name in ("package.json","package-lock.json"):shutil.copy2(tools/name,root/name)
    (root/"node_modules").symlink_to(tools/"node_modules",target_is_directory=True)
    return root


def test_source_analysis_views_keep_current_owners_and_deep_immutability(package):
    source=package/"same.ts";source.write_text("export const value=1;\n")
    rule=package/"check.ts"
    rule.write_text('export function check(context){const file=context.facts.source_files[0];const first=context.sources.ast(file);const second=context.sources.ast(file);return {records:{data:{type_id:"test.owner.v1",value:{ids:context.sources.ownership(file).declared.map(item=>item.id),nodes:context.sources.ownership(file).node_definitions,same:first===second,frozen:Object.isFrozen(first)&&Object.isFrozen(first.children)&&Object.isFrozen(first.children[0]),text:context.sources.text(file)}}}};}\n')
    with JavascriptPluginSession() as session:
        session.open_rule("owners",rule={"id":"test.owners","module":str(rule),"export":"check"},package_root=package)
        for owner in ("left","right"):
            facts={"sources":[{"path":str(source),"text":source.read_text(),"owner":owner}],"source_files":[str(source)],
                "source_owners":[{'node_type': 'vibeflow.node', "path":str(source),"kind":"node","id":owner}],"node_definitions":{owner:{}}}
            value=session.evaluate_rule("owners",context={"facts":facts},inputs={},params={})["records"]["data"]["value"]
            assert value=={"ids":[owner],"nodes":[owner],"same":True,"frozen":True,"text":source.read_text()}


def test_source_snapshot_changes_do_not_reuse_old_ast(package):
    source=package/"same.ts";source.write_text("export const value=1;\n")
    rule=package/"check.ts"
    rule.write_text('export function check(context){const file=context.facts.source_files[0];return {records:{text:{type_id:"test.text.v1",value:{ast:context.sources.ast(file).text,text:context.sources.text(file)}}}};}\n')
    with JavascriptPluginSession() as session:
        session.open_rule("text",rule={"id":"test.text","module":str(rule),"export":"check"},package_root=package)
        for version in (1,2,1):
            text=f"export const value={version};\n"
            value=session.evaluate_rule("text",context={"facts":{"sources":[{"path":str(source),"text":text}],"source_files":[str(source)]}},inputs={},params={})["records"]["text"]["value"]
            assert value=={"ast":text,"text":text}


def test_program_cache_keeps_snapshot_changes_real(package):
    source=package/"same.ts";source.write_text("export const value=1;\n")
    with DriverScope():
        for version in (1,2,1):
            text=f"export const value={version};\n"
            result=run_rule_check_driver({"typecheckFiles":[str(source)],"ruleTopics":[],
                "sourceSnapshots":[{"path":str(source),"text":text}]},package_root=package)
            assert next(item["text"] for item in result.sources if item["path"]==str(source))==text


def test_program_sharing_does_not_share_base_lib_permissions(package):
    source=package/"same.ts";helper=package/"helper.ts"
    source.write_text('import {value} from "./helper.ts";export function run(){return value;}\n')
    helper.write_text('export const value=1;\n')
    owners=[{'node_type': 'vibeflow.node', "path":str(source),"kind":"node","id":"test.node","export":"run"},
        {"path":str(helper),"kind":"base_lib","id":"test.helper","export":"value"}]
    with DriverScope():
        for libraries in ([],["test.helper"],[]):
            from tests.fixtures.support.resource_rules import javascript_references
            findings=javascript_references(package,{"owners":owners,"nodeBaseLibs":{"test.node":libraries}})
            denied=any(item["code"]=="RESOURCE.REFERENCE.UNDECLARED" for item in findings)
            assert denied==(not libraries)


def test_quality_import_lines_follow_actual_factory_and_helpers(package):
    source=package/"plugin.ts"
    source.write_text('import {used} from "./used.ts";\nimport {unused} from "./unused.ts";\nimport {definePlugin} from "@vibeflow/plugin";\nfunction local(){return used;}\nexport const plugin=definePlugin({id:"test",resources:[],compiler(){return {beforeCompile(){return {annotation:{v:local()}};}};}});\n')
    (package/"used.ts").write_text('export const used=1;\n')
    (package/"unused.ts").write_text('export const unused=2;\n')
    with DriverScope():
        result=run_quality_facts_driver({"qualityRoot":str(package),"qualityFiles":[str(source)],
            "qualityImplementations":[{"path":str(source),"kind":"plugin","type_key":"test.compiler","export":"plugin.compiler"}]},package_root=package)
    assert result.implementations[0]["import_lines"]==[1]


@pytest.mark.parametrize("initialization,body,entry_lines,module_lines",[
    ("void value;", "return 6;", [], [1]),
    ("const snapshot=value;", "return 6;", [], [1]),
    ("", "const input:Input={};return 6;", [2], []),
    ("type Local=Input;", "const input:Local={};return 6;", [2], []),
    ("function unused(){return value;}", "return 6;", [], []),
    ('export const unused=defineNode({type_key:"unused",run(){return value;}});', "return 6;", [], []),
    ("function load(){return value;}\nconst snapshot=load();", "return 6;", [], [1]),
    ("const tools={read(){return value;}};tools.read();", "return 6;", [], [1]),
    ("const tools={read(){return value;}};", "return 6;", [], []),
    ("class Holder{constructor(){void value;}};new Holder();", "return 6;", [], [1]),
    ("class Holder{constructor(){void value;}};", "return 6;", [], []),
    ("", 'return import("./helper.ts");', [5], []),
    ("", 'const result=require("./helper.ts");return result;', [5], []),
])
def test_quality_ownership_separates_entry_types_and_real_initialization(package,initialization,body,entry_lines,module_lines):
    source=package/"node.ts"
    source.write_text('import {value} from "./helper.ts";\nimport type {Input} from "./helper.ts";\nimport {defineNode} from "@vibeflow/plugin";\n'+initialization+'\nexport const model=defineNode({type_key:"model",run(){'+body+'}});\n')
    (package/"helper.ts").write_text('export const value=1;export type Input=Record<string,unknown>;\n')
    with DriverScope():
        result=run_quality_facts_driver({"qualityRoot":str(package),"qualityFiles":[str(source)],
            "qualityImplementations":[{'node_type': 'vibeflow.node', "path":str(source),"kind":"node",'id':"model","export":"model.run"}]},package_root=package)
    facts=result.implementations[0]
    assert facts["entry_import_lines"]==entry_lines
    assert facts["module_initialization_import_lines"]==module_lines
    assert facts["import_lines"]==sorted(set(entry_lines+module_lines))


def test_driver_scope_releases_its_owned_process_on_root_error(package):
    source=package/"same.ts";source.write_text('export const value=1;\n')
    scope=DriverScope()
    with pytest.raises(RuntimeError,match="original"):
        with scope:
            run_rule_check_driver({"typecheckFiles":[str(source)],"ruleTopics":[]},package_root=package)
            driver=next(iter(scope.drivers.values()));process=driver.process
            raise RuntimeError("original")
    assert process.poll() is not None
    assert process.stdin.closed and process.stdout.closed and driver.stderr.closed
    assert scope.drivers=={} and scope.rule_sessions=={}


def test_source_sdk_identity_does_not_hide_raw_imports(package):
    from vibeflow.targets.javascript.resources.identity import business_import_sites
    source = package / "plugin.ts"
    source.write_text('import {definePlugin} from "@vibeflow/plugin";export const plugin=definePlugin({id:"example",resources:[]});')
    facts = run_quality_facts_driver({"qualityRoot":str(package),"qualityFiles":[str(source)]},package_root=package)
    sdk = next(site for file in facts.files for site in file["import_sites"] if site["raw_import"] == "@vibeflow/plugin")
    assert sdk["framework_resource"] == "javascript/sdk.d.ts"
    assert Path(sdk["resolved_path"]).is_file()
    assert not list(business_import_sites(facts.files))
