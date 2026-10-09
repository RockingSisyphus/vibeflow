"""Registration, activation and workflow isolation through public CLIs."""
import json
from pathlib import Path

from resource_support import project, cli, config, replace, declarations, observe, FILES, IDS


def run_cases(work, toolchain):
    rows=[]
    for target,kinds in (("javascript",("node","base_lib","plugin","host_extension")),("python",("node","base_lib","plugin"))):
        for kind in kinds:
            variants=("registered","disabled","planned","unselected","missing_export","duplicate_plugin")
            for variant in variants:
                case=f"register.{target}.{kind}.{variant}"
                root=project(work/case,target,toolchain)
                if variant == "disabled":config(root,lambda x:x["plugins"][0].update(enabled=False))
                elif variant == "planned":config(root,lambda x:x["plugins"][0].update(id="demo",status="planned"))
                elif variant == "unselected":config(root,lambda x:x.update(plugins=[]))
                elif variant == "missing_export":config(root,lambda x:x["plugins"][0]["source"].update(export="missing"))
                elif variant == "duplicate_plugin":config(root,lambda x:x["plugins"].append(x["plugins"][0].copy()))
                marker=root/"declaration.marker"
                if variant in {"registered","disabled","planned","unselected"}:
                    entry=root/("plugin.py" if target=="python" else "plugin.ts")
                    prefix=('from pathlib import Path\nPath('+repr(str(marker))+').write_text("loaded")\n' if target=="python" else 'import {writeFileSync} from "node:fs";\nwriteFileSync('+json.dumps(str(marker))+',"loaded");\n')
                    entry.write_text(prefix+entry.read_text())
                actual=cli(root,"inspect-resources",name="registered")
                actual["metrics"]["declaration_loaded"]=marker.exists()
                ids=[item.get("id",item.get("type_key")) for item in declarations(actual)]
                actual["metrics"]["resource_present"]=IDS[kind] in ids
                accept=variant not in {"missing_export","duplicate_plugin"}
                rows.append(observe(case,"resource-registration",actual,accept=accept,
                    code="PLUGIN.DUPLICATE" if variant=="duplicate_plugin" else "PLUGIN.DECLARATION.LOAD" if variant=="missing_export" else None,
                    metrics={"resource_present":variant=="registered","declaration_loaded":variant=="registered"}))
    # The same definition is selected by two workflows with isolated config.
    for target in ("python","javascript"):
        case=f"register.{target}.workflow_isolation";root=project(work/case,target,toolchain)
        marker=root/"config.marker"
        if target=="javascript":
            path=root/"plugin.ts";text=path.read_text()
            prefix='import {defineRule,defineRuleset} from "@vibeflow/plugin";\nimport {writeFileSync} from "node:fs";\nexport const capture=defineRule({id:"demo.config",check(context){writeFileSync('+json.dumps(str(marker))+',JSON.stringify(context.facts.plugins.demo.offset));return {findings:[]};}});\nexport const configuration=defineRuleset({id:"demo.configuration",calls:[{id:"check",rule_id:"demo.config"}],entrypoints:{static:["check"]}});\n'
            text=text.replace('id:"demo",','id:"demo",config_schema:{offset:{type:"integer"}},config_defaults:{offset:1},').replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,capture,configuration]')
            path.write_text(prefix+text)
            replace(root,"node.ts",'rulesets:["vibeflow.process"]','rulesets:["vibeflow.process","demo.configuration"]')
        else:
            path=root/"plugin.py";text=path.read_text()
            prefix='from vibeflow.targets.python.sdk import rule,ruleset\nfrom pathlib import Path\n@rule(id="demo.config")\ndef capture(context,inputs,params):\n    Path('+repr(str(marker))+').write_text(str(context.facts["plugins"]["demo"]["offset"]))\n    return {"findings":[]}\nconfiguration=ruleset(id="demo.configuration",calls=[{"id":"check","rule_id":"demo.config"}],entrypoints={"static":["check"]})\n'
            text=text.replace('id="demo",','id="demo",config_schema={"offset":{"type":"integer"}},config_defaults={"offset":1},').replace('resources=[Start, Model, increment, number]','resources=[Start, Model, increment, number,capture,configuration]')
            path.write_text(prefix+text)
            replace(root,"node_resource.py",'rulesets=["vibeflow.process"]','rulesets=["vibeflow.process","demo.configuration"]')
        config(root,lambda data:data["plugins"][0].update(config={"offset":2}))
        first=cli(root,"inspect-resources",name="first")
        second=config(root);second["plugins"][0]["config"]={"offset":3}
        (root/"second.jsonc").write_text(json.dumps(second,indent=2))
        actual=cli(root,"inspect-resources",name="second",config_file="second.jsonc")
        actual["metrics"]["definitions_identical"]=declarations(first)==declarations(actual)
        observed=[];exits=[]
        for index,file in enumerate(("workflow.jsonc","second.jsonc","workflow.jsonc")):
            checked=cli(root,"validate",name="config-"+str(index),config_file=file)
            exits.append(checked["metrics"]["exit_code"]);observed.append(int(marker.read_text()) if marker.exists() else None)
        actual["metrics"].update(configurations=observed,validation_exits=exits)
        rows.append(observe(case,"resource-registration",actual,metrics={"definitions_identical":True,"configurations":[2,3,2],"validation_exits":[0,0,0]}))
    from resource_registration_extra import run_cases as additional
    rows.extend(additional(work,toolchain))
    return rows
