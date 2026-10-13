import type {NodeRunContext} from "@vibeflow/plugin";
export async function run(inputs: any, params: any, context: NodeRunContext) {
  const {label, scenario} = inputs["fixture.request"].value;
  context.trace("worker_started", {label});
  let listener: (()=>void) | undefined;
  try {
    if (["failure","cleanup_failure","concurrent_failure","unobserved_failure"].includes(scenario) && (label==="B" || ["concurrent_failure","unobserved_failure"].includes(scenario))) throw new Error("B failed deliberately");
    if (scenario === "unexpected_failure" && label === "B") {
      const missing: any = undefined;
      missing.value;
    }
    if (scenario === "uncooperative") {
      await new Promise(resolve=>setTimeout(resolve,40));
      context.trace("underlying_finished", {label});
      return {"fixture.value":label};
    }
    if (scenario === "success" || scenario === "root_failure" && label === "A") return {"fixture.value": label};
    await new Promise<void>(resolve=>{
      listener = resolve;
      context.signal!.addEventListener("abort", listener, {once:true});
      if (context.signal!.aborted) resolve();
    });
    return {"fixture.value": label};
  } finally {
    if (listener) context.signal!.removeEventListener("abort", listener);
    context.trace("cleanup_started", {label});
    await new Promise(resolve=>setTimeout(resolve, scenario==="unobserved_failure" && label==="A" ? 80 : 40));
    context.trace("cleanup_finished", {label});
    if(scenario==="cleanup_failure" && label==="B")throw new Error("B cleanup failed",{cause:new Error("B failed deliberately")});
  }
}
