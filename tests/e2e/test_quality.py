"""User-configured source limits, dependency diagnostics and resource ownership."""
import json
from pathlib import Path

import pytest

from .host_projects import register
from .support import cli, example, findings, write


def project(root,language,toolchain):
    app=root / "app"
    register(app,language)
    if language=="python":
        write(app / "nodes/task.py",'''from vibeflow.targets.python.sdk import node
@node(id="example.task",node_type="vibeflow.node",rulesets=[],contract={})
class Task:
    def run_pure(self, inputs, params):
        return {}
''')
    else:
        write(app / "package.json",{"type":"module","private":True})
        (app / "node_modules").symlink_to(toolchain / "node_modules",target_is_directory=True)
        write(app / "nodes/task.ts",'''import {defineNode} from "@vibeflow/plugin";
export const task=defineNode({id:"example.task",node_type:"vibeflow.node",rulesets:[],contract:{},run(){return {};}});
''')
    config=write(app / "workflow.jsonc",{"rulesets":[],"pipeline":{"nodes":[{
        "id":"task","definition_id":"example.task","display_name":"Task","description":"Check real user source"}]}})
    return app,config


def check(app,config,rule,params):
    write(app / "root_rules.jsonc",{"rulesets":[{"rule_id":rule,"params":params}]})
    result=cli(app,"quality-check","--workspace",app.parent / "vibeflow_config.jsonc","--path",app,"--json",success=False)
    return result,findings(result)


# These are authored examples and independent limits, never measured compiler facts.
@pytest.mark.parametrize("language",["python","javascript"])
def test_file_and_function_quality_policies_with_legal_controls(tmp_path,toolchain,language):
    app,config=project(tmp_path,language,toolchain)
    code='''def measure(a, b, c):
    if a:
        if b:
            return c
    return a

def another():
    return 2

def third():
    return 3

class First: pass
class Second: pass
class Third: pass
''' if language=="python" else '''export function measure(a, b, c) {
  if (a) {
    if (b) return c;
  }
  return a;
}
export function another() { return 2; }
export function third() { return 3; }
export class First {}
export class Second {}
export class Third {}
'''
    source=write(app / ("measures.py" if language=="python" else "measures.ts"),code)
    fields={
        "max_file_lines":("QUALITY.FILE.MAX_LINES","error",1),
        "max_file_bytes":("QUALITY.FILE.MAX_BYTES","error",1),
        "max_functions_per_file":("QUALITY.FILE.TOO_MANY_FUNCTIONS","warning",1),
        "max_classes_per_file":("QUALITY.FILE.TOO_MANY_CLASSES","warning",1),
        "max_public_api_per_file":("QUALITY.FILE.TOO_WIDE_PUBLIC_API","warning",1),
        "max_file_branches":("QUALITY.FILE.TOO_MANY_BRANCHES","warning",1),
        "max_function_lines":("QUALITY.FUNCTION.MAX_LINES","warning",1),
        "max_function_branches":("QUALITY.FUNCTION.TOO_MANY_BRANCHES","warning",1),
        "max_function_nesting":("QUALITY.FUNCTION.TOO_DEEP_NESTING","warning",1),
        "max_function_params":("QUALITY.FUNCTION.TOO_MANY_PARAMS","warning",2),
    }
    permissive={field:10000 for field in fields}
    result,rows=check(app,config,"vibeflow.root.files",{**permissive,"warn_file_lines":10000})
    assert result.returncode==0 and not rows,result.stdout
    strict={field:limit for field,(_,_,limit) in fields.items()}
    result,rows=check(app,config,"vibeflow.root.files",strict)
    assert result.returncode==1,result.stdout
    for field,(code,severity,_) in fields.items():
        matches=[row for row in rows if row["code"]==code and Path(row["source_location"]["path"])==source]
        assert matches,(field,result.stdout)
        assert all(row["severity"]==severity and row["source_location"]["line"]>=1 for row in matches)
    # Three parameters are allowed at three, warned at two; physical byte limits
    # use the actual user file size, independently of AST or compiler metrics.
    for field,limit,code in (("max_function_params",3,"QUALITY.FUNCTION.TOO_MANY_PARAMS"),
        ("max_file_bytes",len(source.read_bytes()),"QUALITY.FILE.MAX_BYTES")):
        result,rows=check(app,config,"vibeflow.root.files",{**permissive,field:limit})
        assert not any(row["code"]==code and row.get("source_location",{}).get("path")==str(source) for row in rows),result.stdout


