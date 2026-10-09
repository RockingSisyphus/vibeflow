"""Count real JS analysis constructions in a copied Target resource driver."""
from pathlib import Path

from .common import run_probe, row
from .js_fixtures import project, cli_args


_COUNT_PROBE = r"""
from collections import Counter
from contextlib import contextmanager,redirect_stdout,redirect_stderr
import io,json,sys
from pathlib import Path
from unittest.mock import patch
import vibeflow.targets.javascript.resources as resources
import vibeflow.targets.javascript.build.rule_session as rules
from vibeflow.tooling.application.cli import main
root=Path.cwd(); copied=root.parent/(root.name+"-instrumented-target");copied.mkdir()
for name in resources.RESOURCE_NAMES:(copied/name).write_text(resources.read_text(name))
events_path=root/"analysis-events.jsonl"
driver=copied/"toolchain_driver.mjs";code=driver.read_text()
prefix='''import {appendFileSync as __countAppend,readFileSync as __countRead} from "node:fs";
import {createHash as __countHash} from "node:crypto";
const __eventPath=EVENT_PATH;
let __programKey="";
function __event(value){__countAppend(__eventPath,JSON.stringify({...value,pid:process.pid})+"\\n");}
function __hash(value){return __countHash("sha256").update(JSON.stringify(value)).digest("hex");}
function __text(source){try{return source.text ?? __countRead(source.fileName,"utf8");}catch{return "";}}
__event({event:"driver-loaded"});
'''.replace("EVENT_PATH",json.dumps(str(events_path)))
marker='  let program;\n  let checker;'
injected='''  const __snapshots=new Map((request.sourceSnapshots||[]).map(item=>[path.resolve(item.path),item.text]));
  const __texts=files.map(file=>[file,__snapshots.get(file)??(()=>{try{return __countRead(file,"utf8");}catch{return "";}})()]);
  __programKey=__hash({packageRoot:path.resolve(request.packageRoot),native:!!ts.__native,options:jsonCompilerOptions,files:[...files].sort(),texts:__texts.sort((a,b)=>a[0].localeCompare(b[0]))});
  let program;
  let checker;'''
native='snapshot = api.updateSnapshot({ openProjects: [configPath] });'
classic='program = ts.createProgram({ rootNames: files, options: compilerOptions, host });'
if marker in code:
    code=code.replace(marker,injected)
    if native not in code and classic not in code:raise RuntimeError("analysis instrumentation did not find any real Program constructor")
    code=code.replace(native,'__event({event:"program",key:__programKey,backend:"native"}); '+native)
    code=code.replace(classic,'__event({event:"program",key:__programKey,backend:"classic"}); '+classic)
else:
    helper=copied/"analysis_program.mjs"
    if not helper.is_file():raise RuntimeError("analysis instrumentation lost Program owner module")
    helper_code=helper.read_text()
    helper_marker='  const cached=session?.programs.get(key);'
    if helper_marker not in helper_code:raise RuntimeError("analysis instrumentation lost Program cache marker")
    helper_code=helper_code.replace(helper_marker,injected.split('  let program;')[0]+helper_marker)
    for constructor,backend in (('snapshot=api.updateSnapshot({openProjects:[configPath]});','native'),('program=ts.createProgram({rootNames:files,options,host});','classic')):
        if constructor not in helper_code:raise RuntimeError("analysis instrumentation lost "+backend+" constructor")
        helper_code=helper_code.replace(constructor,'__event({event:"program",key:__programKey,backend:'+json.dumps(backend)+'});'+constructor)
    helper.write_text(prefix.replace('__event({event:"driver-loaded"});','')+helper_code)
for before,after in (
 ('function collectQualityFacts(ts, program, checker, project, sourceFiles, request) {','function collectQualityFacts(ts, program, checker, project, sourceFiles, request) { __event({event:"quality-facts",key:__programKey});'),
 ('function qualityFunctions(ts, sourceFile) {','function qualityFunctions(ts, sourceFile) { __event({event:"functions",key:__hash({path:path.resolve(sourceFile.fileName),text:__text(sourceFile)}),path:sourceFile.fileName});'),
 ('function qualityCallGraph(ts, sourceFile, exportName) {','function qualityCallGraph(ts, sourceFile, exportName) { __event({event:"call-graph",key:__hash({path:path.resolve(sourceFile.fileName),text:__text(sourceFile),exportName:exportName||""}),path:sourceFile.fileName,exportName:exportName||""});')):
    if before not in code:raise RuntimeError("analysis instrumentation lost metric marker: "+before)
    code=code.replace(before,after)
driver.write_text(prefix+code)
@contextmanager
def copied_resources():yield copied
sessions=[];original=rules._RuleSession.__init__
def counted(self,*args,**kwargs):
    sessions.append(1);return original(self,*args,**kwargs)
stdout,stderr=io.StringIO(),io.StringIO()
with patch.object(resources,"materialized_resources",copied_resources),patch.object(rules._RuleSession,"__init__",counted),redirect_stdout(stdout),redirect_stderr(stderr):
    exit_code=main(sys.argv[1:])
try:payload=json.loads(stdout.getvalue())
except ValueError:payload={}
events=[json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
totals=Counter(item["event"] for item in events)
duplicate=lambda event:sum(value-1 for value in Counter(item["key"] for item in events if item["event"]==event).values())
print(json.dumps({"exit_code":exit_code,"status":payload.get("status"),"diagnostics":payload.get("diagnostics",[]),"formal_payload":payload,
  "rule_session_instances":len(sessions),"driver_processes":len({item["pid"] for item in events if item["event"]=="driver-loaded"}),
  "program_constructions":totals["program"],"distinct_program_keys":len({item["key"] for item in events if item["event"]=="program"}),
  "duplicate_program_constructions":duplicate("program"),"quality_fact_extractions":totals["quality-facts"],
  "function_metric_extractions":totals["functions"],"duplicate_function_metrics":duplicate("functions"),
  "call_graph_extractions":totals["call-graph"],"duplicate_call_graphs":duplicate("call-graph"),"events":events,
  "boundary":"Explicit Target createProgram/native updateSnapshot and metric function entries; not TypeScript backend internal parser counts. No timing claim."}))
"""


