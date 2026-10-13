import type {TaskManagerContext, TaskRef} from "@vibeflow/plugin";
export async function run(inputs: any, params: any, context: TaskManagerContext) {
  const scenario = inputs["fixture.scenario"].value;
  const refs: TaskRef[] = [];
  for (const label of ["A", "B", "C"]) {
    refs.push(context.tasks.start("worker", {"fixture.request": {label, scenario}}));
  }
  if (scenario === "selective") {
    await new Promise(resolve=>setTimeout(resolve,0));
    const extra=context.tasks.start("worker", {"fixture.request":{label:"D",scenario:"success"}});
    if(new Set([...refs,extra].map(ref=>ref.task_id)).size!==4)throw new Error("task identity reused");
    context.tasks.requestStop([refs[1]]);
    await context.tasks.waitAllExited([refs[1]]);
    if((await context.tasks.waitAny([extra]))!.status!=="succeeded")throw new Error("wrong instance stopped");
    context.tasks.requestStop([refs[0],refs[2]]);
  } else if(scenario === "invalid_refs") {
    await new Promise(resolve=>setTimeout(resolve,0));
    for(const operation of [()=>context.tasks.start("undeclared",{}),
        ()=>context.tasks.waitAny([{run_id:"foreign",task_id:"1"}]),
        ()=>context.tasks.waitAny([{run_id:refs[0].run_id,task_id:"unknown"}])]) {
      try {await operation();}catch(error:any){context.trace("expected_contract_error",{code:error.code});continue;}
      throw new Error("invalid operation accepted");
    }
    context.tasks.requestStop(refs);
  } else if(scenario==="root_failure" || scenario==="unobserved_failure") {
    await context.tasks.waitAllExited([refs[0]]);
    if(scenario==="root_failure")throw new Error("parent failed after starting B and C");
  }
  if (scenario === "failure" || scenario === "unexpected_failure" || scenario === "cleanup_failure") {
    const first = await context.tasks.waitAny(refs);
    context.trace("first_outcome", {outcome:first});
    context.tasks.requestStop(refs.filter(ref=>ref.task_id !== first!.task.task_id));
  } else if (scenario === "stop_return" || scenario === "stop_wait" || scenario === "uncooperative") {
    // Let each task enter its own wait; this is a one-shot Node-owned timer.
    await new Promise(resolve=>setTimeout(resolve, 0));
    context.tasks.requestStop(refs);
    if (scenario === "stop_wait") await context.tasks.waitAllExited(refs);
  }
  context.trace("manager_return", {scenario});
  return {"fixture.refs": refs};
}