@pytest.mark.parametrize("language",["python","javascript"])
def test_dependency_chain_cycle_and_repair_are_reported_by_cli(tmp_path,toolchain,language):
    app,config=project(tmp_path,language,toolchain)
    package=app / "ordinary";package.mkdir()
    if language=="python":
        write(package / "__init__.py","")
        a=write(package / "a.py","from .b import value\n")
        b=write(package / "b.py","from .c import value\n")
        c=write(package / "c.py","value=7\n")
    else:
        a=write(package / "a.ts",'export {value} from "./b.ts";\n')
        b=write(package / "b.ts",'export {value} from "./c.ts";\n')
        c=write(package / "c.ts",'export const value=7;\n')
    params={"max_dependency_chain":3,"warn_dependency_chain":10}
    result,rows=check(app,config,"vibeflow.root.dependencies",params)
    assert result.returncode==0 and not rows,result.stdout
    result,rows=check(app,config,"vibeflow.root.dependencies",{**params,"max_dependency_chain":2})
    matches=[row for row in rows if row["code"]=="QUALITY.DEPENDENCY.CHAIN_TOO_DEEP"]
    assert result.returncode==1 and matches,result.stdout
    assert all(row["severity"]=="error" and Path(row["source_location"]["path"]) in {a,b} for row in matches)
    write(c,'from .a import value\n' if language=="python" else 'export {value} from "./a.ts";\n')
    result,rows=check(app,config,"vibeflow.root.dependencies",params)
    assert result.returncode==1 and any(row["code"]=="QUALITY.DEPENDENCY.CYCLE" and row["severity"]=="error" for row in rows),result.stdout
    write(c,'value=7\n' if language=="python" else 'export const value=7;\n')
    result,rows=check(app,config,"vibeflow.root.dependencies",params)
    assert result.returncode==0 and not rows,result.stdout


