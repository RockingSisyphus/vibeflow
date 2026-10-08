"""Selected workflows preserve shared-source and cross-root import permissions."""

from pathlib import Path

from sandbox.adaptation_regressions.common import row, run_cli, write_json
from sandbox.adaptation_regressions.structure import CONTRACT, findings, write


def workspace(root, *, cross_root=False):
    root.mkdir(parents=True)
    roots = [{"id":"app","path":"app"}, {"id":"shared","path":"shared"}] if cross_root else [{"id":"app","path":"."}]
    write_json(root / "vibeflow_config.jsonc", {"roots":roots})
    for item in roots:
        write_json(root / item["path"] / "vibeflow_project.jsonc", {"project_target":"python"})
    return root / ("app" if cross_root else ".")


def workflow(app, name, plugin, types):
    path = app / "configs" / (name + ".jsonc")
    write_json(path, {"plugins":[{"source":{"kind":"file","ref":plugin}}],"rulesets":[],
        "pipeline":{"nodes":[{"id":"leaf" + str(index),"type_used":type_key,
            "display_name":"Leaf " + str(index),"description":"Review the selected implementation."}
            for index,type_key in enumerate(types)]}})
    return path


def shared_fixture(root, *, denied):
    app = workspace(root)
    second_contract = {"provides":[{"key":"result2","type":"number","display_name":"Second result"}],
                       "output_semantics":{"result2":["The second calculated result."]}}
    write(app,"parts/util.py","def value():\n    return 7\n")
    write(app,"nodes/shared.py", "from parts.util import value\n"
        "class First:\n    def run_pure(self,inputs,params):\n        return {'result':value()}\n"
        "class Second:\n    def run_pure(self,inputs,params):\n        return {'result2':" + ("value()" if denied else "7") + "}\n")
    write(app,"plugins/entry.py", "from vibeflow.targets.python.sdk import Plugin,node,SourceLocator\n"
        f"first=node(type_key='audit.first',contract={CONTRACT!r},rulesets=['vibeflow.process'],"
        "source=SourceLocator('file','nodes/shared.py','First'),implementation_files=['../parts/util.py'])\n"
        f"second=node(type_key='audit.second',contract={second_contract!r},rulesets=['vibeflow.process'],"
        "source=SourceLocator('file','nodes/shared.py','Second'))\n"
        "plugin=Plugin(id='audit.shared',resources=[first,second],declaration_rulesets=['vibeflow.plugin_declaration'])\n")
    return workflow(app,"workflow","plugins/entry.py",("audit.first","audit.second"))


def library_fixture(root, *, cross_root=False, both=False, denied=False):
    app = workspace(root,cross_root=cross_root)
    library_root = root / "shared" if cross_root else app
    write(library_root,"libraries/math.py","def value():\n    return 7\n")
    write(app,"nodes/leaf.py","from libraries.math import value\n"
        "class Leaf:\n    def run_pure(self,inputs,params):\n        return {'result':value()}\n")
    for selection in (("allowed","denied") if both else (("denied",) if denied else ("allowed",))):
        source = ("from vibeflow.targets.python.sdk import Plugin,node,base_lib,SourceLocator\n"
            f"library=base_lib(id='audit.library',rulesets=['vibeflow.base_lib'],source=SourceLocator('file',"
            f"{'../shared/libraries/math.py' if cross_root else 'libraries/math.py'!r},'value'))\n"
            f"leaf=node(type_key='audit.leaf',contract={CONTRACT!r},rulesets=['vibeflow.process'],"
            "source=SourceLocator('file','nodes/leaf.py','Leaf'),base_libs="
            + ("[]" if selection == "denied" else "['audit.library']") + ")\n"
            "plugin=Plugin(id='audit." + selection + "',resources=[leaf,library],"
            "declaration_rulesets=['vibeflow.plugin_declaration'])\n")
        write(app,"plugins/" + selection + ".py",source)
        workflow(app,selection,"plugins/" + selection + ".py",("audit.leaf",))
    return app


def lifecycle_fixture(root, *, denied=True):
    app = workspace(root)
    write(app,"nodes/leaf.py", "from vibeflow.targets.python.sdk import node\n"
        f"@node(type_key='audit.leaf',contract={CONTRACT!r},rulesets=[])\n"
        "class Leaf:\n    def run_pure(self,inputs,params):\n        return {'result':7}\n")
    write(app,"libraries/math.py","def value():\n    return 7\n")
    write(app,"plugins/factory.py", ("from nodes.leaf import Leaf\n" if denied else "from libraries.math import value\n")
        + "class Compiler:\n    def before_compile(self,graph):\n        self.value = " + ("Leaf" if denied else "value()") + "\n"
        "def compiler(context):\n    return Compiler()\n")
    write(app,"plugins/entry.py", "from vibeflow.targets.python.sdk import Plugin,lifecycle,base_lib,SourceLocator\n"
        "from nodes.leaf import Leaf\n"
        "library=base_lib(id='audit.library',rulesets=['vibeflow.base_lib'],source=SourceLocator('file','libraries/math.py','value'))\n"
        "factory=lifecycle(id='audit.compiler',type='compiler',rulesets=[],"
        "source=SourceLocator('file','plugins/factory.py','compiler'),base_libs=['audit.library'])\n"
        "plugin=Plugin(id='audit.lifecycle',resources=[Leaf,factory,library],declaration_rulesets=['vibeflow.plugin_declaration'])\n")
    return workflow(app,"workflow","plugins/entry.py",("audit.leaf",))


