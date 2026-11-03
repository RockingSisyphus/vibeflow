"""Effect and lexical-scope examples checked as ordinary SDK projects.

Case files contain user source and independent diagnostic expectations. Several
files with one policy share a validation command; filenames identify failures.
"""
import json
from pathlib import Path

import pytest

from .support import cli, findings, workspace, write


CASES = Path(__file__).with_name("cases")
GROUPS = [(path.stem, group) for path in sorted(CASES.glob("source_*.json"))
          for group in json.loads(path.read_text(encoding="utf-8"))]


@pytest.mark.parametrize("family,group", GROUPS, ids=[f"{family}-{group['subject']}-{group['scope']}-{index}"
    for index, (family, group) in enumerate(GROUPS)])
def test_source_policy_matrix(tmp_path, family, group):
    app = workspace(tmp_path, "")
    # Ordinary user packages used by the dynamic-namespace input examples.
    for package in ("__vibeflow_local__", "example_package"):
        write(app / package / "__init__.py", "tools = object()\n")
    declarations = ["from vibeflow.targets.python.sdk import node"]
    resources = ["from vibeflow.targets.python.sdk import Plugin,ruleset,base_lib,lifecycle",
        "policy=ruleset(id='example.effects',calls=[{'id':'effects','rule_id':'vibeflow.no_side_effects',"
        f"'params':{{'effect_scope':{group['scope']!r},'policy':{group.get('policy', {})!r}}}}}],"
        "entrypoints={'import':[],'static':['effects'],'run':['effects']})"]
    contributed, nodes = ["policy"], []
    input_policy = any(case.get("rule") == "vibeflow.input_writes" for case in group["cases"])
    if input_policy:
        resources[1] = resources[1].replace("vibeflow.no_side_effects", "vibeflow.input_writes").replace(
            f"'params':{{'effect_scope':{group['scope']!r},'policy':{group.get('policy', {})!r}}}", "'params':{}")
    rule_id = "vibeflow.input_writes" if input_policy else "vibeflow.no_side_effects"
    expected = {}
    for index, case in enumerate(group["cases"]):
        symbol = f"case_{index}"
        relative = f"base_lib/{symbol}.py"
        source = case["source"]
        for name, source in case.get("files", {}).items():
            write(app / f"base_lib/{symbol}_{name}", source)
        source = case["source"]
        for name in case.get("files", {}):
            source = source.replace("base_lib." + Path(name).stem, "base_lib." + symbol + "_" + Path(name).stem)
        write(app / relative, source)
        expected[str((app / relative).resolve())] = case
        kind = group["subject"]
        if kind == "node":
            declarations.append(f"{symbol}=node(id='example.{symbol}',node_type='vibeflow.node',"
                f"source={{'kind':'file','ref':{relative!r},'export':'Task'}},rulesets=['example.effects'],contract={{}})")
            nodes.append({"id":symbol,"definition_id":f"example.{symbol}", "display_name":symbol,"description":case["name"]})
        else:
            factory = "base_lib" if kind == "base_lib" else "lifecycle"
            options = "" if kind == "base_lib" else ",type='runtime'"
            export = case.get("export", "caller" if family == "source_helpers" else "task") if kind == "plugin" else ""
            resources.append(f"{symbol}={factory}(id='example.{symbol}',source={{'kind':'file','ref':{str(app / relative)!r},'export':{export!r}}},"
                f"rulesets=['example.effects']{options})")
            contributed.append(symbol)
    if not nodes:
        entry = ""
        if group["subject"] == "base_lib":
            entry = "\n".join(f"import base_lib.case_{index}" for index in range(len(group["cases"]))) + "\n"
        write(app / "nodes/entry.py", entry + "class Task:\n    def run_pure(self, inputs, params):\n        return {}\n")
        declarations.append("task=node(id='example.task',node_type='vibeflow.node',rulesets=[],contract={},"
            "source={'kind':'file','ref':'nodes/entry.py','export':'Task'})")
        nodes.append({"id":"task","definition_id":"example.task","display_name":"Task","description":"Select resources"})
    resources.append(f"plugin=Plugin(id='example',resources=[{','.join(contributed)}])")
    write(app / "nodes/tasks.py", "\n".join(declarations) + "\n")
    write(app / "plugins/example/plugin.py", "\n".join(resources) + "\n")
    config = write(app / "configs/main.jsonc", {"rulesets":[],"plugins":[{
        "source":{"kind":"file","ref":"plugins/example/plugin.py"}}],"pipeline":{"nodes":nodes,
        "edges":[[a["id"],b["id"]] for a,b in zip(nodes,nodes[1:])]}})
    result = cli(tmp_path, "validate", "--workspace", tmp_path / "vibeflow_config.jsonc", "--config", config,
        "--json", success=False)
    report = findings(result)
    unexpected = [item for item in report if item["severity"] == "error" and
        item.get("definition_id") != rule_id]
    assert not unexpected, result.stdout + result.stderr
    for path, case in expected.items():
        selected = [item for item in report if item.get("definition_id") == rule_id
            and item.get("source_location", {}).get("path") == path]
        if "contains" in case:
            selected = [item for item in selected if case["contains"] in item["message"]]
        assert bool(selected) == case["denied"], (family, group["subject"], group["scope"], case, selected, result.stdout)
        for item in selected:
            assert item["severity"] == "error"
            assert item["source_location"]["line"] > 0
            assert item["source_location"].get("column", 1) > 0
    assert result.returncode == (1 if any(item["severity"] == "error" for item in report) else 0), result.stdout


@pytest.mark.parametrize("expression,denied", [
    ("(sys.argv, [sys for sys in ()])", True),
    ("[sys.argv for sys in ()]", False),
])
def test_source_scope_diagnostic_and_shadowing_control(tmp_path, expression, denied):
    app = workspace(tmp_path, '''import sys
from vibeflow.targets.python.sdk import node
@node(id="example.task", node_type="vibeflow.node", rulesets=["vibeflow.process"], contract={})
class Task:
    def run_pure(self, inputs, params):
        value = ''' + expression + '''
        return {}
''')
    config = write(app / "configs/main.jsonc", {"rulesets":[], "pipeline":{"nodes":[{
        "id":"task", "definition_id":"example.task", "display_name":"Task", "description":"Scope check"}]}})
    result = cli(tmp_path, "validate", "--workspace", tmp_path / "vibeflow_config.jsonc",
        "--config", config, "--json", success=False)
    matches = [item for item in findings(result) if item["code"] == "NODE.EFFECT.CALL_FORBIDDEN" and "sys.argv" in item["message"]]
    assert bool(matches) == denied, result.stdout + result.stderr
    assert result.returncode == (1 if denied else 0), result.stdout + result.stderr
    if denied:
        assert matches[0]["severity"] == "error"
        assert Path(matches[0]["source_location"]["path"]).name == "tasks.py"
        assert matches[0]["source_location"]["line"] == 6

