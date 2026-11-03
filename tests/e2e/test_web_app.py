"""Formal web-app delivery and application-owned browser listener lifecycle."""
import json
import shutil

import pytest

from .support import ROOT, cli, command, example, serve


@pytest.mark.parametrize("kind,config,application,html",[
    ("linear","linear","app.ts","index.template.html"),
    ("messages","browser_message_loop","browser_session_app.ts","browser_session.template.html")])
def test_formal_web_app_user_controls_and_cleanup(tmp_path,toolchain,browser_runtime,kind,config,application,html):
    work=example(tmp_path / "source","javascript/integration",toolchain)
    target=tmp_path / "web"
    cli(work,"build","--workspace",work / "vibeflow_config.jsonc","--config",work / f"project/configs/{config}.jsonc",
        "--target","browser","--profile","web-app","--html",work / "project/web" / html,
        "--app-entry",work / "project/web" / application,"--out-dir",target)
    shutil.rmtree(work)
    with serve(target) as url:
        result=command("node",ROOT / "tests/e2e/browser/web_app.cjs",browser_runtime / "package.json",url+"/index.html",kind,cwd=tmp_path)
    assert json.loads(result.stdout)=={"kind":kind,"errors":[]}
