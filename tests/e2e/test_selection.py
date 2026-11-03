"""Default, replaced, empty and nested rule selections emit normal diagnostics."""
from collections import Counter
import json

import pytest

from .support import cli, example


@pytest.mark.parametrize("language",["python","javascript"])
@pytest.mark.parametrize("name",["default","dynamic","empty"])
def test_rule_scopes_and_local_choices(language,name,tmp_path,toolchain):
    work=example(tmp_path / "source",language+"/rule_selection",toolchain if language=="javascript" else None)
    result=cli(work,"validate","--workspace",work / "vibeflow_config.jsonc","--config",work / f"project/configs/{name}.jsonc","--json")
    report=json.loads(result.stdout)
    proofs=[item for item in report["warnings"] if item["rule_id"].startswith("SELECTION.")]
    graphs=[item["details"] for item in proofs if item["rule_id"]=="SELECTION.GRAPH"]
    local_all=[item["details"] for item in proofs if item["rule_id"]=="SELECTION.LOCAL"]
    local=[item for item in local_all if item["phase"]=="static"]
    expected={"default":[(),("left",),("right",),("takeover",)],"dynamic":[(),("takeover",)],"empty":[("takeover",)]}[name]
    assert Counter(tuple(item["entry"]) for item in graphs)==Counter(expected),graphs
    assert all(item["label"]==("selection.child" if item["entry"]==["takeover"] else "selection.whole" if name=="dynamic" else "selection.default") for item in graphs)
    covered=[tuple(graph["path"]) for item in graphs for graph in item["graphs"]]
    assert Counter(covered)==Counter([(),("left",),("right",),("takeover",)] if name!="empty" else [("takeover",)])
    assert all(item["phase"]=="static" and "muted" in item["background_nodes"] for item in graphs)
    assert Counter(tuple(item["path"]) for item in local)==Counter([
        ("direct",),("left","local"),("right","local"),("takeover","local"),("muted","local")])
    assert all(not item["forbidden"] for item in local)
    assert Counter(tuple(item["path"]) for item in local_all if item["phase"]=="import")==Counter([("direct",)])
