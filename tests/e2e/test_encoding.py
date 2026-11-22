"""UTF-8 user inputs and outputs in deployed applications under native locales."""
import json
import shutil
import sys

import pytest

from .support import ROOT, cli, command, workspace, write


MESSAGE="通知服务：中文输入与输出🙂"


@pytest.mark.parametrize("utf8_mode",["0","1"])
@pytest.mark.parametrize("entry",["cli","application"])
def test_bundle_text_roundtrip_without_source(tmp_path,utf8_mode,entry):
    app=workspace(tmp_path / "source",'''from vibeflow.targets.python.sdk import node
@node(id="text.echo",node_type="vibeflow.node",flow_kind="terminal",rulesets=[],contract={
 "requires":[{"type":"text","cardinality":"exactly_one","display_name":"输入文字"}],
 "input_semantics":{"text":["UTF-8 文字"]},
 "provides":[{"key":"result","type":"text","display_name":"输出文字"}],
 "output_semantics":{"result":["原样返回 UTF-8 文字"]}})
class Echo:
    def run_pure(self, inputs, params):
        return {"result":inputs["text"]["value"]}
''',plugin='''from vibeflow.targets.python.sdk import Plugin,data_schema
plugin=Plugin(id="text",resources=[data_schema(type_key="text",schema={"type":"string"})])
''')
    config=write(app / "configs/文字.jsonc",{"rulesets":[],"plugins":[{"source":{"kind":"file","ref":"plugins/example/plugin.py"}}],
        "pipeline":{"inputs":[{"key":"message","type":"text","required":True,"display_name":"输入"}],
            "nodes":[{"id":"echo","definition_id":"text.echo","display_name":"回声","description":MESSAGE}],
            "outputs":[{"type":"text","as":"result","cardinality":"exactly_one","display_name":"输出"}]}})
    target=tmp_path / "中文 bundle"
    cli(app.parent,"build","--workspace",app.parent / "vibeflow_config.jsonc","--config",config,"--out-dir",target)
    shutil.rmtree(app.parent)
    env={"PYTHONPATH":None,"LC_ALL":"C","PYTHONUTF8":utf8_mode,"PYTHONCOERCECLOCALE":"0",
        "PYTHONWARNDEFAULTENCODING":"1","PYTHONWARNINGS":"error::EncodingWarning"}
    if entry=="cli":
        initial=write(tmp_path / "中文输入.json",{"message":MESSAGE})
        result=command(sys.executable,"-B",target / "run.py","run","--input",initial,"--run-root",tmp_path / "runs",cwd=tmp_path,env=env)
        assert json.loads(result.stdout)["status"] in {"PASS","CONCERNS"}
    else:
        initial=write(tmp_path / "请求.json",{"initial":{"message":MESSAGE}})
        result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",target,initial,
            tmp_path / "runs",cwd=tmp_path,env=env)
        payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
        assert payload["outputs"]=={"result":MESSAGE}
