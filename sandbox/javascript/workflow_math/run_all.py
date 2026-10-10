"""One reusable arithmetic project for nesting, loops, tasks and trace settings."""
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
FIXTURE = Path(__file__).resolve().parent
ROOT = FIXTURE.parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "sandbox/javascript/integration")]
from tests.fixtures.support.addition_sandboxes import main, workspace
from vibeflow.targets.javascript.build.driver_session import check_scope


@check_scope
def run(work, *, toolchain=None):
    workspace(FIXTURE, work, toolchain)
    os.environ["VIBEFLOW_SANDBOX_RUNTIME_ROOT"] = str(work)
    from sandbox_support import BuildCache, run_node
    from advanced_cases import nested_override_case, nested_async_case, edge_role_case, execution_model_case, loop_max_error_case
    from runtime_cases import loop_case
    cache = BuildCache(work / "build")
    def build(name):
        return cache.build(name, name + ".jsonc")
    observations = []
    # Existing assertion helpers preserve the old path, route and task checks.
    for name, invoke in [
        ("nested_override", lambda: nested_override_case(build("nested_override").entry)),
        ("loop", lambda: loop_case(build("loop").entry)),
        ("loop_max_failure", lambda: loop_max_error_case(build("loop_max_failure").entry)),
        ("edge_roles", lambda: edge_role_case(build("edge_roles"))),
        ("nested_async", lambda: nested_async_case(build("nested_async"))),
        ("task_metadata", lambda: execution_model_case(build("linear"), build("async_capability"), build("detached"))),
    ]:
        observations.append(dict(config=name, result=invoke(), checks={"migrated_assertions":"PASS"}))
    nested = build("nested_loop")
    result = run_node(nested.entry, '''
const trace = [];
const result = workflow.runWorkflow({x:4}, {trace:"full",onTrace:e=>trace.push(e)});
assert(result.result === 10 && result.iterations === 2, JSON.stringify(result));
const iterations = trace.filter(e=>e.kind==="loop_iteration");
assert(iterations.length === 8, JSON.stringify(iterations));
const nodes = trace.filter(e=>e.kind==="node_start").map(e=>e.nodePath);
assert(nodes.filter(p=>p.endsWith("increment")).length === 6, JSON.stringify(nodes));
process.stdout.write(JSON.stringify({result,nodes,iterations}));
''')
    observations.append(dict(config="nested_loop",result=result,checks={"two_by_three_additions":"PASS","iteration_paths":"PASS"}))
    # Reuse the same AOT output; only trace selection and input state change.
    result = run_node(build("nested_override").entry, '''
const rows=[];
for (const level of ["full","boundary","off"]) {
  const trace=[];
  const result=workflow.runWorkflow({x:5},{trace:level,onTrace:e=>trace.push(e)});
  assert(result.result===19 && result.defaultResult===11, JSON.stringify(result));
  const kinds=trace.map(e=>e.kind);
  if(level==="full") assert(kinds.includes("node_start"), JSON.stringify(kinds));
  if(level==="boundary") assert(!kinds.includes("node_start") && kinds.includes("nodeset_enter"), JSON.stringify(kinds));
  if(level==="off") assert(kinds.length===0, JSON.stringify(kinds));
  rows.push({level,result,kinds});
}
process.stdout.write(JSON.stringify(rows));
''')
    observations.append(dict(config="trace_matrix",result=result,checks={"same_build_three_trace_modes":"PASS"}))
    return dict(status="PASS",observations=observations)


if __name__ == "__main__":
    main(run, "JavaScript workflow math", javascript=True)
