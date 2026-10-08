"""Public SDK compiler hooks, declaration previews and owned-worker cleanup."""
import json
from pathlib import Path

from .common import run_cli, run_command, run_probe, row
from .js_fixtures import project, compiler, native_shape, marker_events, cli_args, cli_summary, check_cli, edit, config, COMPILER_IO_RULESET_SOURCE


def _build(root, kernel, toolchain, *, target="node", name="build"):
    return run_cli(root, cli_args(root, "build", "--target", target, "--profile", "single-esm",
        "--out-dir", root / "dist"), kernel, name=name, toolchain=toolchain)


def _execution(root, kernel, built, toolchain, *, initial=None):
    entry = built.get("payload", {}).get("entry") if isinstance(built.get("payload"), dict) else None
    if not entry:
        return {"exit_code": None, "number": None}
    script = 'const workflow=await import('+json.dumps(Path(entry).as_uri())+');const value=await workflow.runWorkflow('+json.dumps(initial or {})+');console.log(JSON.stringify(value));'
    result = run_command(root, ["node", "--input-type=module", "--eval", script], kernel,
        name="native-run", toolchain=toolchain)
    return {"exit_code": result["exit_code"], "number": (result.get("payload") or {}).get("number")}


def finite_graph_cases(work, kernel, toolchain):
    rows=[]
    for variant in ("serial", "nodeset", "nested", "shared", "loop"):
        identifier=f"js.A03.compiler.{variant}"
        root=project(work/identifier, toolchain)
        native_shape(root, variant)
        compiler(root)
        built=_build(root,kernel,toolchain)
        observed=cli_summary(built)
        events=marker_events(root)
        observed["hook_events"]=[item["event"] for item in events]
        observed["finite_definitions"]=next((item.get("definitions") for item in events if item["event"]=="before"),None)
        observed["native"]=_execution(root,kernel,built,toolchain,initial={"value":2} if variant=="loop" else {})
        failures=check_cli(observed)
        expected_definitions=[] if variant=="serial" else ["audit.body","audit.outer"] if variant=="nested" else ["audit.body"]
        if observed["hook_events"] != ["factory","before","after","dispose"]:
            failures.append(f"all four hook phases must execute once: {observed['hook_events']}")
        if sorted(observed["finite_definitions"] or []) != expected_definitions:
            failures.append(f"finite declaration table must contain {expected_definitions}")
        if observed["native"] != {"exit_code":0,"number":6}:
            failures.append(f"native workflow result changed: {observed['native']}")
        manifest=Path((built.get("payload") or {}).get("manifest",root/"dist/vibeflow-build.json"))
        if manifest.is_file():
            observed["manifest_path"]=str(manifest)
            annotations=json.loads(manifest.read_text()).get("plugins",{}).get("annotations",[])
            observed["annotation_phases"]=[item.get("stage") for item in annotations]
        else:
            observed["annotation_phases"]=[]
        if observed["annotation_phases"] != ["before","after"]:
            failures.append("native manifest must preserve both accepted compiler annotations")
        rows.append(row(identifier,"A03","Compiler receives a finite native graph and preserves numeric execution",
            {"exit_code":0,"hook_events":["factory","before","after","dispose"],"finite_definitions":expected_definitions,"native":{"exit_code":0,"number":6}},observed,failures,root))
    for variant in ("void","mutation"):
        identifier=f"js.A03.compiler.{variant}"; root=project(work/identifier,toolchain);compiler(root,variant)
        observed=cli_summary(_build(root,kernel,toolchain))
        failures=check_cli(observed,accepted=variant=="void")
        if variant=="mutation" and observed.get("code") != "VF_PLUGIN_HOOK_RESULT":
            failures.append(f"mutation must report VF_PLUGIN_HOOK_RESULT, got {observed.get('code')}")
        observed["hook_events"]=[item["event"] for item in marker_events(root)]
        rows.append(row(identifier,"A03","Existing void results remain legal; compiler graph mutation remains rejected",
            {"exit_code":0 if variant=="void" else 1},observed,failures,root))
    return rows


