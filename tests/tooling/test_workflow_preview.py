"""Current-operation target facts and offline entry/operation inspection."""
import json
from pathlib import Path
import subprocess

from tests.coordination.test_hosts import python_project
from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export
from vibeflow.tooling.application.python.presentation.preview import python_preview
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def preview_project(root):
    for name in ("caller", "worker"):
        location = root / name
        location.mkdir()
        python_project(location)
    worker_config = root / "worker/workflow.jsonc"
    worker = json.loads(worker_config.read_text())
    worker["pipeline"]["nodes"].append({"id":"alternate", "type_used":"peer.boundary", "display_name":"Other entry", "description":"Not selected by the call"})
    worker["pipeline"]["edges"].append(["alternate","work"])
    worker["pipeline"]["entries"] = {"main":{"start":"start"},"other":{"start":"alternate"}}
    worker["pipeline"]["default_entry"] = "main"
    worker_config.write_text(json.dumps(worker))
    config = root / "caller/workflow.jsonc"
    caller = json.loads(config.read_text())
    caller["workflow_targets"] = {"worker": {"root": "worker", "workflow": "workflow.jsonc",
        "command": ["python", "-m", "vibeflow.coordination", "run-python", "--config", "workflow.jsonc"], "cwd": "../worker"}}
    caller["pipeline"]["nodes"].append({"id": "gui", "type_used": "peer.boundary", "display_name": "GUI entry", "description": "GUI preprocessing"})
    caller["pipeline"]["edges"].append(["gui", "work"])
    caller["pipeline"]["entries"] = {"cli": {"start": "start"}, "gui": {"start": "gui"}}
    caller["pipeline"]["default_entry"] = "cli"
    work = caller["pipeline"]["nodes"][1]
    grant = work["rulesets"][1]["params"]
    grant["operations"] += ["call", "wait"]
    grant["actions"] = [{"operation": "call", "target": "worker", "wait": True},
        {"operation": "wait"}, {"operation": "send"}, {"operation": "receive"}]
    config.write_text(json.dumps(caller))
    plugin = root / "caller/plugin.py"
    source = plugin.read_text().replace('["self","send","receive"]', '["self","send","receive","call","wait"]')
    source = source.replace('        message=api["receive"]({"port":"request"})',
        '        peer=api["call"]({"target":"worker"})\n        api["send"]({"id":peer["id"],"port":"request","payload":{"value":7}})\n        message=api["receive"]({"port":"reply"})\n        api["wait"]({"id":peer["id"]})')
    source = source.replace('        api["send"]({"id":message["sender"],"port":"reply","payload":{"value":value,"self":api["self"]({})["id"]}})\n', '')
    plugin.write_text(source)
    workspace_file = root / "vibeflow_config.jsonc"
    workspace_file.write_text(json.dumps({"roots": [{"id": name, "path": name} for name in ("caller", "worker")]}))
    workspace = load_workspace_config(workspace_file)
    result = load_workspace_graph_for_export(config, workspace=workspace, validate_health=True, _include_presentation=True)
    assert result[4] is None, result[4].to_dict() if result[4] else result[5].to_dict()
    return python_preview(result[6], config=config, workspace=workspace)


def test_preview_reads_target_facts_from_this_operation(tmp_path):
    record = preview_project(tmp_path)
    script = (record.directory / "snapshot.js").read_text()
    payload = json.loads(script[len("VibeFlowPreview.snapshot("):-3])
    assert set(payload["workflow_graphs"]) == {"worker:workflow.jsonc"}
    assert payload["architecture"]["workflow"]["workflow_targets"]["worker"]["identity"] == "worker:workflow.jsonc"
    assert set(payload["architecture"]["workflow"]["entries"]) == {"cli", "gui"}
    actions = payload["architecture"]["call_policies"]['["work"]']["actions"]
    assert actions[0] == {"operation": "call", "target": "worker", "wait": True, "capability": "vibeflow.workflow"}


