"""Explicit file validation, duplicate resources and stable alternate exports."""
import json

from resource_support import project,cli,replace,observe,KINDS,FILES,PARTS,IDS,config,declarations


def run_cases(work,toolchain):
    rows=[]
    for kind in KINDS:
        for variant in ("unused_missing","duplicate_file","glob","outside_root","wrong_container","duplicate_resource"):
            case=f"register.javascript.{kind}.{variant}";root=project(work/case,toolchain=toolchain)
            part=PARTS[kind];code="DESCRIPTOR.INVALID"
            if variant=="unused_missing":
                replace(root,FILES[kind],'"'+part+'"','"'+part+'","missing-unused.ts"');code="RESOURCE.SOURCE.UNAVAILABLE"
            elif variant=="duplicate_file":replace(root,FILES[kind],'"'+part+'"','"'+part+'","'+part+'"')
            elif variant=="glob":replace(root,FILES[kind],'"'+part+'"','"'+part+'","*.ts"')
            elif variant=="outside_root":
                (root.parent/"unowned.ts").write_text("export const value=1;\n")
                replace(root,FILES[kind],'"'+part+'"','"'+part+'","../unowned.ts"');code="RESOURCE.SOURCE.ROOT"
            elif variant=="wrong_container":replace(root,FILES[kind],'implementation_files:[','implementation_files:true,unused_files:[')
            elif variant=="duplicate_resource":
                if kind=="plugin":
                    path=root/"plugin.ts";text=path.read_text()
                    source='import {defineResource} from "@vibeflow/plugin";\nexport const duplicate=defineResource({kind:"plugin",id:"demo.runtime",type:"runtime",targets:["node","browser"],implementations:[{language:"typescript",targets:["node","browser"],source:{kind:"file",ref:"plugin_support.ts",export:"lifecycle"}}]});\n'
                    path.write_text(source+text.replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,duplicate]'));code="DESCRIPTOR.CONFLICT"
                else:
                    name={"node":"model","base_lib":"library","host_extension":"host"}[kind]
                    replace(root,"plugin.ts",'resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,'+name+']');code="DESCRIPTOR.DUPLICATE"
            actual=cli(root,"inspect-resources",name="registration")
            rows.append(observe(case,"resource-registration",actual,accept=False,code=code))
    for target in ("python","javascript"):
        case=f"register.{target}.alternate_export";root=project(work/case,target,toolchain)
        file="plugin.py" if target=="python" else "plugin.ts"
        replace(root,file,"plugin = Plugin" if target=="python" else "const plugin=definePlugin","selected = Plugin" if target=="python" else "const selected=definePlugin")
        config(root,lambda value:value["plugins"][0]["source"].update(export="selected"))
        actual=cli(root,"inspect-resources",name="registration")
        from vibeflow.tooling.project.descriptor_loader import load_workflow_catalogs
        catalogs=load_workflow_catalogs(root,workflow_config=root/"workflow.jsonc")
        declaration=catalogs.plugin_records[0]["declaration"]
        actual["metrics"]["selected_symbol"]=declaration["implementations"][0]["source"]["export"]
        del catalogs
        rows.append(observe(case,"resource-registration",actual,metrics={"selected_symbol":"selected"}))
    for target,kinds in (("javascript",KINDS),("python",("node","base_lib","plugin"))):
        for kind in kinds:
            case=f"register.{target}.{kind}.module_relative_files";root=project(work/case,target,toolchain)
            directory=root/"parts";directory.mkdir()
            if target=="javascript":
                source,part=FILES[kind],PARTS[kind]
                for file in (source,part,*(('types.d.ts',) if kind=="host_extension" else ())):
                    (root/file).rename(directory/file)
                for path in root.glob("*.ts"):
                    path.write_text(path.read_text().replace('"./'+source+'"','"./parts/'+source+'"'))
                path=directory/source;text=path.read_text()
                for neighbor in ("node.ts","math.ts","host.ts"):
                    text=text.replace('"./'+neighbor+'"','"../'+neighbor+'"')
                path.write_text(text)
                if kind=="plugin":config(root,lambda data:data["plugins"][0]["source"].update(ref="parts/plugin.ts"))
            else:
                source={"node":"node_resource.py","base_lib":"math_resource.py","plugin":"plugin.py"}[kind]
                part={"node":"node_support.py","base_lib":"math_support.py","plugin":"plugin_support.py"}[kind]
                (directory/"__init__.py").write_text("")
                for file in (source,part):(root/file).rename(directory/file)
                module=source.removesuffix(".py")
                for path in root.glob("*.py"):
                    path.write_text(path.read_text().replace('from '+module+' import','from parts.'+module+' import'))
                path=directory/source;text=path.read_text().replace('from '+part.removesuffix(".py")+' import','from .'+part.removesuffix(".py")+' import')
                text=text.replace('"'+part+'"','"'+part+'","__init__.py"');path.write_text(text)
                if kind=="plugin":config(root,lambda data:data["plugins"][0]["source"].update(ref="parts/plugin.py"))
            actual=cli(root,"validate",name="validate")
            rows.append(observe(case,"resource-registration",actual))
    return rows
