"""Copyable declarations exercise the ordinary SDK on both Targets."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from vibeflow.targets.python.sdk.resources import definition
from vibeflow.core.descriptors import NodeDescriptor


def test_shipped_templates_and_contract_resources_use_normal_sdk(tmp_path, monkeypatch):
    from distribution.build import _copy_coordination_templates
    _copy_coordination_templates(tmp_path)
    root = tmp_path / "kernel/templates/workflow_nodes"
    spec = importlib.util.spec_from_file_location("copied_nodes", root / "nodes.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    nodes = [definition(item).descriptor for item in module.resources
             if isinstance(definition(item).descriptor, NodeDescriptor)]
    assert len(nodes) == 9
    assert {item.presentation["shape"] for item in nodes} >= {"fr-rect", "diamond", "lean-r"}
    sdk = Path(__file__).resolve().parents[2] / "src/vibeflow/targets/javascript/resources/sdk.mjs"
    javascript = (root / "nodes.mjs").read_text().replace('"@vibeflow/plugin"', json.dumps(sdk.as_uri()))
    (root / "nodes.mjs").write_text(javascript)
    result = subprocess.run(["node", "--input-type=module", "-e", f'''
import {{resources,CallAndWaitRun,ReceiveRun,SendRun}} from {json.dumps((root / "nodes.mjs").as_uri())};
const calls=[];
const context={{capabilities:{{"vibeflow.workflow":{{call:async()=>({{id:"worker-id"}}),wait:async r=>({{state:"succeeded",outputs:{{answer:42}}}}),receive:async()=>({{payload:7}}),send:r=>calls.push(r)}}}}}};
const result=await CallAndWaitRun({{}},{{}},context);
const message=await ReceiveRun({{}},{{}},context);
SendRun({{"example.instance":{{value:"worker-id"}},"example.payload":{{value:7}}}},{{}},context);
console.log(JSON.stringify({{count:resources.length,result,message,calls}}));
'''], text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["result"] == {"instance": "worker-id", "result": {"state": "succeeded", "outputs": {"answer": 42}}}
    assert payload["message"] == {"message": {"payload": 7}}
    assert payload["calls"] == [{"id": "worker-id", "payload": 7}]