def test_offline_browser_selects_entries_and_expands_a_workflow(tmp_path):
    import pytest
    from vibeflow.tooling.presentation.mermaid import _find_mmdc, is_mermaid_svg_renderer_available
    if not is_mermaid_svg_renderer_available():
        pytest.skip("browser dependencies are supplied by the full gate")
    record = preview_project(tmp_path)
    browser = Path(__file__).resolve().parents[1] / "fixtures/preview/workflows.cjs"
    result = subprocess.run(["node", str(browser), str(_find_mmdc().resolve()), str(tmp_path / "vibeflow-preview.html")],
        text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_foreign_target_facts_cross_the_cli_boundary_and_missing_targets_are_local(tmp_path):
    from tests.targets.javascript.test_code_plugins import project as javascript_project
    from vibeflow.tooling.presentation.preview.targets import prepare_targets
    caller, worker = tmp_path / "caller", tmp_path / "worker"
    caller.mkdir()
    worker.mkdir()
    javascript_project(worker)
    (caller / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    config = caller / "workflow.jsonc"
    config.write_text('{}')
    workspace_file = tmp_path / "vibeflow_config.jsonc"
    workspace_file.write_text(json.dumps({"roots":[{"id":"caller","path":"caller"},{"id":"worker","path":"worker"}]}))
    workspace = load_workspace_config(workspace_file)
    facts = {"project_target":"python","workflow":{"nodes":[],"workflow_targets":{
        "worker":{"root":"worker","workflow":"workflow.jsonc","command":["node","worker"]},
        "missing":{"root":"worker","workflow":"missing.jsonc","command":["node","missing"]}}},
        "call_policies":{'["call"]':{"actions":[{"capability":"vibeflow.workflow","operation":"call","target":name} for name in ("worker","missing")]}}}
    updated, graphs = prepare_targets(facts,config=config,workspace=workspace)
    assert graphs["worker:workflow.jsonc"]["architecture"]["project_target"] == "javascript"
    assert updated["workflow"]["workflow_targets"]["missing"]["preview_error"]
    assert "identity" not in facts["workflow"]["workflow_targets"]["worker"]


def test_model_defaults_to_the_real_target_entry_and_preserves_cycles_and_empty_definitions(tmp_path):
    script = Path(__file__).resolve().parents[2] / "tools/workflow-viewer/model.js"
    result = subprocess.run(["node","--input-type=module","-e",f'''
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
const context={{window:{{}}}};vm.runInNewContext(fs.readFileSync({json.dumps(str(script))},'utf8'),context);
const model=context.window.VFModel;
const action={{capability:'vibeflow.workflow',operation:'call',target:'peer'}};
const root={{workflow:{{nodes:[{{id:'call'}}],workflow_targets:{{peer:{{identity:'peer:flow'}}}}}},call_policies:{{'["call"]':{{actions:[action]}}}}}};
const peer={{workflow:{{nodes:[{{id:'main'}},{{id:'other'}}],entries:{{main:{{nodes:['main'],inputs:[],outputs:[]}},other:{{nodes:['other'],inputs:[],outputs:[]}}}},default_entry:'main',workflow_targets:{{peer:{{identity:'root:flow'}}}}}},call_policies:{{'["main"]':{{actions:[action]}}}}}};
const all=model.bodies(root,{{'peer:flow':{{architecture:peer,workflow:{{id:'peer:flow'}}}}}},{{id:'root:flow'}});
const first=model.childOptions({{id:'call'}},all.workflow,['call'],all)[0];
assert.equal(first.key,'workflow:peer:flow:entry:main');assert.equal(first.error,'');
const cyclic=model.childOptions({{id:'main'}},all[first.key],['main'],all)[0];assert.equal(cyclic.key,'workflow');assert.equal(cyclic.error,'');
const empty=model.bodies({{workflow:{{nodes:[]}},nodesets:{{empty:{{body:{{nodes:[]}}}}}}}});
assert.match(model.childOptions({{invokes:{{target:'empty'}}}},empty.workflow,['empty'],empty)[0].error,/内部定义不可用/);
'''],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
