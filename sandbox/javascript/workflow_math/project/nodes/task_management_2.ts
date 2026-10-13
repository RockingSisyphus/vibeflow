import type {TaskManagerContext} from "@vibeflow/plugin";
export async function run(inputs: any, params: any, context: TaskManagerContext) {
  const ref=context.tasks.start("work", {});
  return {};
}
