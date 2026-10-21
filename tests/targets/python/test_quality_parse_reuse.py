"""Quality commands share syntax, while workflow review state stays separate."""

import ast
from collections import Counter
import json

from tests.targets.python.test_code_plugins import executable_project, EXECUTABLE, PLUGIN_SOURCE
from vibeflow.targets.python.project.check_session import current_python_check
from vibeflow.targets.python.project.source_closure import collect_python_source_facts
from vibeflow.targets.python.quality.source import PythonSource, analyze_python_source
from vibeflow.tooling.application.cli import main


def test_quality_cli_reuses_syntax_across_workflows_and_project_scan(tmp_path,monkeypatch,capsys):
    plugin_source = PLUGIN_SOURCE.replace('from vibeflow.core.rules import RuleResult',
        'from vibeflow.core.rules import RuleResult\nfrom vibeflow.core.findings import HealthFinding')
    plugin_source += """
@rule(id="demo.config",level="graph",params_schema={"value":{"type":"integer"}},params_defaults={"value":1})
def config_check(context,inputs,params):
    return RuleResult(findings=(HealthFinding(rule_id="TEST.CONFIG",severity="warning",message=str(params["value"])),))
plugin=Plugin(id="demo",resources=[shell,check,rules,config_check])
"""
    workspace, original = executable_project(tmp_path, plugin_source=plugin_source)
    configs = tmp_path / "configs"
    configs.mkdir()
    data = json.loads(original.read_text())
    data["rulesets"] = [{"rule_id":"demo.config","params":{"value":1}}]
    (configs / "first.jsonc").write_text(json.dumps(data))
    data["rulesets"][0]["params"]["value"] = 9
    (configs / "second.jsonc").write_text(json.dumps(data))
    original.unlink()
    parses = Counter()
    parse = ast.parse
    def counted(text,*args,**kwargs):
        filename = str(kwargs.get("filename",args[0] if args else ""))
        if filename.startswith(str(tmp_path)):
            parses[filename] += 1
        return parse(text,*args,**kwargs)
    monkeypatch.setattr(ast,"parse",counted)
    from vibeflow.tooling.application.python.project import core
    environments = []
    loader = core.build_workspace_environment
    def environment(*args,**kwargs):
        result = loader(*args,**kwargs)
        environments.append(result)
        return result
    monkeypatch.setattr(core,"build_workspace_environment",environment)
    assert main(["quality-check","--workspace",str(workspace.path),"--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [next(item["message"] for item in report["warnings"] if item["rule_id"] == "TEST.CONFIG")
            for report in payload["reports"]] == ["1","9"]
    assert parses == {str(tmp_path / "plugins/demo/plugin.py"):1, str(tmp_path / "nodes/steps.py"):1}
    assert len(environments) == 2
    assert all(current_python_check(item.registry) is None for item in environments)
    # A later command owns a fresh syntax cache and independently checks both workflows.
    assert main(["quality-check","--workspace",str(workspace.path),"--json"]) == 0
    capsys.readouterr()
    assert parses == {str(tmp_path / "plugins/demo/plugin.py"):2, str(tmp_path / "nodes/steps.py"):2}


def test_syntax_cache_preserves_error_locations_and_tracks_text_changes(tmp_path,monkeypatch):
    path = tmp_path / "invalid.py"
    path.write_text("def broken(:\n    return 1\n")
    cache, counts = {}, []
    parse = ast.parse
    monkeypatch.setattr(ast,"parse",lambda *args,**kwargs:counts.append(1) or parse(*args,**kwargs))
    facts = collect_python_source_facts(path,project_root=tmp_path,_parse_cache=cache)
    report = analyze_python_source(PythonSource("invalid","invalid.py",str(path),path.read_text()),_parse_cache=cache)
    assert len(counts) == 1
    finding = report.findings[0]
    assert finding.source_location == {"path":str(path),"line":facts[0].parse_line,"column":facts[0].parse_column}
    assert finding.message == facts[0].parse_error
    path.write_text("def fixed():\n    return 1\n")
    changed = analyze_python_source(PythonSource("invalid","invalid.py",str(path),path.read_text()),_parse_cache=cache)
    assert len(counts) == 2 and not changed.findings and changed.file.function_count == 1


def test_shared_syntax_never_shares_import_resolution_between_roots(tmp_path,monkeypatch):
    shared, first, second = (tmp_path/name for name in ("shared","first","second"))
    for path in (shared,first,second):
        path.mkdir()
    entry = shared / "entry.py"
    entry.write_text("import helper\n")
    for root in (first,second):
        (root / "helper.py").write_text("VALUE = 1\n")
    counts = Counter()
    parse = ast.parse
    def counted(text,*args,**kwargs):
        counts[kwargs["filename"]] += 1
        return parse(text,*args,**kwargs)
    monkeypatch.setattr(ast,"parse",counted)
    cache = {}
    left = collect_python_source_facts(entry,project_root=shared,source_roots=(first,),_parse_cache=cache)
    right = collect_python_source_facts(entry,project_root=shared,source_roots=(second,),_parse_cache=cache)
    assert {item.path for item in left} == {str(entry),str(first / "helper.py")}
    assert {item.path for item in right} == {str(entry),str(second / "helper.py")}
    assert counts[str(entry)] == 1 and all(value == 1 for value in counts.values())
