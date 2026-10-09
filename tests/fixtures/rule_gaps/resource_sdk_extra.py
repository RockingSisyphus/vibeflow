"""Independent lifecycle and rule modules declared by the public code SDKs."""
from resource_support import project, cli, replace, observe, config


def run_cases(work,toolchain):
    rows=[]
    for delayed in (False,True):
        case=f"rules.python.lifecycle.{'delayed' if delayed else 'decorated'}"
        root=project(work/case,"python",toolchain)
        header='from vibeflow.targets.python.sdk import lifecycle\nfrom plugin_support import Runtime\n'
        decorator='@lifecycle(id="demo.runtime",type="runtime",implementation_files=["plugin_support.py"],rulesets=["vibeflow.plugin"],presentation={"fill":"#abcdef","shape":"cyl"})\n'
        (root/"runtime_resource.py").write_text(header+('' if delayed else decorator)+'def create_runtime(context):\n    return Runtime()\n')
        text=(root/"plugin.py").read_text().replace('from plugin_support import Runtime','from runtime_resource import create_runtime' if not delayed else 'from vibeflow.targets.python.sdk import lifecycle')
        text=text.replace('def create_runtime(context):\n    return Runtime()\n', '')
        if delayed:
            text=text.replace('plugin = Plugin', 'create_runtime = lifecycle(id="demo.runtime",type="runtime",source={"kind":"file","ref":"runtime_resource.py","export":"create_runtime"},implementation_files=["plugin_support.py"],rulesets=["vibeflow.plugin"],presentation={"fill":"#abcdef","shape":"cyl"})\n\nplugin = Plugin')
        text=text.replace('resources=[Start, Model, increment, number], runtime=create_runtime','resources=[Start, Model, increment, number, create_runtime]')
        (root/"plugin.py").write_text(text)
        actual=cli(root,"validate",name="validate")
        built=cli(root,"run",name="run")
        actual["metrics"]["run_exit"]=built["metrics"]["exit_code"]
        rows.append(observe(case,"resource-rules",actual,metrics={"run_exit":0}))
    for target in ("python","javascript"):
        for rejected in (False,True):
            case=f"rules.{target}.separate_module.{'reject' if rejected else 'accept'}"
            root=project(work/case,target,toolchain)
            if target=="javascript":
                code='import {defineRule,defineRuleset} from "@vibeflow/plugin";\n'
                result='{findings:[{rule_id:"DEMO.MODULE",severity:"error",file:context.facts.source_files.find(file=>file.endsWith("node_support.ts")),line:1,message:"separate rule diagnostic"}]}' if rejected else '{findings:[]}'
                code+='export const checker=defineRule({id:"demo.module",check(context){return '+result+';}});\nexport const checks=defineRuleset({id:"demo.module_checks",calls:[{id:"check",rule_id:"demo.module"}],entrypoints:{static:["check"]}});\n'
                (root/"checks.ts").write_text(code)
                path=root/"plugin.ts";text=path.read_text()
                path.write_text('import {checker,checks} from "./checks.ts";\n'+text.replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,checker,checks]'))
                replace(root,"node.ts",'rulesets:["vibeflow.process"]','rulesets:["demo.module_checks"]')
            else:
                result='{"findings":[{"rule_id":"DEMO.MODULE","severity":"error","file":next(file.path for file in context.require("source_context").files if file.path.endswith("node_support.py")),"line":1,"message":"separate rule diagnostic"}]}' if rejected else '{"findings":[]}'
                code='from vibeflow.targets.python.sdk import rule,ruleset\n@rule(id="demo.module")\ndef checker(context,inputs,params):\n    return '+result+'\nchecks=ruleset(id="demo.module_checks",calls=[{"id":"check","rule_id":"demo.module"}],entrypoints={"static":["check"]})\n'
                (root/"checks.py").write_text(code)
                path=root/"plugin.py";text=path.read_text();path.write_text('from checks import checker,checks\n'+text.replace('resources=[Start, Model, increment, number]','resources=[Start, Model, increment, number,checker,checks]'))
                replace(root,"node_resource.py",'rulesets=["vibeflow.process"]','rulesets=["demo.module_checks"]')
            actual=cli(root,"validate",name="validate")
            rows.append(observe(case,"resource-rules",actual,accept=not rejected,code="DEMO.MODULE" if rejected else None))
    return rows
