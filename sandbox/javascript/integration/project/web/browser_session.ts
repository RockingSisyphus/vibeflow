import {createWindowPortApi} from "../adapters/window_ports.ts";

interface Workflow {
  runWorkflowAsync(inputs:Record<string,unknown>,options:Record<string,unknown>):Promise<unknown>;
}

// Application-owned invocation. API construction does not establish listeners;
// the workflow's explicit open Node does that work.
export function createBrowserSession(workflow:Workflow, entry?:string){
  const controller=new AbortController();
  const capabilities=createWindowPortApi({signal:controller.signal});
  let invocation:Promise<unknown>|undefined;
  let started=false;
  const settled=()=>{started=false;controller.abort();};
  return {
    get signal(){return controller.signal;},
    get started(){return started;},
    get completion(){if(!invocation)throw Error("session has not started");return invocation;},
    start(){
      if(invocation)return;
      started=true;
      invocation=workflow.runWorkflowAsync({}, {capabilities,signal:controller.signal,entry});
      invocation.then(settled,settled);
    },
    async stop(){
      controller.abort();
      try{await invocation;}catch(error){if((error as {code?:string})?.code!=="VF_ABORTED")throw error;}
    },
  };
}
