"""Normal SDK host application inputs and CLI builds."""
import json
import os
from pathlib import Path
import shutil
from tests.e2e.support import cli,write


def register(root,target):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    path=root.parent / "vibeflow_config.jsonc"
    data=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"roots":[]}
    if not any(item["id"]==root.name for item in data["roots"]):data["roots"].append({"id":root.name,"path":root.name})
    write(path,data)
    write(root.parent / "project_rules.jsonc",{"rulesets":[]})
    write(root / "root_rules.jsonc",{"rulesets":[]})
    write(root / "vibeflow_project.jsonc",{"project_target":target})
    return path


def python_input_project(root,source,plugin):
    root=Path(root);workspace=register(root,"python")
    write(root / "nodes/steps.py",source)
    write(root / "plugins/demo/plugin.py",plugin)
    config=write(root / "workflow.jsonc",{"plugins":[{"source":{"kind":"file","ref":"plugins/demo/plugin.py"}}],"rulesets":[],"pipeline":{"nodes":[]}})
    return workspace,config


def javascript_project(root,source,plugin):
    root=Path(root);workspace=register(root,"javascript")
    (root / "node_modules").symlink_to(Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"]) / "node_modules",target_is_directory=True)
    write(root / "package.json",{"type":"module","private":True})
    write(root / "nodes/steps.ts",source)
    write(root / "plugins/demo/plugin.ts",plugin)
    config=write(root / "workflow.jsonc",{"plugins":[{"source":{"kind":"file","ref":"plugins/demo/plugin.ts"}}],"rulesets":[],"pipeline":{"nodes":[]}})
    return workspace,config

def python_project(root):
    source = 'from vibeflow.targets.python.sdk import node\n\n@node(node_type="vibeflow.node",id="peer.boundary",flow_kind="terminal",contract={},rulesets=["vibeflow.process"])\nclass Boundary:\n    def run_pure(self,inputs,params):return {}\n\n@node(node_type="vibeflow.node",id="peer.work",rulesets=["vibeflow.process"],\n      workflow_operations=[{"operation":"send"},{"operation":"receive"}],\n      contract={"params_schema":{"workflow":{"type":"object"},"launch":{"type":"object"},"factor":{"type":"number"}},"params_defaults":{"workflow":{},"launch":{},"factor":3},\n        "provides":[{"key":"out","type":"number","display_name":"Result"}],"output_semantics":{"out":["Tripled message"]}})\nclass Work:\n    async def run_pure(self,inputs,params,context):\n        api=context.workflow\n        message=await api.receive({"port":"request"})\n        value=message["payload"]["value"]*params["factor"]\n        api.send({"id":message["sender"],"port":"reply","payload":{"value":value,"self":context.workflow.self()["id"]}})\n        return {"out":value}\n'
    plugin_source = 'from vibeflow.targets.python.sdk import Plugin,data_schema\nplugin=Plugin(id="peer",resources=[data_schema(type_key="number",schema={"type":"number"})])\n'
    workspace, config = python_input_project(root, source, plugin_source)
    data = json.loads(config.read_text())
    data['rulesets'] = ['vibeflow.workflow']
    data['pipeline'] = {'entry_mode': 'async', 'nodes': [{'id': key, 'definition_id': node, 'display_name': key, 'description': key} for key, node in [('start', 'peer.boundary'), ('work', 'peer.work'), ('end', 'peer.boundary')]], 'edges': [['start', 'work'], ['work', 'end']], 'outputs': [{'type': 'number', 'as': 'result', 'cardinality': 'exactly_one', 'display_name': 'Result'}]}
    data['pipeline']['nodes'][1]['rulesets'] = ['vibeflow.process']
    config.write_text(json.dumps(data))
    return (workspace, config)

def node_module(root, *, caller=False, peer=None, prefix=""):
    """Build a real SDK project for the standard Node or browser host."""
    import shutil

    operations = ["send", "receive"]
    body = '''
      const api=context.workflow;
      const message=await api.receive({port:"request"});
      const value=message.payload.value*3;
      api.send({id:message.sender,port:"reply",payload:{value,self:context.workflow.self().id}});
      return {out:value};
    '''
    if caller:
        operations += ["call", "wait"]
        body = '''
          const api=context.workflow;
          const peer=await api.call({workflow:params.workflow,launch:params.launch});
          api.send({id:peer.id,port:"request",payload:{value:7}});
          const message=await api.receive({port:"reply"});
          const ended=await api.wait({id:peer.id});
          if(ended.state!=="succeeded")throw new Error(JSON.stringify(ended));
          return {out:message.payload.value*3};
        '''
    definition = {
        "id":"peer.work", "node_type":"vibeflow.node", "rulesets":["vibeflow.python_io" if prefix else "vibeflow.process"],
        "workflow_operations":[{"operation": op} for op in operations],
        "completion":"suspend",
        "contract":{
            "provides":[{"key":"out","type":"number","display_name":"Result"}],
            "output_semantics":{"out":["Calculated reply"]},
            "params_schema":{"workflow":{"type":"object"},"launch":{"type":"object"}},
            "params_defaults":{"workflow":{},"launch":{}}},
    }
    source = 'import {defineNode} from "@vibeflow/plugin";\n'
    source += 'export const work=defineNode({...'+json.dumps(definition)+',async run(inputs,params,context){'+prefix+body+'}});\n'
    source += 'export const boundary=defineNode({id:"peer.boundary",node_type:"vibeflow.node",flow_kind:"terminal",contract:{},rulesets:[],run(){return {};}});'
    plugin = 'import {definePlugin,defineDataSchema} from "@vibeflow/plugin";export const number=defineDataSchema({type_key:"number",schema:{type:"number"}});export const plugin=definePlugin({id:"peer",resources:[number]});'
    workspace, config = javascript_project(root / "source", source, plugin)
    value = json.loads(config.read_text())
    value["pipeline"] = {
        "entry_mode":"async",
        "nodes":[{"id":key,"definition_id":"peer.work" if key=="work" else "peer.boundary",
                  "display_name":key,"description":key, **({"config":peer or {}} if key=="work" else {})}
                 for key in ("start","work","end")],
        "edges":[["start","work"],["work","end"]],
        "outputs":[{"type":"number","as":"result","cardinality":"exactly_one","display_name":"Result"}],
    }
    config.write_text(json.dumps(value))
    built = json.loads(cli(root, "build", "--workspace", workspace, "--config", config, "--out-dir", root / "build", "--target", "browser", "--profile", "single-esm").stdout)
    path = root / "workflow.mjs"
    shutil.copy2(built["entry"], path)
    return path

