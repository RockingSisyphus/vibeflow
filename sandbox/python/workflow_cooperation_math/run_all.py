"""Three independent workflows, two message rounds and a synchronous subcall."""
import asyncio
import inspect
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
FIXTURE = Path(__file__).resolve().parent
ROOT = FIXTURE.parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from tests.fixtures.support.addition_sandboxes import main
from tests.fixtures.support.workflow_cooperation import CASES, CANCEL_CASE, FAULTS, expected, prepare, reference, set_fault, verify_rows, verify_cancelled
from vibeflow.coordination import Coordinator, CoordinationError
from vibeflow.targets.python.runtime.workflow_host import bind_workflow
from vibeflow.tooling.application.python import PythonBuildRequest, build_python_aot, load_bundle, run_workspace_checked, run_workspace_checked_async
from vibeflow.tooling.project.workspace_loader import load_workspace_config


class ObservedCoordinator(Coordinator):
    """Measure real runner overlap while delegating every protocol operation."""
    def __init__(self):
        super().__init__()
        self.active_parents = self.peak_parents = 0

    def bind(self, descriptor, runner):
        if descriptor["workflow"]["path"] != "configs/a.jsonc":
            return super().bind(descriptor, runner)
        async def observed(inputs, options):
            self.active_parents += 1
            self.peak_parents = max(self.peak_parents, self.active_parents)
            try:
                return await runner(inputs, options)
            finally:
                self.active_parents -= 1
        return super().bind(descriptor, observed)


async def exercise(scope, *, timeout=45):
    try:
        immediate = scope.invoke_sync({"workflow": reference("c"), "inputs": {
            "request": {"u": 13, "v": 3, "case_id": "direct"}}})
        assert not inspect.isawaitable(immediate) and immediate["computed"]["p"] == 64
        assert not scope.instances, "sync invocations must not retain records"
        try:
            scope.invoke_sync({"workflow": reference("a"), "inputs": CASES[0]})
        except CoordinationError as error:
            assert error.code == "VF_WORKFLOW_SYNC_UNSUPPORTED", error
        else:
            raise AssertionError("async workflow accepted by InvokeSync")
        ended = await asyncio.wait_for(asyncio.gather(*(scope.run(reference("a"), case) for case in [*CASES, CANCEL_CASE])), timeout)
        assert all(item["state"] == "succeeded" for item in ended), ended
        assert scope.peak_parents > 1 and scope.active_parents == 0, "parent workflows did not overlap"
        rows = [item["outputs"]["computed"] for item in ended[:-1]]
        cancelled = ended[-1]["outputs"]["computed"]
        verify_cancelled(cancelled)
        stopped = await scope.operations(ended[-1]["id"])["wait"]({"id":cancelled["identities"]["b"]})
        assert stopped["state"] == "cancelled" and stopped["outputs"] is None, stopped
        assert len({identity for row in [*rows,cancelled] for identity in row["identities"].values()}) == 3*(len(CASES)+1)
        verify_rows(rows)
        assert len(scope.instances) == 2*(len(CASES)+1), "only A/B terminal records may remain"
        for item, row in zip(ended, rows):
            assert item["id"] == row["identities"]["a"]
            repeated = await scope.operations(item["id"])["wait"]({"id": row["identities"]["b"]})
            assert repeated["outputs"]["computed"]["d"] == row["stages"]["d"]
        for identifier in list(scope.instances):
            scope.release(identifier)
        assert not scope.instances
        return {"rows": rows, "cancelled":cancelled, "peakParents": scope.peak_parents}
    finally:
        await scope.aclose()


def bind_bundles(bundles, output, execution):
    scope = ObservedCoordinator()
    for bundle in bundles.values():
        def factory(bundle=bundle, **options):
            return bundle.create_runtime(run_dir=output / options["workflow_instance_id"],
                                         runtime_options={"execution": execution, "trace": "full"}, **options)
        bind_workflow(scope, bundle.workflow_descriptor, factory)
    return scope


def bind_sources(bundles, workspace, output, execution):
    scope = ObservedCoordinator()
    for name, bundle in bundles.items():
        config = workspace.root / f"project/configs/{name}.jsonc"
        def execute(inputs, options, config=config, mode=bundle.workflow_descriptor["entry_mode"]):
            arguments = dict(workspace=workspace, initial=inputs, run_root=output,
                run_id=options["workflow_instance_id"], preview_root=output / "preview",
                runtime_options={"execution": execution, "trace": "full"}, **options)
            if mode == "sync":
                return run_workspace_checked(config, **arguments).public_outputs
            async def run():
                return (await run_workspace_checked_async(config, **arguments)).public_outputs
            return run()
        scope.bind(bundle.workflow_descriptor, execute)
    return scope


def run(work, *, toolchain=None):
    output = prepare(FIXTURE, work, "python")
    workspace = load_workspace_config(work / "vibeflow_config.jsonc")
    bundles = {name: load_bundle(build_python_aot(PythonBuildRequest(workspace,
        work / f"project/configs/{name}.jsonc", output / f"bundle-{name}")).out_dir) for name in ("a", "b", "c")}
    observations = []
    for execution in ("plan", "block", "compiled"):
        # Checked source runs repeat synchronous project preparation and auditing.
        # Give each parent its budget; AOT retains the execution-only 45s bound.
        result = asyncio.run(exercise(bind_sources(bundles, workspace, output / f"source-{execution}", execution),
                                      timeout=45*(len(CASES)+1)))
        observations.append({"execution": f"source-{execution}", "status": "PASS", **result})
    # Retain four intentionally wrong A builds: the independent oracle must
    # detect incorrect arithmetic/data wiring, rather than bless any number.
    faulty = {}
    for fault in FAULTS:
        set_fault(work, "python", fault)
        faulty[fault] = load_bundle(build_python_aot(PythonBuildRequest(workspace,
            work / "project/configs/a.jsonc", output / f"fault-{fault}")).out_dir)
    shutil.rmtree(work / "project")
    for execution in ("plan", "block", "compiled"):
        result = asyncio.run(exercise(bind_bundles(bundles, output / f"aot-{execution}", execution)))
        observations.append({"execution": f"aot-{execution}", "status": "PASS", **result})

    async def fault_cases():
        for fault, wrong in FAULTS.items():
            scope = bind_bundles({**bundles, "a": faulty[fault]}, output / f"fault-runs-{fault}", "compiled")
            try:
                ended = await asyncio.wait_for(scope.run(reference("a"), CASES[0]), 15)
                assert ended["state"] == "succeeded", ended
                actual = ended["outputs"]["computed"]["result"]
                assert actual == wrong and actual != expected(CASES[0]), (fault, ended)
                observations.append({"execution": "fault-control", "fault": fault, "status": "PASS",
                                     "observed": actual, "correct": expected(CASES[0])})
            finally:
                await scope.aclose()
    asyncio.run(fault_cases())
    return {"status": "PASS", "observations": observations}


if __name__ == "__main__":
    main(run, "Python multi-workflow cooperative formula")
