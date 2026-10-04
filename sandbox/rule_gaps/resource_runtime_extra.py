"""Runtime-only bundling and preview boundaries with observable resource handlers."""
import json
from pathlib import Path

from resource_support import project,replace,cli,observe
from resource_runtime import execute


def run_cases(work,toolchain):
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
                source='import {defineRule,defineRuleset} from "@vibeflow/plugin";\nimport {writeFileSync} from "node:fs";\n'
                source+='export const audit=defineRule({id:"demo.fs_rule",check(){writeFileSync('+json.dumps(str(rule_marker))+',"checked");return {findings:[]};}});\n'
                source+='export const checks=defineRuleset({id:"demo.fs_checks",calls:[{id:"check",rule_id:"demo.fs_rule"}],entrypoints:{static:["check"]}});\n'
                compiler='compiler(){return {afterCompile(){writeFileSync('+json.dumps(str(compiler_marker))+',"compiled");}};},'
                path.write_text(source+text.replace('runtime(){',compiler+'runtime(){').replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,audit,checks]'))
                replace(root,"node.ts",'rulesets:["vibeflow.process"]','rulesets:["vibeflow.process","demo.fs_checks"]')
            actual=cli(root,"build",name="build",extra=["--target","browser" if browser else "node","--profile","single-esm","--out-dir",root/"dist"])
            expected={"runtime_exit":0,"value":6,"unused_loaded":False}
            if actual["metrics"]["exit_code"]==0:
                entry=actual["payload"]["entry"]
                body='const result=workflow.runWorkflow({});return {value:result.number,unused_loaded:globalThis.__unusedLoaded===true};'
                observed=execute(root,body,browser=True,entry=entry) if browser else execute(root,'const workflow=await import('+json.dumps(Path(entry).as_uri())+');console.log(JSON.stringify(await(async()=>{'+body+'})()));')
                actual["metrics"].update(runtime_exit=observed["metrics"]["exit_code"],**observed["payload"])
                if variant=="check_code_excluded":
                    actual["metrics"].update(rule_executed=rule_marker.exists(),compiler_executed=compiler_marker.exists(),
                        node_fs_in_bundle="node:fs" in Path(entry).read_text())
            if variant=="check_code_excluded":expected.update(rule_executed=True,compiler_executed=True,node_fs_in_bundle=False)
            rows.append(observe(case,"resource-runtime",actual,metrics=expected))
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
