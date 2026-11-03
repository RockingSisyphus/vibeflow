import {runWorkflowAsync} from "@vibeflow/workflow";
import {createBrowserSession} from "./browser_session.ts";

let session:ReturnType<typeof createBrowserSession>|undefined;
let hostId=0;
const state=document.querySelector<HTMLOutputElement>('#state')!;
const history=document.querySelector<HTMLOutputElement>('#history')!;
const messages:number[]=[];
window.addEventListener('message',event=>{
  if(event.source!==window)return;
  if(event.data.kind==='vibeflow-sandbox-lifecycle'){
    state.textContent=event.data.phase==='start'?'运行中':'已停止';
    if(event.data.phase==='start')window.postMessage({kind:'vibeflow-sandbox-bind',hostId},'*');
  }
  if(event.data.kind==='vibeflow-sandbox-output'&&event.data.hostId===hostId){
    messages.push(event.data.value);history.textContent=JSON.stringify(messages);
  }
});
document.querySelector('#start')!.addEventListener('click',()=>{
  if(session?.started)return;
  hostId++;
  session=createBrowserSession({runWorkflowAsync});
  session.start();
  session.completion.catch(error=>{if(error.code!=='VF_ABORTED')state.textContent=error.message;});
});
document.querySelector('#send')!.addEventListener('click',()=>{
  const value=Number(document.querySelector<HTMLInputElement>('#value')!.value);
  window.postMessage({kind:'vibeflow-sandbox-input',hostId,value},'*');
});
document.querySelector('#stop')!.addEventListener('click',async()=>{
  await session?.stop();
});
