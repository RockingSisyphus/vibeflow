import {runWorkflowAsync} from "@vibeflow/workflow";
const button=document.querySelector<HTMLButtonElement>("#run")!;
const output=document.querySelector<HTMLOutputElement>("#output")!;
button.addEventListener("click", async ()=>{
 const trace: unknown[]=[];
 try {
  const result=await runWorkflowAsync({scenario:"failure"},{trace:"full",onTrace:event=>trace.push(event)});
  output.textContent=JSON.stringify({result,trace});
 } catch(error) {output.textContent=JSON.stringify({error:String(error),trace});}
});