@pytest.mark.parametrize("language,binding",[("python","class"),("javascript","shorthand"),("javascript","property"),("javascript","method")])
@pytest.mark.parametrize("topic",["complexity","size","call_chain"])
def test_registered_node_limits_are_real_source_diagnostics(tmp_path,toolchain,language,binding,topic):
    app,config=project(tmp_path,language,toolchain)
    contract={"params_schema":{key:{"type":"number"} for key in ("a","b","c")},"params_defaults":{"a":1,"b":2,"c":3}}
    def declare(policy):
        selection=[{"rule_id":"vibeflow.maintainability","params":{"policy":policy}}]
        if language=="python":
            source=write(app / "nodes/task.py",'''from vibeflow.targets.python.sdk import node
@node(id="example.task",node_type="vibeflow.node",rulesets='''+repr(selection)+''',contract='''+repr(contract)+''')
class Task:
    def run_pure(self, inputs, params):
        return self.first(params['a'])
    def first(self, value):
        if value:
            if value > 1:
                return self.second(value)
        return self.second(0)
    def second(self, value):
        return {}
''')
        else:
            source=write(app / "nodes/task.ts",'''import {defineNode} from "@vibeflow/plugin";
export function run(inputs, params) { return first(params.a); }
function first(value) {
  if (value) { if (value > 1) return second(value); }
  return second(0);
}
function second(value) { return {}; }
export const task=defineNode({id:"example.task",node_type:"vibeflow.node",rulesets:'''+json.dumps(selection)+''',contract:'''+json.dumps(contract)+''',run});
''')
        if language=="javascript" and binding!="shorthand":
            text=source.read_text(encoding="utf-8")
            member="run:run" if binding=="property" else "run(inputs,params){return first(params.a);}"
            write(source,text.replace(",run});",","+member+"});"))
        return source
    codes={"complexity":["NODE.MAINTAINABILITY.COMPLEXITY_"+name for name in ("MAX_FUNCTIONS","MAX_BRANCHES","MAX_NESTING_DEPTH","MAX_PARAMS")],
        "size":["NODE.PURITY.SOURCE_TOO_LARGE","NODE.PURITY.SOURCE_BYTES_TOO_LARGE"],
        "call_chain":["NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP"]}[topic]
    policies={"complexity":{"complexity":{name:1 for name in ("max_functions","max_branches","max_nesting_depth","max_params")}},
        "size":{"node_source":{"max_lines":1,"max_bytes":1}},
        "call_chain":{"maintainability":{"warn_call_chain_length":1,"max_call_chain_length":1}}}
    states=("allowed","warning","error","allowed") if topic in {"size","call_chain"} else ("allowed","error","allowed")
    for state in states:
        policy=policies[topic] if state=="error" else {}
        if state=="warning":
            policy={"maintainability":{"warn_call_chain_length":1,"max_call_chain_length":10}} if topic=="call_chain" else {
                "node_source":{"warn_lines":1,"warn_bytes":1}}
        source=declare(policy)
        result=cli(app,"validate","--workspace",app.parent / "vibeflow_config.jsonc","--config",config,"--json",success=False)
        rows=findings(result)
        assert result.returncode==(1 if state=="error" else 0),result.stdout+result.stderr
        expected=[code.replace("TOO_LARGE","NEAR_LIMIT") for code in codes] if state=="warning" and topic=="size" else codes
        for code in expected:
            matches=[row for row in rows if row["code"]==code]
            assert bool(matches)==(state!="allowed"),(code,result.stdout)
            for row in matches:
                assert row["severity"]==state and Path(row["source_location"]["path"])==source and row["source_location"]["line"]>0,row


@pytest.mark.parametrize("language",["python","javascript"])
@pytest.mark.parametrize("topic",["complexity","size"])
def test_library_limits_reach_real_multifile_resource(tmp_path,toolchain,language,topic):
    work=example(tmp_path / "source",language+"/multifile_resources",toolchain if language=="javascript" else None)
    app=work / "project"
    declaration=app / ("base_lib/math_resource.py" if language=="python" else "base_lib/math.ts")
    original=declaration.read_text(encoding="utf-8")
    helper=app / ("base_lib/math_support.py" if language=="python" else "base_lib/math_support.ts")
    write(helper,'''def add(left, right):
    if left:
        if right:
            return left + right
    return left + right
''' if language=="python" else '''export function add(left:number,right:number):number {
  if(left) { if(right) return left+right; }
  return left+right;
}
''')
    policy={"complexity":{"max_functions":0,"max_branches":0,"max_nesting_depth":0}} if topic=="complexity" else {"node_source":{"max_lines":1,"max_bytes":1}}
    codes=["BASE_LIB.COMPLEXITY."+name for name in ("MAX_FUNCTIONS","MAX_BRANCHES","MAX_NESTING_DEPTH")] if topic=="complexity" else ["BASE_LIB.SOURCE.MAX_LINES","BASE_LIB.SOURCE.MAX_BYTES"]
    for denied in (False,True,False):
        selected=[{"rule_id":"vibeflow.maintainability","params":{"policy":policy if denied else {}}}]
        rendered=repr(selected) if language=="python" else json.dumps(selected)
        source=original.replace('["vibeflow.base_lib"]',rendered)
        assert source!=original
        write(declaration,source)
        result=cli(work,"review","--workspace",work / "vibeflow_config.jsonc","--config",app / "configs/workflow.jsonc",success=False)
        rows=findings(result)
        assert result.returncode==(1 if denied else 0),result.stdout
        for code in codes:
            matches=[row for row in rows if row["code"]==code]
            assert bool(matches)==denied,(code,result.stdout)
            assert all(row["severity"]=="error" and Path(row["source_location"]["path"]) in {helper,declaration} for row in matches)


