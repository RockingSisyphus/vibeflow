// Explicit standard Node host. A custom browser/desktop environment supplies its own host.
import {pathToFileURL} from "node:url";
import {resolve} from "node:path";
import {runConnected} from "./workflow_host.mjs";

const [modulePath]=process.argv.slice(2);
if(!modulePath)throw new Error("usage: node workflow_node.mjs WORKFLOW_MODULE");
const workflow=await import(pathToFileURL(resolve(modulePath)).href);
const run=workflow.runWorkflowAsync||workflow.runWorkflow;
if(typeof run!=="function")throw new Error("module must export runWorkflow or runWorkflowAsync");
await runConnected(run,{url:process.env.VIBEFLOW_COORDINATION_URL,
  id:process.env.VIBEFLOW_INSTANCE_ID||null,workflow:resolve(modulePath)});
