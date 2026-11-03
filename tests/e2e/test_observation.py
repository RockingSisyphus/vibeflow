"""Natural status documents, console logs and browser application status."""
import json
from pathlib import Path

import pytest

from .observation import observe
from .javascript_observation import observe as observe_javascript, write_project
from .support import ROOT, cli, command, serve, write


@pytest.mark.parametrize("case_id",["success","runtime_failure","startup_failure"])
def test_cli_status_console_and_failure_reset(tmp_path,case_id):
    result=observe(tmp_path,case_id)
    assert result["matched"],result


def test_node_status_heartbeat_survives_busy_application(tmp_path,toolchain):
    result=observe_javascript(tmp_path,toolchain)
    assert result["matched"],result


def test_browser_application_displays_normal_status(tmp_path,toolchain,browser_runtime):
    project=write_project(tmp_path,toolchain)
    built=cli(tmp_path,"build","--workspace",tmp_path / "vibeflow_config.jsonc","--config",project / "workflow.jsonc",
        "--target","browser","--profile","single-esm","--out-dir",tmp_path / "web")
    entry=Path(json.loads(built.stdout)["entry"])
    html=write(entry.parent / "index.html",'''<meta charset="utf-8"><button id="run">运行</button><pre id="result"></pre>
<script type="module">
import {runWorkflow} from "./'''+entry.name+'''";
document.querySelector('#run').addEventListener('click',()=>{
 const records=[];
 const value=runWorkflow({value:3},{onStatus:status=>records.push(status)});
 document.querySelector('#result').textContent=JSON.stringify({result:value.result,
  states:records.map(record=>record.state),info:records.at(-1).info});
});
</script>''')
    with serve(html.parent) as url:
        result=command("node",ROOT / "tests/e2e/browser/application.cjs",browser_runtime / "package.json",url+"/index.html",cwd=tmp_path)
    assert json.loads(result.stdout)=={"result":4,"states":["starting","running","succeeded"],
        "info":[{"metrics":{"loss":.125}},{"message":"训练第10轮"}]}
