"""Real resources, ownership, selected domain rules and full-project governance."""
import json
import shutil
import sys

import pytest

from .support import ROOT, cli, command, example, findings, write


@pytest.fixture
def shared(tmp_path):
    source=tmp_path / "source"
    shutil.copytree(ROOT / "sandbox/python/multi_root",source)
    return source


def test_shared_resources_and_private_roots_survive_deployment(shared,tmp_path):
    cli(shared,"quality-check","--workspace",shared / "vibeflow_config.jsonc","--path",shared,"--json")
    targets=[]
    for name,expected in (("desktop",18),("backend",22)):
        target=tmp_path / name
        cli(shared,"build","--workspace",shared / "vibeflow_config.jsonc","--config",shared / f"{name}/configs/main.jsonc",
            "--out-dir",target)
        targets.append((target,expected))
    shutil.rmtree(shared)
    request=write(tmp_path / "request.json",{})
    for target,expected in targets:
        result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",target,request,
            tmp_path / "runs",cwd=tmp_path,env={"PYTHONPATH":None})
        payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
        assert payload["outputs"]=={"result":expected}


def test_local_validation_and_complete_project_inventory_have_distinct_scope(shared):
    write(shared / "backend/configs/broken.jsonc",'{"pipeline":')
    cli(shared,"validate","--workspace",shared / "vibeflow_config.jsonc","--config",shared / "desktop/configs/main.jsonc","--json")
    result=cli(shared,"quality-check","--workspace",shared / "vibeflow_config.jsonc","--path",shared / "desktop","--json",success=False)
    assert result.returncode==1
    matches=[item for item in findings(result) if item["code"]=="PROJECT.USAGE.INCOMPLETE"]
    assert matches and all(item["severity"]=="error" for item in matches),result.stdout
    assert any(item.get("root_id")=="backend" for item in findings(result)),result.stdout


def test_root_rule_parameters_and_explicit_empty_selection(shared):
    rulefile=shared / "desktop/root_rules.jsonc"
    write(rulefile,{"rulesets":[{"rule_id":"vibeflow.root.files"}],"rule_params":{
        "vibeflow.root.files":{"max_file_lines":1}}})
    args=("validate","--workspace",shared / "vibeflow_config.jsonc","--config",shared / "desktop/configs/main.jsonc","--json")
    rejected=cli(shared,*args,success=False)
    assert rejected.returncode==1 and any(item["code"]=="QUALITY.FILE.MAX_LINES" and item["severity"]=="error"
        for item in findings(rejected)),rejected.stdout
    write(rulefile,{"rulesets":[]})
    cli(shared,*args)
    config=shared / "desktop/configs/main.jsonc";data=json.loads(config.read_text(encoding="utf-8"))
    data["pipeline"]["nodes"][0]["definition_id"]="missing.node";write(config,data)
    rejected=cli(shared,*args,success=False)
    assert rejected.returncode==1 and any(item["code"]=="NODE.DEFINITION.UNKNOWN" for item in findings(rejected)),rejected.stdout


@pytest.mark.parametrize("command_name",["validate","quality-check","review","run"])
def test_domain_rule_reaches_real_helper_source_and_all_user_commands(tmp_path,command_name):
    work=example(tmp_path / "source","python/domain_rules")
    app=work / "project"
    write(app / "vibeflow_project.jsonc",{"project_target":"python","architecture":{"documents":[{
        "workflow":"configs/model.jsonc","document":"ARCHITECTURE.jsonc"}]}})
    helper=write(app / "base_lib/domain_helpers/illegal_model.py",'"""An ordinary transform helper."""\ndef model_forward(value):\n    return value + 1\n')
    path=app / "nodes/domain_nodes.py"
    source=path.read_text(encoding="utf-8").replace("from ..base_lib.domain_helpers.arithmetic import scale",
        "from ..base_lib.domain_helpers.arithmetic import scale\nfrom ..base_lib.domain_helpers.illegal_model import model_forward")
    write(path,source.replace('return {"result": value + params["offset"]}',
        'return {"result": model_forward(value) + params["offset"]}'))
    declarations=app / "nodes/code_plugin_declarations.py"
    lines=declarations.read_text(encoding="utf-8").splitlines()
    write(declarations,"\n".join(line[:-1]+",implementation_files=['../base_lib/domain_helpers/illegal_model.py'])"
        if "'id': 'example.transform'" in line and line.endswith(")") else line for line in lines)+"\n")
    args=[command_name,"--workspace",work / "vibeflow_config.jsonc"]
    if command_name=="quality-check":args += ["--path",app,"--json"]
    else:
        args += ["--config",app / "configs/model.jsonc"]
        if command_name=="validate":args += ["--json"]
        elif command_name=="run":args += ["--input",work / "input.json","--run-root",tmp_path / "runs"]
    result=cli(work,*args,success=False)
    matches=[item for item in findings(result) if item["code"]=="EXAMPLE.MODEL.LOCATION"]
    assert result.returncode==1 and matches,result.stdout + result.stderr
    assert all(item["severity"]=="error" for item in matches)
    assert all(item["source_location"]=={"path":str(helper),"line":2,"column":1} for item in matches)


def test_domain_rule_legal_model_counterpart_executes(tmp_path):
    work=example(tmp_path / "source","python/domain_rules")
    request=write(tmp_path / "request.json",{"workspace":str(work / "vibeflow_config.jsonc"),"initial":{"value":3}})
    result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","source",work / "project/configs/model.jsonc",
        request,tmp_path / "runs",cwd=tmp_path)
    payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    assert payload["outputs"]=={"result":7}