def counted_case(work,kernel,toolchain,command="validate"):
    identifier="js.S02.analysis."+("one_check_session" if command=="validate" else "quality_check_session")
    root=project(work/identifier,toolchain)
    args=cli_args(root,command)
    if command=="quality-check":args += ["--config",str(root/"workflow.jsonc")]
    result=run_probe(root,_COUNT_PROBE,kernel,args=args,name="counted-"+command,toolchain=toolchain)
    observed=result.get("payload") or {};failures=[]
    if result["exit_code"]!=0 or observed.get("exit_code")!=0 or observed.get("status") not in {"PASS","CONCERNS"}:
        failures.append("counted formal check must complete with its original healthy semantic result")
    if not observed.get("program_constructions") or not observed.get("function_metric_extractions"):
        failures.append("instrumentation must observe actual Program and file metric constructors")
    for field in ("duplicate_program_constructions","duplicate_function_metrics","duplicate_call_graphs"):
        if observed.get(field)!=0:failures.append(f"same immutable analysis identity must be reused: {field}={observed.get(field)}")
    if observed.get("driver_processes")!=1:failures.append("one formal check must use one persistent analysis driver")
    if observed.get("rule_session_instances")!=1:failures.append("one formal check must share one Rule session across its phases")
    return row(identifier,"S02","Share syntax and metrics across topics without skipping Rule decisions",
        {"exit_code":0,"rule_session_instances":1,"driver_processes":1,"duplicate_program_constructions":0,"duplicate_function_metrics":0,"duplicate_call_graphs":0},observed,failures,root)


def observe(work:Path,kernel:Path,toolchain:Path|None,renderer:Path|None):
    return [counted_case(work,kernel,toolchain,command) for command in ("validate","quality-check")]
