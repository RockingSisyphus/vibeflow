import {runWorkflowAsync} from "@vibeflow/workflow";
import {createBrowserSession} from "./browser_session.ts";

document.addEventListener("vibeflow-sandbox-request-workflow", event=>{
  const request=event as CustomEvent<{resolve:(value:unknown)=>void}>;
  request.detail.resolve({runWorkflowAsync,createSession:(entry?:string)=>createBrowserSession({runWorkflowAsync},entry)});
});
