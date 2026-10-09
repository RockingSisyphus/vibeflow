"""All file-size boundary observations, including pure declarations and unused parts."""
from resource_support import project,cli,replace,observe,KINDS,FILES,PARTS


def pad(path,count,target):
    text=path.read_text();comment="# audited file\n" if target=="python" else "// audited file\n"
    path.write_text(text+comment*(count-len(text.splitlines())))


def run_cases(work,toolchain):
    rows=[]
    for target,kinds in (("javascript",KINDS),("python",KINDS[:-1])):
        for kind in kinds:
            file,part=(FILES[kind],PARTS[kind]) if target=="javascript" else ({"node":"node_resource.py","base_lib":"math_resource.py","plugin":"plugin.py"}[kind],{"node":"node_support.py","base_lib":"math_support.py","plugin":"plugin_support.py"}[kind])
            for role in ("entry","support"):
                for count in (449,450,500,501):
                    case=f"limits.{target}.{kind}.{role}.{count}";root=project(work/case,target,toolchain)
                    pad(root/(file if role=="entry" else part),count,target)
                    actual=cli(root,"validate",name="validate")
                    node_entry=kind=="node" and role=="entry"
                    error="NODE.PURITY.SOURCE_TOO_LARGE" if node_entry else "NODE.PURITY.SOURCE_TOO_LARGE" if target=="javascript" and kind=="node" else "BASE_LIB.SOURCE.MAX_LINES"
                    warning="NODE.PURITY.SOURCE_NEAR_LIMIT" if node_entry or target=="javascript" and kind=="node" else "BASE_LIB.SOURCE.NEAR_LIMIT"
                    actual["metrics"]["boundary_warning"]=any(item["code"]==warning and item["severity"]=="warning" for item in actual["codes"])
                    observed=observe(case,"resource-ownership",actual,accept=count<=500,code=error if count>500 else None,
                        metrics={"boundary_warning":450<=count<=500})
                    if 450<=count<=500:
                        observed["expected"]["codes"]=[{"code":warning,"severity":"warning"}]
                        observed["expected"]["located_codes"]=[warning]
                    rows.append(observed)
        # Without a lifecycle, declaration auditing still enforces each file.
        for count in (449,450,500,501):
            case=f"limits.{target}.plugin_declaration.entry.{count}";root=project(work/case,target,toolchain)
            if target=="javascript":replace(root,"plugin.ts",'runtime(){return lifecycle();},','')
            else:replace(root,"plugin.py",'runtime=create_runtime, ','')
            pad(root/("plugin.py" if target=="python" else "plugin.ts"),count,target)
            actual=cli(root,"validate",name="validate")
            actual["metrics"]["boundary_warning"]=any(item["code"]=="BASE_LIB.SOURCE.NEAR_LIMIT" for item in actual["codes"])
            observed=observe(case,"resource-ownership",actual,accept=count<=500,code="BASE_LIB.SOURCE.MAX_LINES" if count>500 else None,
                metrics={"boundary_warning":450<=count<=500})
            if 450<=count<=500:observed["expected"].update(codes=[{"code":"BASE_LIB.SOURCE.NEAR_LIMIT","severity":"warning"}],located_codes=["BASE_LIB.SOURCE.NEAR_LIMIT"])
            rows.append(observed)
    return rows
