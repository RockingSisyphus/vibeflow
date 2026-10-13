import type {TaskManagerContext} from "@vibeflow/plugin";
export async function run(inputs:any, params:any, context:TaskManagerContext) {
  const ref=context.tasks.start("nested",{"fixture.scenario":inputs["fixture.scenario"].value});
  const outcome=(await context.tasks.waitAny([ref]))!;
  if(outcome.status!=="succeeded")throw new Error(JSON.stringify(outcome.error));
  context.trace("nested_joined");
  return {"fixture.report":outcome.outputs!["fixture.report"]};
}
