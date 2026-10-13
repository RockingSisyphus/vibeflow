"""Actual AOT builds and executions for parallel conditional call routes."""
from copy import deepcopy
import json


def run_conditional_routes(cache, work, run_node):
    config_root = work / "project/configs"
    original = json.loads((config_root / "conditional_routes.jsonc").read_text())
    routes = original["pipeline"]["edges"][1:3]
    variants = {
        "forward": routes,
        "reverse": routes[::-1],
        "exact_duplicate": [*routes, routes[0]],
        "overlap": [*routes, {**routes[0], "when": "route != 'failed'"}],
    }
    observations = []
    for mode in ("sync", "async"):
        for variant, selected in variants.items():
            config = deepcopy(original)
            config["pipeline"]["entry_mode"] = mode
            config["pipeline"]["edges"][1:3] = selected
            name = f"conditional_routes_{mode}_{variant}"
            # Variants and outputs stay in the copied, temporary project.
            (config_root / f"{name}.jsonc").write_text(json.dumps(config, indent=2) + "\n")
            built = cache.build(name, f"{name}.jsonc")
            result = run_node(built.entry, '''
const rows = [];
for (const event of ["done", "failed", "unknown"]) {
  const trace = [];
  const shouldFinish = event !== "unknown" || VARIANT === "overlap";
  let result, error;
  try {
    result = await workflow.RUN({event}, {trace:"full", onTrace:e=>trace.push(e)});
  } catch (cause) { error = cause.code; }
  if (shouldFinish) assert(error === undefined && result?.result === 43,
    JSON.stringify({event, result, error}));
  else assert(error === "VF_OUTPUT_CARDINALITY", JSON.stringify({event, result, error}));
  const finishes = trace.filter(e=>e.kind === "node_start" && e.nodeId === "finish_call").length;
  assert(finishes === (shouldFinish ? 1 : 0), JSON.stringify({event, finishes, trace}));
  rows.push({event, result, error, finishes});
}
process.stdout.write(JSON.stringify(rows));
'''.replace("VARIANT", json.dumps(variant)).replace(
                "workflow.RUN", "workflow.runWorkflowAsync" if mode == "async" else "workflow.runWorkflow"
            ))
            observations.append(dict(config=name, result=result, checks={
                "both_status_routes": "PASS", "finish_once": "PASS", "unknown_status_control": "PASS",
            }))
    return observations