@pytest.mark.parametrize("language",["python","javascript"])
def test_duplicate_advice_disappears_after_real_source_repair(tmp_path,toolchain,language):
    app,config=project(tmp_path,language,toolchain)
    source='''def calculate(value):
    result=value+7
    return result
''' if language=="python" else '''export function calculate(value) {
  const result=value+7;
  return result;
}
'''
    a=write(app / ("first.py" if language=="python" else "first.ts"),source)
    b=write(app / ("second.py" if language=="python" else "second.ts"),source)
    for duplicate in (True,False,True):
        write(b,source if duplicate else source.replace('+7','*9'))
        result,rows=check(app,config,"vibeflow.root.duplicates",{})
        assert result.returncode==0,result.stdout
        matches=[row for row in rows if row["code"]=="QUALITY.DUPLICATE.AST_FINGERPRINT"]
        assert bool(matches)==duplicate,result.stdout
        for row in matches:
            assert row["severity"]=="warning"
            assert {name.split(':')[0] for name in row["details"]["functions"]}=={a.name,b.name},row


@pytest.mark.parametrize("language",["python","javascript"])
def test_resource_permissions_follow_sdk_ownership_not_folder_name(tmp_path,toolchain,language):
    app,config=project(tmp_path,language,toolchain)
    extension="py" if language=="python" else "ts"
    write(app / ("nodes/helper."+extension),'value=7\n' if language=="python" else 'export const value=7;\n')
    ordinary='from .helper import value\n' if language=="python" else 'import {value} from "./helper.ts";\n'
    write(app / ("nodes/ordinary."+extension),ordinary)
    source=app / ("nodes/task."+extension);original=source.read_text(encoding="utf-8")
    for denied in (False,True,False):
        used=original.replace('        return {}','        value\n        return {}') if language=="python" else original.replace('run(){return {};}','run(){void value;return {};}')
        write(source,ordinary+used if denied else original)
        write(app / "root_rules.jsonc",{"rulesets":["vibeflow.root.resource_usage"]})
        result=cli(app,"quality-check","--workspace",app.parent / "vibeflow_config.jsonc","--path",app,"--json",success=False)
        rows=findings(result)
        matches=[row for row in rows if row["code"]=="RESOURCE.REFERENCE.UNDECLARED"]
        assert result.returncode==(1 if denied else 0),result.stdout
        assert bool(matches)==denied,result.stdout
        for row in matches:
            assert row["severity"]=="error" and row["details"]["resource_id"]=="example.task",row
            assert Path(row["source_location"]["path"])==source and row["source_location"]["line"]==1,row


def test_python_node_relations_reject_direct_calls_but_allow_ordinary_helpers(tmp_path):
    from .support import workspace
    app=workspace(tmp_path,'')
    config=write(app / "workflow.jsonc",{"rulesets":[],"pipeline":{"nodes":[{
        "id":"caller","definition_id":"example.caller","display_name":"Caller","description":"Use workflow relations"}]}})
    for denied in (False,True,False):
        source=write(app / "nodes/tasks.py",'''from vibeflow.targets.python.sdk import node
@node(id="example.other",node_type="vibeflow.node",rulesets=[],contract={})
class Other:
    def run_pure(self, inputs, params):
        return {}
class Ordinary:
    def run_pure(self, inputs, params):
        return {}
@node(id="example.caller",node_type="vibeflow.node",rulesets=["vibeflow.process"],contract={})
class Caller:
    def run_pure(self, inputs, params):
        return '''+('Other' if denied else 'Ordinary')+'''().run_pure(inputs,params)
''')
        result=cli(tmp_path,"validate","--workspace",tmp_path / "vibeflow_config.jsonc","--config",config,"--json",success=False)
        matches=[row for row in findings(result) if row["code"]=="NODE.METADATA.NODE_DIRECT_CALL"]
        assert result.returncode==(1 if denied else 0),result.stdout
        assert bool(matches)==denied,result.stdout
        assert all(row["severity"]=="error" and row["source_location"]["path"]==str(source) and row["source_location"]["line"]==12 for row in matches)
