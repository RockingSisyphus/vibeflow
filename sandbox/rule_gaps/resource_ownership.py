"""Explicit membership, import edges and per-file quality boundaries."""
from resource_support import project,cli,replace,observe,KINDS,FILES,PARTS


def run_cases(work,toolchain):
    rows=[]
    for kind in KINDS:
        for variant in ("registered","unregistered","transitive_registered","transitive_unregistered","missing_support","directory","over_limit","boundary","total_over_limit"):
            case=f"ownership.javascript.{kind}.{variant}";root=project(work/case,toolchain=toolchain)
            source=FILES[kind];part=PARTS[kind];code=None
            if variant=="unregistered":
                replace(root,source,f'"{part}"', '"unused.ts"');(root/"unused.ts").write_text("export const unused=1;\n")
                code="VF_IMPORT_OWNER"
            elif variant.startswith("transitive"):
                (root/"deep.ts").write_text("export function leaf(value:number){return value;}\n")
                with (root/part).open("a") as f:f.write('import {leaf} from "./deep.ts";\nexport function referenced(value:number){return leaf(value);}\n')
                if variant=="transitive_registered":replace(root,source,f'"{part}"',f'"{part}","deep.ts"')
                else:code="VF_IMPORT_OWNER"
            elif variant=="missing_support":
                (root/part).unlink();code="PLUGIN.DECLARATION.LOAD"
            elif variant=="directory":
                replace(root,source,f'"{part}"','"support_dir"');(root/"support_dir").mkdir();code="RESOURCE.SOURCE.UNAVAILABLE"
            elif variant in {"over_limit","boundary","total_over_limit"}:
                path=root/part;count=501 if variant=="over_limit" else 500 if variant=="boundary" else 300
                text=path.read_text();path.write_text(text+"// reviewed support\n"*(count-len(text.splitlines())))
                if variant=="over_limit":code="NODE.PURITY.SOURCE_TOO_LARGE" if kind=="node" else "BASE_LIB.SOURCE.MAX_LINES"
                elif variant=="total_over_limit":
                    path=root/source;text=path.read_text();path.write_text(text+"// reviewed entry\n"*(300-len(text.splitlines())))
            actual=cli(root,"validate",name="validate")
            rows.append(observe(case,"resource-ownership",actual,accept=code is None,code=code))
    for kind,file,part in (("node","node_resource.py","node_support.py"),("base_lib","math_resource.py","math_support.py"),("plugin","plugin.py","plugin_support.py")):
        for variant in ("registered","unregistered","over_limit","total_over_limit"):
            case=f"ownership.python.{kind}.{variant}";root=project(work/case,"python",toolchain);code=None
            if variant=="unregistered":
                replace(root,file,f'"{part}"','"unused.py"');(root/"unused.py").write_text("UNUSED=1\n");code="VF_IMPORT_OWNER"
            elif variant in {"over_limit","total_over_limit"}:
                path=root/part;text=path.read_text();count=501 if variant=="over_limit" else 300
                path.write_text(text+"# reviewed support\n"*(count-len(text.splitlines())))
                if variant=="over_limit":code="BASE_LIB.SOURCE.MAX_LINES"
                else:
                    path=root/file;text=path.read_text();path.write_text(text+"# reviewed entry\n"*(300-len(text.splitlines())))
            actual=cli(root,"validate",name="validate")
            rows.append(observe(case,"resource-ownership",actual,accept=code is None,code=code))
    rows.extend(import_forms(work,toolchain))
    from resource_boundaries import run_cases as boundaries
    rows.extend(boundaries(work,toolchain))
    from resource_ownership_extra import run_cases as additional
    rows.extend(additional(work,toolchain))
    return rows


def import_forms(work,toolchain):
    rows=[]
    for kind in KINDS:
        for syntax in ("type_only","dynamic","require"):
            for registered in (False,True):
                case=f"ownership.javascript.{kind}.{syntax}.{'registered' if registered else 'unregistered'}"
                root=project(work/case,toolchain=toolchain)
                part=PARTS[kind];source=FILES[kind]
                extension="edge_types.d.ts" if syntax=="type_only" else "edge.ts"
                (root/extension).write_text("export type Value=number;\n" if syntax=="type_only" else "export function leaf(value:number){return value;}\n")
                addition=('import type {Value} from "./edge_types.d.ts";\nexport function typed(value:Value){return value;}\n' if syntax=="type_only" else
                          'export async function dynamic(){return await import("./edge.ts");}\n' if syntax=="dynamic" else
                          'export function required(){return require("./edge.ts");}\n')
                with (root/part).open("a") as file:file.write(addition)
                if registered:replace(root,source,'"'+part+'"','"'+part+'","'+extension+'"')
                actual=cli(root,"validate",name="validate")
                rows.append(observe(case,"resource-ownership",actual,accept=registered,
                                    code=None if registered else "VF_IMPORT_OWNER"))
    return rows
