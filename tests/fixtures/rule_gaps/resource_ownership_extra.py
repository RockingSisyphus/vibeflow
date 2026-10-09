"""Workspace boundaries and shared source permissions through real workflows."""
from common import write
from resource_support import project,cli,replace,observe,KINDS,FILES,PARTS,config


def run_cases(work,toolchain):
    rows=[]
    for kind in KINDS:
        for registered in (False,True):
            case=f"ownership.javascript.{kind}.cross_root.{'registered' if registered else 'unregistered'}"
            root=project(work/case/"project",toolchain=toolchain);sibling=root.parent/"shared";sibling.mkdir()
            (sibling/"leaf.ts").write_text("export function leaf(value:number){return value;}\n")
            write(sibling/"vibeflow_project.jsonc",{"project_target":"javascript","javascript":{"package_root":"."}})
            replace(root,FILES[kind],'"'+PARTS[kind]+'"','"'+PARTS[kind]+'","../shared/leaf.ts"')
            with (root/PARTS[kind]).open("a") as f:f.write('import {leaf} from "../shared/leaf.ts";\nexport function cross(value:number){return leaf(value);}\n')
            if registered:write(root/"vibeflow_config.jsonc",{"roots":[{"id":"resource-demo","path":"."},{"id":"shared","path":"../shared"}]})
            actual=cli(root,"validate",name="validate")
            rows.append(observe(case,"resource-ownership",actual,accept=registered,code=None if registered else "RESOURCE.SOURCE.ROOT"))
    for kind in ("node","base_lib"):
        for unsafe in (False,True):
            case=f"ownership.javascript.{kind}.shared_host.{'io' if unsafe else 'pure'}";root=project(work/case,toolchain=toolchain)
            # Both resources explicitly own a shared file; Host permission must
            # not widen the selected Process or BaseLib constraint.
            (root/"shared.ts").write_text('export function shared(value:number){'+('console.log(value);' if unsafe else '')+'return value;}\n')
            for selected in (kind,"host_extension"):
                replace(root,FILES[selected],'"'+PARTS[selected]+'"','"'+PARTS[selected]+'","shared.ts"')
                with (root/PARTS[selected]).open("a") as f:f.write('import {shared} from "./shared.ts";\nexport function sharedUse(value:number){return shared(value);}\n')
            actual=cli(root,"validate",name="validate")
            rows.append(observe(case,"resource-ownership",actual,accept=not unsafe,code="VF_BASE_LIB_HOST_IO" if unsafe else None))
    # Registering an IO-capable neighbor does not authorize direct imports.
    for kind in ("node","base_lib","plugin"):
        for imported in (False,True):
            case=f"ownership.javascript.{kind}.host_layer.{'imported' if imported else 'neighbor'}";root=project(work/case,toolchain=toolchain)
            if imported:
                with (root/PARTS[kind]).open("a") as f:f.write('import {host} from "./host.ts";\nexport function hidden(){return host.createHost({});}\n')
            actual=cli(root,"validate",name="validate")
            rows.append(observe(case,"resource-ownership",actual,accept=not imported,
                code="VF_PLUGIN_IMPORT_POLICY" if kind=="plugin" and imported else "VF_IMPORT_LAYER" if imported else None))
    # Different exported libraries in one file retain their own identities.
    # A Host selecting the second library must not be checked against the first.
    for declared in (False,True):
        case=f"ownership.javascript.host_extension.same_file_libraries.{'declared' if declared else 'undeclared'}"
        root=project(work/case,toolchain=toolchain)
        path=root/"math.ts";path.write_text(path.read_text()+'\nexport const secondary=defineBaseLib({id:"demo.secondary",rulesets:["vibeflow.base_lib"],implementation(value:number){return value+1;}});\n')
        path=root/"plugin.ts";path.write_text(path.read_text().replace('import {library}', 'import {library,secondary}').replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,secondary,host,session,number]'))
        path=root/"host.ts";text=path.read_text().replace('import {library}', 'import {secondary}').replace('library.implementation','secondary.implementation')
        path.write_text(text.replace('base_libs:["demo.math"]','base_libs:["demo.secondary"]') if declared else text)
        actual=cli(root,"validate",name="validate")
        rows.append(observe(case,"resource-ownership",actual,accept=declared,code=None if declared else "VF_IMPORT_LAYER"))
    for imported_node in (False,True):
        case=f"ownership.python.node.mixed_library.{'node' if imported_node else 'library'}"
        root=project(work/case,"python",toolchain)
        with (root/"math_resource.py").open("a") as file:
            file.write('\nfrom vibeflow.targets.python.sdk import node\n@node(type_key="demo.extra", contract={}, rulesets=[])\nclass Extra:\n    def run_pure(self, inputs, params):\n        return {}\n')
        replace(root,"plugin.py","from math_resource import increment","from math_resource import increment, Extra")
        replace(root,"plugin.py","increment, number]","increment, number, Extra]")
        if imported_node:
            replace(root,"node_resource.py","from math_resource import increment","from math_resource import increment, Extra")
            replace(root,"node_resource.py",'        return {"result":', '        Extra().run_pure({}, {})\n        return {"result":')
        actual=cli(root,"validate",name="validate")
        observed=observe(case,"resource-ownership",actual,accept=not imported_node,code="VF_IMPORT_LAYER" if imported_node else None)
        # The selected declaration import rule rejects this before the static
        # NoSideEffects entry. Assert its located root cause, not a later rule
        # that cannot run after the import phase fails.
        rows.append(observed)
    for declared in (False,True):
        case=f"ownership.python.node.same_file_libraries.{'declared' if declared else 'undeclared'}"
        root=project(work/case,"python",toolchain)
        with (root/"math_resource.py").open("a") as file:
            file.write('\n@base_lib(id="demo.math2",implementation_files=["math_support.py"],rulesets=["vibeflow.base_lib"])\ndef other_increment(value):\n    return add(value,1)\n')
        replace(root,"plugin.py","from math_resource import increment","from math_resource import increment, other_increment")
        replace(root,"plugin.py","increment, number]","increment, number, other_increment]")
        replace(root,"node_resource.py","from math_resource import increment","from math_resource import other_increment as increment")
        if declared:replace(root,"node_resource.py",'base_libs=["demo.math"]','base_libs=["demo.math2"]')
        actual=cli(root,"validate",name="validate")
        rows.append(observe(case,"resource-ownership",actual,accept=declared,code=None if declared else "VF_IMPORT_LAYER"))
    return rows
