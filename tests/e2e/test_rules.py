"""Selected external SDK Rules through CLI diagnostics and their ordinary audit log."""
import json
import sys

import pytest

from .support import ROOT, cli, command, example, findings, write


CALLS=[{"id":"provider","rule_id":"example.number_provider"},{"id":"checker","rule_id":"example.number_checker"}]
REQUIRES={"source":"checker","target":"provider","kind":"requires","bindings":{"numbers":"numbers"}}


def declare(work,language,*,mode="valid",calls=None,relations=None,entrypoints=None):
    """Author a normal Plugin with the public SDK's declarative Rule graph."""
    package=work / "project/plugins/code_plugin"
    extension="py" if language=="python" else "ts"
    options={"mode":{"type":"string"},"value":{"type":"integer"},"marker":{"type":"string"},"source":{"type":"string"}}
    defaults={"mode":mode,"value":3,"marker":str(work / "rule-events.jsonl"),"source":str(package / f"rules/provider.{extension}")}
    resources=[]
    for name,export,output in (("number_provider","check","example.numbers.v1"),
        ("replacement_provider","replacement","example.numbers.v1"),("wrong_provider","resource_5_check","example.wrong.v1")):
        resources.append(("rule",name,{"id":"example."+name,"source":{"kind":"file","ref":f"rules/provider.{extension}","export":export},
            "inputs":{},"outputs":{"numbers":output},"params_schema":options,"params_defaults":defaults}))
    resources.append(("rule","checker",{"id":"example.number_checker","source":{"kind":"file","ref":f"rules/checker.{extension}","export":"check"},
        "inputs":{"numbers":"example.numbers.v1"},"outputs":{"proof":"example.proof.v1"},
        "params_schema":{"marker":{"type":"string"}},"params_defaults":{"marker":defaults["marker"]}}))
    for identifier,selected in (("example.shared_pair",CALLS),("example.nested",[{"id":"pair","ruleset_id":"example.shared_pair"}]),
        ("example.rule_graph",CALLS if calls is None else calls)):
        resources.append(("ruleset",identifier.split(".")[-1],{"id":identifier,"calls":selected,
            "relations":([REQUIRES] if relations is None else relations) if identifier=="example.rule_graph" else [REQUIRES] if identifier=="example.shared_pair" else [],
            "entrypoints":entrypoints or {}}))
    for index,key in enumerate(("example.input","example.output")):
        resources.append(("data_schema",f"schema_{index}",{"type_key":key,"schema":{"type":"number"}}))
    names=[name for _,name,_ in resources]
    if language=="python":
        source="from vibeflow.targets.python.sdk import Plugin,rule,ruleset,data_schema\n"
        source+="\n".join(f"{name}={kind}(**{options!r})" for kind,name,options in resources)
        source+=f"\nplugin=Plugin(id='example.python.rule_graph',resources=[{','.join(names)}])\n"
    else:
        factories={"rule":"defineRule","ruleset":"defineRuleset","data_schema":"defineDataSchema"}
        source='import {definePlugin,defineRule,defineRuleset,defineDataSchema} from "@vibeflow/plugin";\n'
        source+="\n".join(f"const {name}={factories[kind]}({json.dumps(options)});" for kind,name,options in resources)
        source+=f"\nexport const plugin=definePlugin({{id:'example.javascript.rule_graph',resources:[{','.join(names)}]}});\n"
    write(package / f"plugin.{extension}",source)


@pytest.fixture(params=["python","javascript"])
def rule_project(tmp_path,request,toolchain):
    language=request.param
    work=example(tmp_path / "source",language+"/rule_graph",toolchain if language=="javascript" else None)
    return language,work


def audit(work):
    path=work / "rule-events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def validate(work):
    return cli(work,"validate","--workspace",work / "vibeflow_config.jsonc","--config",work / "project/configs/calculate.jsonc","--json",success=False)


@pytest.mark.parametrize("mode,code,total,error",[("valid",0,3,None),("empty",0,0,None),
    ("warning",0,3,"EXAMPLE.PROVIDER.FINDING"),("error",1,3,"EXAMPLE.PROVIDER.FINDING"),
    ("missing",1,None,"RULE.INPUT.UNAVAILABLE"),("wrong_type",1,None,"RULE.INPUT.UNAVAILABLE"),
    ("failed",1,None,"RULE.INPUT.UNAVAILABLE"),("unavailable",1,None,"RULE.INPUT.UNAVAILABLE")])
def test_typed_rule_records_and_unavailable_provider(rule_project,mode,code,total,error):
    language,work=rule_project
    declare(work,language,mode=mode,entrypoints={"static":["checker"]})
    result=validate(work)
    assert result.returncode==code,result.stdout+result.stderr
    checks=[item for item in audit(work) if item["handler"]=="checker"]
    if total is None:assert not checks
    else:assert checks and all(item["total"]==total for item in checks),checks
    if error:
        matches=[item for item in findings(result) if item["code"].startswith(error)]
        assert matches,result.stdout
        assert all(item["severity"]==("warning" if mode=="warning" else "error") for item in matches)


