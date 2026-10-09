"""Runtime-only bundling and preview boundaries with observable resource handlers."""
import json
from pathlib import Path

from resource_support import project,replace,cli,observe
from resource_runtime import execute


def run_cases(work,toolchain,*,include_previews=True):
    rows=[]
    for browser in (False,True):
        for variant in ("unused_registered","check_code_excluded"):
            case=f"runtime.{'browser' if browser else 'node'}.{variant}";root=project(work/case,toolchain=toolchain)
            if variant=="unused_registered":
                (root/"unreferenced.ts").write_text('globalThis.__unusedLoaded=true;export const unused=9;\n')
                replace(root,"node.ts",'"node_support.ts"','"node_support.ts","unreferenced.ts"')
                replace(root,"node.ts",'rulesets:["vibeflow.process"]','rulesets:[]')
                replace(root,"plugin.ts",'declaration_rulesets:["vibeflow.plugin_declaration"]','declaration_rulesets:[]')
            else:
                rule_marker=root/"rule.marker";compiler_marker=root/"compiler.marker"
                path=root/"plugin.ts";text=path.read_text()
                source='import {defineRule,defineRuleset,defineResource} from "@vibeflow/plugin";\nimport {writeFileSync} from "node:fs";\n'
                source+='export const audit=defineRule({id:"demo.fs_rule",check(){writeFileSync('+json.dumps(str(rule_marker))+',"__vf_rule_check_only__");return {findings:[]};}});\n'
                source+='export const checks=defineRuleset({id:"demo.fs_checks",calls:[{id:"check",rule_id:"demo.fs_rule"}],entrypoints:{static:["check"]}});\n'
                (root/"compiler.ts").write_text('import {writeFileSync} from "node:fs";\n'
                    'export function createCompiler(){return {afterCompile(){writeFileSync('+json.dumps(str(compiler_marker))+',"__vf_compiler_check_only__");}};}\n')
                # The observable compiler marker is explicit filesystem I/O.
                # Give only that resource permission; the runtime stays pure.
                io_rules={"id":"demo.compiler_io", "calls":[{"id":"native","ruleset_id":"vibeflow.plugin"}],
                    "relations":[{"source":"$self","target":"native/"+topic,"kind":"overrides","params":{"effect_scope":"python_io"}} for topic in ("effects","imports")],
                    "entrypoints":{"import":["native"],"static":["native"],"run":[]}}
                compiler={"kind":"plugin","id":"demo.compiler","type":"compiler","targets":["node","browser"],
                    "rulesets":["demo.compiler_io"],"implementations":[{"language":"typescript","targets":["node","browser"],
                    "source":{"kind":"file","ref":"compiler.ts","export":"createCompiler"}}]}
                source+='export const compilerIo=defineRuleset('+json.dumps(io_rules)+');\n'
                source+='export const compilerResource=defineResource('+json.dumps(compiler)+');\n'
                path.write_text(source+text.replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,audit,checks,compilerIo,compilerResource]'))
                replace(root,"node.ts",'rulesets:["vibeflow.process"]','rulesets:["vibeflow.process","demo.fs_checks"]')
            actual=cli(root,"build",name="build",extra=["--target","browser" if browser else "node","--profile","single-esm","--out-dir",root/"dist"])
            expected={"runtime_exit":0,"value":6,"unused_loaded":False}
            if actual["metrics"]["exit_code"]==0:
                entry=actual["payload"]["entry"]
                body='const result=workflow.runWorkflow({});return {value:result.number,unused_loaded:globalThis.__unusedLoaded===true};'
                observed=execute(root,body,browser=True,entry=entry) if browser else execute(root,'const workflow=await import('+json.dumps(Path(entry).as_uri())+');console.log(JSON.stringify(await(async()=>{'+body+'})()));')
                actual["metrics"].update(runtime_exit=observed["metrics"]["exit_code"],**observed["payload"])
                if variant=="check_code_excluded":
                    bundle=Path(entry).read_text()
                    actual["metrics"].update(rule_executed=rule_marker.exists(),compiler_executed=compiler_marker.exists(),
                        rule_check_code_in_bundle="__vf_rule_check_only__" in bundle or rule_marker.name in bundle,
                        compiler_check_code_in_bundle="__vf_compiler_check_only__" in bundle or compiler_marker.name in bundle,
                        node_fs_in_bundle="node:fs" in bundle)
            if variant=="check_code_excluded":
                expected.update(rule_executed=True,compiler_executed=True,
                    rule_check_code_in_bundle=False,compiler_check_code_in_bundle=False)
                if browser:expected["node_fs_in_bundle"]=False
            rows.append(observe(case,"resource-runtime",actual,metrics=expected))
    if not include_previews:return rows
    # Definitions are loaded, but no resource handler or factory runs in preview.
    for command in ("review-rules","inspect-resources"):
        case=f"runtime.preview.{command}";root=project(work/case,toolchain=toolchain)
        marker=root/"invoked.marker";path=root/"plugin.ts"
        text='import {defineRule,defineRuleset} from "@vibeflow/plugin";\nimport {writeFileSync} from "node:fs";\n'+path.read_text()
        text=text.replace('runtime(){return lifecycle();}', 'runtime(){writeFileSync('+json.dumps(str(marker))+',"runtime");return lifecycle();}')
        text+='\nexport const audit=defineRule({id:"demo.preview",check(){writeFileSync('+json.dumps(str(marker))+',"rule");return {findings:[]};}});\nexport const checks=defineRuleset({id:"demo.preview_checks",calls:[{id:"check",rule_id:"demo.preview"}],entrypoints:{static:["check"]}});\n'
        # Declarations must precede the fixed plugin object.
        prefix=text[text.index('\nexport const audit='):];text=prefix+text[:text.index('\nexport const audit=')]
        path.write_text(text.replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,audit,checks]'))
        replace(root,"node.ts",'rulesets:["vibeflow.process"]','rulesets:["demo.preview_checks"]')
        for file,method in (("node.ts","run()"),("host.ts","createHost()"),("math.ts","implementation(value:number):number")):
            source=root/file
            source.write_text('import {writeFileSync} from "node:fs";\n'+source.read_text().replace(method+'{',method+'{writeFileSync('+json.dumps(str(marker))+',"'+file+'");'))
        actual=cli(root,command,name="preview");actual["metrics"]["handler_called"]=marker.exists()
        rows.append(observe(case,"resource-runtime",actual,metrics={"handler_called":False}))
    return rows
