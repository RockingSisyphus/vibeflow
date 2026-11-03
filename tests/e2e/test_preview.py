"""Normal preview publication and user interaction, without fabricated snapshots."""
import json
import shutil

import pytest

from .cooperation import prepare
from .support import ROOT, cli, command, example, workspace, write


def records(work):
    return [json.loads(path.read_text(encoding="utf-8")) for path in (work / "vibeflow-preview").rglob("record.json")]


def call(name,definition="fixture.work",**fields):
    if fields.get("status")=="planned":fields.update(flow_kind="process",requires=[],provides=[])
    return dict(id=name,definition_id=definition,display_name=name,description="Review "+name,**fields)


def definition(key,behavior,body=None):
    return dict(type_key=key,display_name=key,description="Draft "+key,status="planned",planned_behavior=behavior,
        requires=[],provides=[],rulesets=[],**({"pipeline":{"nodes":body}} if body else {}))


@pytest.mark.parametrize("target",["python","javascript"])
def test_planned_calls_in_actual_review(tmp_path,toolchain,browser_runtime,target):
    if target=="python":
        app=workspace(tmp_path,'''from vibeflow.targets.python.sdk import node
@node(id="fixture.work",node_type="vibeflow.node",rulesets=[],contract={})
class Work:
    def run_pure(self, inputs, params):
        return {}
''')
        work=tmp_path
    else:
        work=example(tmp_path / "source","javascript/minimal",toolchain);app=work / "project"
        write(work / "project_rules.jsonc",{"rulesets":[]});write(app / "root_rules.jsonc",{"rulesets":[]})
        write(app / "nodes/work.mjs",'''import {defineNode} from "@vibeflow/plugin";
export const work=defineNode({id:"fixture.work",node_type:"vibeflow.node",rulesets:[],contract:{},run(){return {};}});
''')
    write(app / "vibeflow_project.jsonc",{"project_target":target,"architecture":{"documents":[{
        "workflow":"configs/planned.jsonc","document":"ARCHITECTURE.jsonc"}]}})
    calls=[call("future",status="planned"),call("first","draft.body"),call("second","draft.body"),
        call("empty","draft.empty"),call("loop","vibeflow.loop.while",requires=[],provides=[],
            loop={"body":"draft.body","max_iterations":1,"stop_after":1}),
        call("override","draft.blocking",status="planned",planned_behavior="transparent")]
    definitions=[definition("draft.body","transparent",[call("child",status="planned")]),
        definition("draft.empty","blocking"),definition("draft.blocking","blocking",[call("work")])]
    imports=[]
    for index,data in enumerate(definitions):
        path=f"nodeset_types/draft{index}.jsonc";write(app / "configs" / path,data);imports.append({"path":path})
    config=write(app / "configs/planned.jsonc",{"rulesets":[],"nodeset_imports":imports,"pipeline":{
        "nodes":calls,"edges":[[a["id"],b["id"]] for a,b in zip(calls,calls[1:])]}})
    cli(work,"review","--workspace",work / "vibeflow_config.jsonc","--config",config)
    ids=[record["id"] for record in records(work)]
    result=command("node",ROOT / "tests/e2e/browser/planned.cjs",browser_runtime / "package.json",
        work / "vibeflow-preview.html",*ids,cwd=tmp_path)
    assert json.loads(result.stdout)["page_errors"]==[]


def test_real_workflow_navigation_preserves_each_reading_position(tmp_path,browser_runtime):
    output=prepare(ROOT / "sandbox/python/workflow_cooperation_math",tmp_path,"python")
    ids={}
    for name in ("b","a","b","c"):
        label="old_b" if name=="b" and "old_b" not in ids else name
        cli(tmp_path,"build","--workspace",tmp_path / "vibeflow_config.jsonc","--config",
            tmp_path / f"project/configs/{name}.jsonc","--out-dir",output / label)
        candidates=[record for record in records(tmp_path) if record["workflow"]["path"]==f"configs/{name}.jsonc"]
        ids[label]=max(candidates,key=lambda record:record["created_at"])["id"]
    assert len(set(ids.values()))==4,ids
    result=command("node",ROOT / "tests/e2e/browser/workflow-reading.cjs",browser_runtime / "package.json",
        tmp_path / "vibeflow-preview.html",json.dumps(ids),cwd=tmp_path)
    assert json.loads(result.stdout)["history"] is True


def test_review_preview_user_controls(tmp_path, browser_runtime):
    source = example(tmp_path / "source", "python/minimal")
    write(source / "project/vibeflow_project.jsonc", {"project_target":"python", "architecture":{
        "documents":[{"workflow":"configs/config_with_imports.jsonc", "document":"ARCHITECTURE.jsonc"}]}})
    cli(source, "review", "--workspace", source / "vibeflow_config.jsonc", "--config",
        source / "project/configs/config_with_imports.jsonc")
    result = command("node", ROOT / "tests/e2e/browser/preview.cjs", browser_runtime / "package.json",
        source / "vibeflow-preview.html", cwd=tmp_path)
    assert json.loads(result.stdout)["errors"] == []



def test_sdk_presentation_reaches_real_workflow_and_resource_cards(tmp_path,browser_runtime):
    source=example(tmp_path / "source","python/presentation")
    cli(source,"review","--workspace",source / "vibeflow_config.jsonc","--config",source / "project/workflow.jsonc")
    result=command("node",ROOT / "tests/e2e/browser/presentation.cjs",browser_runtime / "package.json",
        source / "vibeflow-preview.html",cwd=tmp_path)
    assert json.loads(result.stdout)=={"nodes":True,"resources":True,"independentCalls":True,"errors":[]}
