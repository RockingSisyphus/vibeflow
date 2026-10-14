import type {TaskManagerContext, TaskRef} from "@vibeflow/plugin";
export async function run(inputs: any, params: any, context: TaskManagerContext) {
  const refs: TaskRef[] = inputs["fixture.forwarded"].value;
  const results = [...inputs["fixture.finished.forwarded"].value,
    ...await context.tasks.waitAllExited([...refs, ...refs.slice(0,1)])];
  results.sort((a,b)=>Number(a.task.task_id)-Number(b.task.task_id));
  if (await context.tasks.waitAny([]) !== null) throw new Error("empty waitAny");
  if ((await context.tasks.waitAllExited([])).length) throw new Error("empty waitAllExited");
  if(refs.length){
    try {await context.tasks.waitAny(refs);throw new Error("consumed result retained");}
    catch(error:any){if(error.code!=="VF_TASK_REF_INVALID")throw error;}
  }
  context.trace("control_joined");
  return {"fixture.report": results};
}
