import type {TaskManagerContext, TaskRef} from "@vibeflow/plugin";
export async function run(inputs: any, params: any, context: TaskManagerContext) {
  const refs: TaskRef[] = inputs["fixture.forwarded"].value;
  const results = await context.tasks.waitAllExited([...refs, refs[0]]);
  const repeated = await context.tasks.waitAny([refs[1]]);
  if (repeated!.task.task_id !== results[1].task.task_id) throw new Error("late outcome lost");
  if (await context.tasks.waitAny([]) !== null) throw new Error("empty waitAny");
  if ((await context.tasks.waitAllExited([])).length) throw new Error("empty waitAllExited");
  if (context.tasks.requestStop(refs).some(ack=>ack.state !== "already_exited")) throw new Error("completed task still active");
  context.trace("control_joined");
  return {"fixture.report": results};
}