def checked(root, config, kernel, identifier, *, command="validate", denied=False, suffix="nodes/leaf.py", code="VF_IMPORT_LAYER"):
    args = [command,"--json", *( ["--config",str(config),"--workspace",str(root / "vibeflow_config.jsonc")]
        if command == "validate" else ["--workspace",str(root / "vibeflow_config.jsonc")])]
    raw = run_cli(root,args,kernel,name=identifier + "-" + command)
    diagnostics = [item for item in findings(raw["payload"]) if item.get("severity") == "error"]
    targets = [item for item in diagnostics if item.get("code",item.get("rule_id")) == code]
    resource = "audit.second" if identifier == "shared-denied" else "audit.compiler" if identifier == "lifecycle-contribution-denied" else "audit.leaf"
    target_path = config.parent.parent / suffix
    object_id = ("nodes.shared -> parts.util" if suffix == "nodes/shared.py" else
                 "plugins.factory -> nodes.leaf" if suffix == "plugins/factory.py" else "nodes.leaf -> libraries.math")
    target_exact = bool(targets) and all(item["severity"] == "error"
        and item.get("source_location") == {"path":str(target_path) if code == "VF_IMPORT_LAYER" else "app/" + suffix,"line":1,"column":1}
        and item.get("source_path") == str(target_path) and item.get("root_id") == "app"
        and item.get("object_type") == ("node" if code == "VF_IMPORT_LAYER" else "module_dependency")
        and item.get("object_id") == (resource if code == "VF_IMPORT_LAYER" else object_id)
        and (code == "VF_IMPORT_LAYER" or item.get("details",{}).get("resource_id") == resource) for item in targets)
    actual = {"exit_code":raw["exit_code"],"target_exact":target_exact,
        "error_codes":sorted({item.get("code",item.get("rule_id")) for item in diagnostics}),
        "diagnostics":diagnostics,"stdout_path":raw["stdout_path"],"stderr_path":raw["stderr_path"]}
    expected = {"exit_code":1 if denied else 0,"target_exact":denied}
    if identifier == "workflow-isolation-mixed":
        actual["workflow_states"] = {Path(item["config"]).stem:item["status"] for item in raw["payload"].get("reports",())}
        expected["workflow_states"] = {"allowed":"PASS","denied":"FAIL"}
    failures = []
    if actual["exit_code"] != expected["exit_code"] or actual["target_exact"] != expected["target_exact"]:
        failures.append(f"expected {expected}, got exit={actual['exit_code']} targeted={target_exact}: {actual['error_codes']}")
    if actual.get("workflow_states") != expected.get("workflow_states"):
        failures.append("one workflow borrowed the other's permission: " + repr(actual.get("workflow_states")))
    permitted = {code,"VF_IMPORT_LAYER","QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT",
                 "QUALITY.STRUCTURE.PLUGIN_NODE_IMPORT"} if denied else set()
    if set(actual["error_codes"]) - permitted:
        failures.append("unrelated errors masked the relationship: " + repr(actual["error_codes"]))
    return row("A05.python." + identifier + "." + command,"A05", "Explicit source ownership: " + identifier,
               expected,actual,failures,root)


def observe(work: Path,kernel: Path,toolchain=None,renderer=None):
    rows = []
    for denied in (False,True):
        name = "shared-denied" if denied else "shared-symbol-isolated"
        root = work / name
        config = shared_fixture(root,denied=denied)
        for command in ("validate","quality-check"):
            rows.append(checked(root,config,kernel,name,command=command,denied=denied,suffix="nodes/shared.py",
                code="QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT" if command == "quality-check" else "VF_IMPORT_LAYER"))
        name = "cross-root-denied" if denied else "cross-root-allowed"
        root = work / name
        app = library_fixture(root,cross_root=True,denied=denied)
        for command in ("validate","quality-check"):
            rows.append(checked(root,app / "configs" / (("denied" if denied else "allowed") + ".jsonc"),kernel,
                name,command=command,denied=denied))
    root = work / "workflow-isolation"
    app = library_fixture(root,both=True)
    for name in ("allowed","denied"):
        rows.append(checked(root,app / "configs" / (name + ".jsonc"),kernel,"workflow-isolation-" + name,
                            denied=name == "denied"))
    rows.append(checked(root,app / "configs/allowed.jsonc",kernel,"workflow-isolation-mixed",command="quality-check",
                        denied=True,code="QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT"))
    for denied in (False,True):
        name = "lifecycle-contribution-denied" if denied else "lifecycle-library-allowed"
        root = work / name
        config = lifecycle_fixture(root,denied=denied)
        rows.append(checked(root,config,kernel,name,command="quality-check",denied=denied,
                            suffix="plugins/factory.py",code="QUALITY.STRUCTURE.PLUGIN_NODE_IMPORT"))
    return rows
