export async function run(inputs: any, params: any, context: any) {const ref=context.tasks.start("work", {});await context.tasks.waitAllExited([ref]);return {};}
