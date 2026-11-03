"""Branch order and independent folding from a real reviewed SDK project."""
import json

from .support import ROOT, cli, command, workspace, write


def test_expansion_preserves_parallel_branch_order(tmp_path,browser_runtime):
    app=workspace(tmp_path,'''from vibeflow.targets.python.sdk import node
@node(id="layout.boundary",node_type="vibeflow.node",flow_kind="terminal",rulesets=[],contract={})
class Boundary:
    def run_pure(self,inputs,params):return {}
@node(id="layout.work",node_type="vibeflow.node",rulesets=[],contract={})
class Work:
    def run_pure(self,inputs,params):return {}
''')
    def node(name,definition="layout.boundary",**options):
        return {"id":name,"definition_id":definition,"display_name":name,"description":"Actual branch "+name,**options}
    def group(key,nodes,edges):
        return {"type_key":key,"display_name":key,"description":"A real nested branch","rulesets":[],
            "requires":[],"provides":[],"pipeline":{"nodes":nodes,"edges":edges}}
    write(app / "configs/leaf.jsonc",group("layout.leaf",[node("start"),node("work","layout.work"),node("end")],
        [["start","work"],["work","end"]]))
    write(app / "configs/branch.jsonc",group("layout.branch",[node("start"),node("first","layout.leaf"),
        node("second","layout.leaf"),node("end",join_policy="all")],
        [["start","first"],["start","second"],["first","end"],["second","end"]]))
    nodes=[node("start"),node("request__start"),node("event__start"),node("request__boundary","layout.branch"),
        node("event__boundary","layout.branch"),node("request__end"),node("event__end")]
    config=write(app / "configs/main.jsonc",{"rulesets":[],"nodeset_imports":["leaf.jsonc","branch.jsonc"],"pipeline":{
        "nodes":nodes,"edges":[["start","request__start"],["start","event__start"],
            ["request__start","request__boundary"],["event__start","event__boundary"],
            ["request__boundary","request__end"],["event__boundary","event__end"]]}})
    write(app / "vibeflow_project.jsonc",{"project_target":"python","architecture":{"documents":[{
        "workflow":"configs/main.jsonc","document":"ARCHITECTURE.jsonc"}]}})
    cli(tmp_path,"review","--workspace",tmp_path / "vibeflow_config.jsonc","--config",config)
    result=command("node",ROOT / "tests/e2e/browser/branch_order.cjs",browser_runtime / "package.json",
        tmp_path / "vibeflow-preview.html",cwd=tmp_path)
    assert json.loads(result.stdout)["page_errors"]==[]