_OWNED_WORKER_PROBE = r'''
from contextlib import redirect_stdout, redirect_stderr
import io,json,sys
from pathlib import Path
from unittest.mock import patch
from vibeflow.targets.javascript.build.plugin_session import JavascriptPluginSession
from vibeflow.targets.javascript.sdk.loading import _close_definitions
from vibeflow.tooling.application.cli import main
sessions=[]
enter=JavascriptPluginSession.__enter__
def track(self):
    answer=enter(self)
    sessions.append((self,self._process,self._stderr,self._resource_context))
    return answer
stdout,stderr=io.StringIO(),io.StringIO()
try:
    with patch.object(JavascriptPluginSession,"__enter__",track),redirect_stdout(stdout),redirect_stderr(stderr):
        try: code=main(sys.argv[1:])
        except BaseException as error:
            code=1;stderr.write(type(error).__name__+": "+str(error))
    # A formal subprocess runs this same owner release at atexit.  Holding a
    # Session for observations must not be mistaken for a Catalog leak.
    release_error=None
    try: _close_definitions()
    except BaseException as error: release_error={"code":getattr(error,"code",""),"message":str(error)}
    try: payload=json.loads(stdout.getvalue())
    except ValueError: payload={}
    observations=[{"pid":process.pid,"alive":process.poll() is None,
       "stdin_closed":process.stdin.closed,"stdout_closed":process.stdout.closed,
       "stderr_closed":stream.closed,"resource_released":session._resource_context is None,
       "opened":list(session._opened)} for session,process,stream,context in sessions]
    print(json.dumps({"exit_code":code,"payload":payload,"stdout":stdout.getvalue(),"stderr":stderr.getvalue(),
       "owned_workers":observations,"release_error":release_error,"alive_after":sum(item["alive"] for item in observations),
       "handles_released":all(item["stdin_closed"] and item["stderr_closed"] and item["resource_released"] for item in observations)}))
finally:
    # Only processes returned by this probe's own Session.__enter__ are touched.
    for session,process,stream,context in sessions:
        if process.poll() is None:
            if process.stdin and not process.stdin.closed: process.stdin.close()
            try: process.wait(timeout=2)
            except Exception:
                process.terminate()
                try: process.wait(timeout=2)
                except Exception: process.kill();process.wait(timeout=2)
        for handle in (process.stdout,process.stdin,stream):
            if handle and not handle.closed: handle.close()
        if session._resource_context is not None:
            try: context.__exit__(None,None,None)
            finally: session._resource_context=None
        session._opened.clear();session._process=None;session._stderr=None
'''


def cleanup_cases(work,kernel,toolchain):
    rows=[]
    for variant in ("normal","dispose","root_and_dispose","multiple"):
        identifier=f"js.A09.cleanup.{variant}";root=project(work/identifier,toolchain)
        compiler(root,"valid" if variant in {"normal","multiple"} else variant)
        if variant=="multiple":
            marker=json.dumps(str(root/"hooks.jsonl"))
            (root/"src/bad.ts").write_text('import {definePlugin,defineRuleset} from "@vibeflow/plugin";import {appendFileSync} from "node:fs";\n'+COMPILER_IO_RULESET_SOURCE.replace("audit.compiler_io", "audit.bad.compiler_io")+'export const plugin=definePlugin({id:"audit.bad",resources:[compilerIO],rulesets:["audit.bad.compiler_io"],declaration_rulesets:["vibeflow.plugin_declaration"],compiler(){return {dispose(){appendFileSync('+marker+',JSON.stringify({event:"bad-dispose"})+"\\n");throw Error("BAD_DISPOSE_FAILURE");}};}});\n')
            config(root,lambda data:data["plugins"].append({"source":{"kind":"file","ref":"src/bad.ts"}}))
        result=run_probe(root,_OWNED_WORKER_PROBE,kernel,args=cli_args(root,"build","--target","node","--profile","single-esm","--out-dir",root/"dist"),name="owned-cleanup",toolchain=toolchain)
        observed=result.get("payload") or {}; events=marker_events(root)
        observed["hook_events"]=[item["event"] for item in events]
        failures=[]
        if result["exit_code"] != 0 or not observed.get("owned_workers"):
            failures.append("owned-worker probe must return actual tracked worker evidence")
        expected_exit=0 if variant=="normal" else 1
        if observed.get("exit_code")!=expected_exit:failures.append(f"formal build exit must be {expected_exit}")
        if observed.get("alive_after")!=0:failures.append("all owned workers must be stopped after build cleanup")
        if observed.get("handles_released") is not True:failures.append("all owned stdio and materialized resources must be released")
        if variant=="multiple" and "dispose" not in observed["hook_events"]:failures.append("earlier plugin must dispose even when later plugin disposal fails")
        if variant=="root_and_dispose":
            payload=observed.get("payload") or {}; message=payload.get("message",payload.get("error",""))
            if "ROOT_HOOK_FAILURE" not in str(message):failures.append("original hook root failure must remain the primary CLI error")
            if "SECONDARY_DISPOSE_FAILURE" not in json.dumps(payload.get("details",{})):
                failures.append("secondary dispose error must be transported in structured CLI details")
        rows.append(row(identifier,"A09","Failing user disposal releases every owned process and preserves primary errors",
            {"exit_code":expected_exit,"alive_after":0,"handles_released":True},observed,failures,root))
    return rows


