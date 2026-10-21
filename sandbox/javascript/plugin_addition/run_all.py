"""Check multi-file addition and compiler/runtime plugins across source edits."""
from pathlib import Path
import json
import sys
sys.dont_write_bytecode = True

FIXTURE = Path(__file__).resolve().parent
REPOSITORY = FIXTURE.parents[2]
sys.path[:0] = [str(REPOSITORY), str(REPOSITORY / "src"), str(REPOSITORY / "sandbox/javascript/integration")]
from tests.fixtures.support.artifacts import artifact_directory
from tests.fixtures.support.addition_sandboxes import main, workspace, PLUGIN_EXPECTED
from sandbox_support import run_node
from vibeflow.targets.javascript.build.driver_session import check_scope
from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot


@check_scope
def run(work, *, toolchain=None):
    workspace_path = workspace(FIXTURE, work, toolchain)
    output = artifact_directory(work)
    helper = work / "project/plugins/addition/math_support.ts"
    original = helper.read_text()
    observations = []
    for phase, code, expected in [("baseline", original, 5), ("edited", original.replace("a + b", "a + b + 1"), 6), ("restored", original, 5)]:
        helper.write_text(code)
        phase_rows = []
        for name, expected_values in PLUGIN_EXPECTED[phase].items():
            built = build_project_aot(ProjectBuildRequest(workspace=workspace_path, config=work / "project/configs" / (name + ".jsonc"), out_dir=output / (phase + "-" + name), target="node", profile="single-esm"))
            manifest = json.loads(built.manifest.read_text())
            plugins = manifest["target_metadata"]["plugins"]
            assert manifest["target_metadata"]["plugin_abi_version"] == "vibeflow.plugin.v4"
            assert [item["id"] for item in plugins["active"]] == ["addition.compiler", "addition.runtime"]
            assert len(plugins["declared"]) == 3 and plugins["planned"] == ["addition.future"]
            for item in plugins["active"]:
                assert len(item["source_hash"]) == len(item["config_hash"]) == 64 and item["completion"] == "immediate"
            assert [item["hook"] for item in plugins["annotations"]] == ["beforeCompile", "afterCompile"]
            entry = built.entry.read_text()
            assert "addition.compiler" not in entry and "addition.future" not in entry and "addition.runtime" in entry
            assert built.prepared.used_base_libs == ("addition.math",)
            library = next(item for item in built.prepared.catalogs.base_libs if item.id == "addition.math")
            assert [Path(item.ref).name for item in library.implementations[0].implementation_files] == ["math_support.ts"]
            node = built.prepared.catalogs.nodes.require("addition.add")
            assert [Path(item.ref).name for item in node.implementations[0].implementation_files] == ["node_support.ts"]
            for plugin_id, source in [("addition.compiler", "compiler_support.ts"), ("addition.runtime", "plugin_support.ts")]:
                plugin = built.prepared.catalogs.plugins.require(plugin_id)
                assert Path(plugin.implementations[0].source.ref).name == source
            wanted = expected_values[0]
            results = run_node(built.entry, f'''
assert(typeof workflow.runWorkflow === "function" && workflow.runWorkflow.constructor.name !== "AsyncFunction", "sync ABI changed");
const inputs = [2, 10, -2];
const expected = {json.dumps(expected_values)};
const values = inputs.map((a, index) => {{
  const trace = [];
  const value = workflow.runWorkflow({{a}}, {{trace:"full", onTrace:event=>trace.push(event)}});
  assert(!(value instanceof Promise) && value.result === expected[index], JSON.stringify(value));
  assert(trace.some(event=>event.kind==="run_start") && trace.some(event=>event.kind==="run_end"), JSON.stringify(trace));
  return value.result;
}});
process.stdout.write(JSON.stringify({{values, sync:true, repeatIsolation:true}}));
''')
            phase_rows.append({"config": name, "expected": wanted, **results,
                "checks": {condition:"PASS" for condition in ("results_and_repeat_isolation", "sync_abi", "manifest",
                    "compiler_annotations", "runtime_plugin_selection", "runtime_hooks", "source_ownership")}})
        observations.append({"phase": phase, "observations": phase_rows})
    return {"status": "PASS", "observations": observations}


if __name__ == "__main__":
    main(run, "JavaScript plugin addition", javascript=True)
