"""Fresh CLI sessions check, execute and render edits, then verify restoration."""
import json
from pathlib import Path

from common import write
from resource_support import project,cli,replace,observe,KINDS,FILES,PARTS,IDS,mutate_presentation,documents,declarations,display_resource,display_nodes
from resource_runtime import execute


def edit(root,kind,variant):
    source=FILES[kind];part=PARTS[kind]
    if variant=="add_file":
        (root/"additional.ts").write_text("export const extra=3;\n")
        replace(root,source,f'"{part}"',f'"{part}","additional.ts"')
    elif variant=="delete_file":(root/part).unlink()
    elif variant in {"rename_file","move_file"}:
        name="renamed.ts" if variant=="rename_file" else "parts/moved.ts"
        (root/name).parent.mkdir(exist_ok=True);(root/part).rename(root/name)
        replace(root,source,part,name)
    elif variant=="implementation":
        old,new={"node":("left*right","left*right+1"),"base_lib":("left+right","left+right+1"),
            "host_extension":("value+count","value+count+1"),
            "plugin":("beforeNode(){}",'beforeNode(){throw Error("edited lifecycle");}')}[kind]
        replace(root,part,old,new)
    elif variant=="ruleset":
        replace(root,source,'rulesets:["vibeflow.'+{"node":"process","base_lib":"base_lib","plugin":"plugin","host_extension":"host_extension"}[kind]+'"]','rulesets:[]')
    elif variant=="colour":mutate_presentation(root,kind,{"fill":"#bbddaa","stroke":"#345678","text":"#123456","shape":"rect","icon":"Edited"})
    elif variant=="shape":mutate_presentation(root,kind,{"fill":"#ddbbff","stroke":"#1a5276","text":"#123456","shape":"diamond","icon":"Changed"})


def execution(root,kind,name):
    built=cli(root,"build",name=name+"-build",extra=["--target","node","--profile","single-esm","--out-dir",root/name])
    if built["metrics"]["exit_code"]:return {"build_exit":built["metrics"]["exit_code"],"runtime_exit":None,"value":None}
    entry=Path(built["payload"]["entry"]).as_uri()
    body='const a=workflow.createWorkflowHost();await a.start();try{const result=a.runWorkflow({});console.log(JSON.stringify(result));}finally{await a.stop();}'
    actual=execute(root,'const workflow=await import('+json.dumps(entry)+');'+body,name=name+"-run")
    return {"build_exit":0,"runtime_exit":actual["metrics"]["exit_code"],"value":actual["payload"].get("number")}


def diagram(root,kind,name):
    actual,architecture,mermaid,browser=documents(root,name=name,screenshot=True)
    resource=display_resource(architecture,kind)
    fields=resource.get("effective_presentation",{}).get("values",{})
    nodes=display_nodes(browser,kind)
    # The rendered call or directory card uses its actual effective style.
    from resource_support import rgb,preview_style_matches
    correct=any(shape["fill"]==rgb(fields["fill"]) for node in nodes for shape in node["shapes"])
    project_file=root/"vibeflow_project.jsonc"
    data=json.loads(project_file.read_text());data.pop("architecture",None);write(project_file,data)
    return {"review_exit":actual["metrics"]["exit_code"],"browser_exit":actual["metrics"].get("browser_exit_code"),
            "fill":fields.get("fill"),"shape":fields.get("shape"),"matches_svg":correct,
            "matches_preview":preview_style_matches(browser,architecture,kind),
            "preview_errors":browser.get("preview",{}).get("errors"),"preview_network":browser.get("preview",{}).get("network")}


def run_cases(work,toolchain,*,kinds=KINDS,include_extra=True):
    rows=[]
    for kind in kinds:
        for variant in ("add_file","delete_file","rename_file","move_file","implementation","ruleset","colour","shape"):
            case=f"edits.javascript.{kind}.{variant}";root=project(work/case,toolchain=toolchain)
            if kind=="host_extension":
                replace(root,"node.ts",'run(){return {result:multiply(library.implementation(2),2)};}','run(inputs,params,context){return {result:context.capabilities["demo.session"].next(2)};}')
                replace(root,"node.ts",'base_libs:["demo.math"],','capabilities:[{id:"demo.session",operations:["next"]}],base_libs:["demo.math"],')
            initial={path:path.read_text() for path in root.glob("*.ts")}
            before=cli(root,"validate",name="before");before_run=execution(root,kind,"before")
            before_diagram=diagram(root,kind,"before-diagram") if variant in {"colour","shape"} else None
            edit(root,kind,variant)
            actual=cli(root,"validate",name="modified")
            inspected=cli(root,"inspect-resources",name="modified-registration")
            modified_run=execution(root,kind,"modified") if variant!="delete_file" else None
            modified_diagram=diagram(root,kind,"modified-diagram") if before_diagram else None
            for path,text in initial.items():path.write_text(text)
            # Extra now-unreferenced files never acquire registration just by being present.
            restored=cli(root,"validate",name="restored");restored_run=execution(root,kind,"restored")
            restored_diagram=diagram(root,kind,"restored-diagram") if before_diagram else None
            value=4 if kind=="host_extension" else 6
            metrics={"before_exit":0,"restored_exit":0,"registration_exit":1 if variant=="delete_file" else 0,
                     "before_run":{"build_exit":0,"runtime_exit":0,"value":value},"restored_run":{"build_exit":0,"runtime_exit":0,"value":value}}
            actual["metrics"].update(before_exit=before["metrics"]["exit_code"],restored_exit=restored["metrics"]["exit_code"],
                registration_exit=inspected["metrics"]["exit_code"],before_run=before_run,restored_run=restored_run)
            if modified_run:
                expected_value=value+1 if variant=="implementation" and kind in {"node","host_extension"} else 8 if variant=="implementation" and kind=="base_lib" else value
                metrics["modified_run"]={"build_exit":0,"runtime_exit":1 if variant=="implementation" and kind=="plugin" else 0,
                                         "value":None if variant=="implementation" and kind=="plugin" else expected_value}
                actual["metrics"]["modified_run"]=modified_run
            if modified_diagram:
                fill,shape=("#bbddaa","rect") if variant=="colour" else ("#ddbbff","diamond")
                metrics.update(modified_diagram={"review_exit":0,"browser_exit":0,"fill":fill,"shape":shape,"matches_svg":True,
                    "matches_preview":True,"preview_errors":[],"preview_network":[]},diagram_restored=True)
                actual["metrics"].update(modified_diagram=modified_diagram,diagram_restored=before_diagram==restored_diagram)
            descriptor=next((item for item in declarations(inspected) if item.get("id",item.get("type_key"))==IDS[kind]),{})
            if variant=="ruleset":
                metrics["modified_rulesets"]=[];actual["metrics"]["modified_rulesets"]=descriptor.get("rulesets")
            rows.append(observe(case,"resource-edits",actual,accept=variant!="delete_file",
                code="PLUGIN.DECLARATION.LOAD" if variant=="delete_file" else None,metrics=metrics))
    if include_extra:
        from resource_edit_extra import run_cases as declaration_cases
        rows.extend(declaration_cases(work,toolchain))
    return rows