@pytest.mark.parametrize("replace_provider",[False,True])
def test_nested_rule_selections_and_local_replacement(rule_project,replace_provider):
    language,work=rule_project
    relation={"source":"$self","target":"left/pair/provider","kind":"overrides","params":{"value":5}}
    if replace_provider:relation["replace_rule"]="example.replacement_provider"
    declare(work,language,calls=[{"id":name,"ruleset_id":"example.nested"} for name in ("left","right")],relations=[relation])
    result=validate(work)
    assert result.returncode==0,result.stdout
    checks=[item for item in audit(work) if item["handler"]=="checker"]
    assert {item["call"]:item["total"] for item in checks}=={"left/pair/checker":15 if replace_provider else 5,"right/pair/checker":3}


@pytest.mark.parametrize("case,code",[("replacement","RULE.REPLACEMENT.INTERFACE"),("requires","RULE.REQUIRES.CYCLE"),("includes","RULE.INCLUDES.CYCLE"),
    ("overrides","RULE.OVERRIDES.CYCLE"),("conflict","RULE.OVERRIDE.CONFLICT"),("binding","RULE.INPUT.BINDING")])
def test_rule_graph_error_diagnostics(rule_project,case,code):
    language,work=rule_project
    relations=[REQUIRES]
    if case=="replacement":relations.append({"source":"$self","target":"provider","kind":"overrides","replace_rule":"example.wrong_provider"})
    elif case=="requires":relations.append({"source":"provider","target":"checker","kind":"requires"})
    elif case=="overrides":relations += [{"source":"provider","target":"checker","kind":"overrides"},{"source":"checker","target":"provider","kind":"overrides"}]
    elif case=="binding":relations=[{**REQUIRES,"bindings":{"numbers":"missing"}}]
    elif case=="conflict":relations += [{"source":name,"target":"provider","kind":"overrides","params":{"value":value}}
        for name,value in (("left",4),("right",5))]
    calls=CALLS+([{"id":name,"rule_id":"example.number_provider"} for name in ("left","right")] if case=="conflict" else [])
    if case=="includes":calls=[{"id":"again","ruleset_id":"example.rule_graph"}];relations=[]
    declare(work,language,calls=calls,relations=relations)
    result=validate(work)
    assert result.returncode==1 and any(item["code"].startswith(code) and item["severity"]=="error" for item in findings(result)),result.stdout


def test_override_precedence_and_user_rule_export(rule_project):
    language,work=rule_project
    calls=CALLS+[{"id":name,"rule_id":"example.number_provider"} for name in ("general","specific","peer")]
    relations=[REQUIRES,
        {"source":"general","target":"provider","kind":"overrides","params":{"value":7,"mode":"warning"}},
        {"source":"specific","target":"provider","kind":"overrides","params":{"value":5}},
        {"source":"peer","target":"provider","kind":"overrides","params":{"mode":"warning"}},
        {"source":"specific","target":"general","kind":"overrides"}]
    declare(work,language,calls=calls,relations=relations)
    result=validate(work)
    assert result.returncode==0,result.stdout
    assert next(item for item in audit(work) if item["handler"]=="checker")["total"]==5
    exported=cli(work,"review-rules","--workspace",work / "vibeflow_config.jsonc","--config",work / "project/configs/calculate.jsonc",
        "--node","calculate","--json")
    document=json.loads(exported.stdout)
    provider=next(item for item in document["nodes"][0]["plans"][0]["calls"] if item["id"]=="provider")
    assert provider["params"]["value"]==5 and provider["params"]["mode"]=="warning"
    assert provider["parameter_sources"]["value"]=="override:specific"


def test_selected_phase_and_actual_business_execution(rule_project,tmp_path):
    language,work=rule_project
    declare(work,language,entrypoints={"import":["checker"],"static":[],"run":["checker"]})
    assert validate(work).returncode==0
    assert {item["phase"] for item in audit(work)}=={"import"}
    (work / "rule-events.jsonl").unlink()
    if language=="python":
        request=write(tmp_path / "request.json",{"workspace":str(work / "vibeflow_config.jsonc"),"initial":{"value":3}})
        result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","source",work / "project/configs/calculate.jsonc",request,
            tmp_path / "runs",cwd=tmp_path)
        output=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))["outputs"]
        assert {item["phase"] for item in audit(work)}=={"import","run"}
    else:
        built=cli(work,"build","--workspace",work / "vibeflow_config.jsonc","--config",work / "project/configs/calculate.jsonc",
            "--target","node","--profile","single-esm","--out-dir",tmp_path / "bundle")
        request=write(tmp_path / "request.json",{"initial":{"value":3}})
        result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",json.loads(built.stdout)["entry"],request,cwd=tmp_path)
        output=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))["output"]
        assert {item["phase"] for item in audit(work)}=={"import"}
    assert output=={"result":7}
