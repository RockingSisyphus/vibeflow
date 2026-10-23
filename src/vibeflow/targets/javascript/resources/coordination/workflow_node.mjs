// Explicit standard Node host. A custom browser/desktop environment supplies its own host.
import {pathToFileURL} from "node:url";
import {resolve,dirname,join} from "node:path";
import {readFileSync,existsSync} from "node:fs";
import {parseArgs} from "node:util";
import {runConnected} from "./workflow_host.mjs";

const [modulePath,...args]=process.argv.slice(2);
const {values}=parseArgs({args,options:{entry:{type:"string"},root:{type:"string"},workflow:{type:"string"}}});
const metadataPath=modulePath&&join(dirname(resolve(modulePath)),"workflow-launches.json");
const metadata=metadataPath&&existsSync(metadataPath)?JSON.parse(readFileSync(metadataPath,"utf8")):null;
if(metadata && metadata.format!=="vibeflow.workflow-launches.v2")throw new Error("unsupported workflow launch declarations; rebuild the bundle");
const reference=values.workflow?{root:values.root||"",path:values.workflow}:metadata?.workflow;
if(!modulePath)throw new Error("usage: node workflow_node.mjs WORKFLOW_MODULE");
const workflow=await import(pathToFileURL(resolve(modulePath)).href);
const run=workflow.runWorkflowAsync||workflow.runWorkflow;
if(typeof run!=="function")throw new Error("module must export runWorkflow or runWorkflowAsync");
await runConnected(run,{url:process.env.VIBEFLOW_COORDINATION_URL,
  id:process.env.VIBEFLOW_INSTANCE_ID||null,workflow:reference||null,entry:values.entry});
