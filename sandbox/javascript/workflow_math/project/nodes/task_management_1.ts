import type {TaskManagerContext} from "@vibeflow/plugin";
export async function run(inputs: any, params: any, context: TaskManagerContext) {
  const outcome=(await context.tasks.waitAllExited([inputs["task.ref.sandbox_async_double"].value]))[0];
  if(outcome.status!=="succeeded")throw new Error(outcome.error!.message);
  return {doubled:outcome.outputs!.doubled};
}
