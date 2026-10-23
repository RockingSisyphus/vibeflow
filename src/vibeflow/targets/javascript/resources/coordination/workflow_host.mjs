// Browser and Node hosts report their actual invocation completion through one protocol.
import {WorkflowClient, errorRecord} from "./workflow_client.mjs";

export async function runConnected(run, {url,id=null,workflow=null,initial={},entry,
    capabilities={},...options}={}) {
  const controller=new AbortController();
  const client=await WorkflowClient.open(url,{id,workflow,onStop:()=>controller.abort("workflow stop requested")});
  try {
    const outputs=await run({...initial,...client.inputs},{...options,
      entry:client.entry??entry,signal:controller.signal,
      workflowInstanceId:client.id,
      capabilities:{...capabilities,"vibeflow.workflow":client.operations()}});
    await client.finish({outputs});
    return outputs;
  } catch(error) {
    try {await client.finish({state:error?.code==="VF_ABORTED"||error?.name==="AbortError"?"cancelled":"failed",
      error:errorRecord(error)});}
    catch(delivery){if(delivery!==error)error.coordinationError=delivery;}
    throw error;
  }
}