def formal_rule_cases(work,kernel,toolchain):
    rows=[]
    for variant,command in (("accepted","validate"),("accepted","build"),("rejected","validate"),("rejected","build"),("preview","review-rules"),("preview","inspect-resources")):
        identifier=f"js.S03.formal.{variant}.{command}";root=project(work/identifier,toolchain);compiler(root)
        path=root/"src/plugin.ts";text=path.read_text(); marker=json.dumps(str(root/"formal-rule.jsonl"))
        rule='export const check=defineRule({id:"audit.plugin_check",check(context){appendFileSync('+marker+',JSON.stringify({subject:context.subject.id})+"\\n");return {findings:'+('[{code:"CASE.PLUGIN.REJECT",reason:"Selected plugin rule rejected lifecycle",severity:"error",file:'+json.dumps(str(path))+',line:1}]' if variant=="rejected" else '[]')+'};}});\nexport const checks=defineRuleset({id:"audit.plugin_checks",calls:[{id:"native",ruleset_id:"audit.compiler_io"},{id:"check",rule_id:"audit.plugin_check"}],entrypoints:{import:["native"],static:["native","check"]}});\n'
        text=text.replace('import {definePlugin,defineCapability,defineDataSchema,defineRuleset}', 'import {definePlugin,defineCapability,defineDataSchema,defineRule,defineRuleset}')
        text=text.replace('export const plugin=',rule+'export const plugin=').replace('resources:[start,model,library,host,session,number,compilerIO]', 'resources:[start,model,library,host,session,number,compilerIO,check,checks]').replace('rulesets:["audit.compiler_io"]','rulesets:["audit.plugin_checks"]')
        path.write_text(text)
        result=_build(root,kernel,toolchain) if command=="build" else run_cli(root,cli_args(root,command),kernel,name=command,toolchain=toolchain)
        observed=cli_summary(result)
        mark=root/"formal-rule.jsonl";observed["rule_executions"]=len(mark.read_text().splitlines()) if mark.exists() else 0
        observed["factory_executions"]=sum(item["event"]=="factory" for item in marker_events(root))
        failures=check_cli(observed,accepted=variant!="rejected",code="CASE.PLUGIN.REJECT" if variant=="rejected" else None,require_status=command!="review-rules")
        expected_rule=0 if variant=="preview" else 1
        expected_factory=1 if variant=="accepted" and command=="build" else 0
        if observed["rule_executions"]!=expected_rule:failures.append(f"selected Rule executes {expected_rule} time(s), observed {observed['rule_executions']}")
        if observed["factory_executions"]!=expected_factory:failures.append(f"factory executes {expected_factory} time(s), observed {observed['factory_executions']}")
        rows.append(row(identifier,"S03","One formal selected-plugin Rule path; previews do not invoke handlers",
            {"exit_code":1 if variant=="rejected" else 0,"rule_executions":expected_rule,"factory_executions":expected_factory},observed,failures,root))
    return rows


def observe(work:Path,kernel:Path,toolchain:Path|None,renderer:Path|None):
    return [*finite_graph_cases(work,kernel,toolchain),*cleanup_cases(work,kernel,toolchain),*formal_rule_cases(work,kernel,toolchain)]
