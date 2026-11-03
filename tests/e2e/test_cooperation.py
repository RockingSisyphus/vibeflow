"""Actual cooperative workflow hosts, cancellation and wrong-result controls."""
import asyncio
import json
from pathlib import Path
import shutil
import inspect
import pytest
from vibeflow.coordination import Coordinator,CoordinationError
from vibeflow.targets.python.runtime.workflow_host import bind_workflow
from vibeflow.tooling.application.python import load_bundle
from tests.e2e.async_cases import async_case
from tests.e2e.support import ROOT,cli,command,write
from tests.e2e.cooperation import CASES,CANCEL_CASE,FAULTS,expected,prepare,reference,set_fault,verify_rows,verify_cancelled

async def exercise(scope, *, timeout=45):
    try:
        immediate = scope.invoke_sync({"workflow": reference("c"), "inputs": {
            "request": {"u": 13, "v": 3, "case_id": "direct"}}})
        assert not inspect.isawaitable(immediate) and immediate["computed"]["p"] == 64
        try:
            scope.invoke_sync({"workflow": reference("a"), "inputs": CASES[0]})
        except CoordinationError as error:
            assert error.code == "VF_WORKFLOW_SYNC_UNSUPPORTED", error
        else:
            raise AssertionError("async workflow accepted by InvokeSync")
        ended = await asyncio.wait_for(asyncio.gather(*(scope.run(reference("a"), case) for case in [*CASES, CANCEL_CASE])), timeout)
        assert all(item["state"] == "succeeded" for item in ended), ended
        rows = [item["outputs"]["computed"] for item in ended[:-1]]
        cancelled = ended[-1]["outputs"]["computed"]
        verify_cancelled(cancelled)
        stopped = await scope.session(ended[-1]["id"]).wait({"id":cancelled["identities"]["b"]})
        assert stopped["state"] == "cancelled" and stopped["outputs"] is None, stopped
        assert len({identity for row in [*rows,cancelled] for identity in row["identities"].values()}) == 3*(len(CASES)+1)
        verify_rows(rows)
        for item, row in zip(ended, rows):
            assert item["id"] == row["identities"]["a"]
            repeated = await scope.session(item["id"]).wait({"id": row["identities"]["b"]})
            assert repeated["outputs"]["computed"]["d"] == row["stages"]["d"]
        for identifier in [item["id"] for item in ended] + [row["identities"]["b"] for row in [*rows, cancelled]]:
            scope.release(identifier)
        return {"rows": rows, "cancelled":cancelled}
    finally:
        await scope.aclose()


def bind_bundles(bundles, output, execution):
    scope = Coordinator()
    for bundle in bundles.values():
        def factory(bundle=bundle, **options):
            return bundle.create_runtime(run_dir=output / options["workflow_instance_id"],
                                         runtime_options={"execution": execution, "trace": "full"}, **options)
        bind_workflow(scope, bundle.workflow_descriptor, factory)
    return scope


@pytest.fixture(scope="module")
def cooperative_bundles(tmp_path_factory):
    work=tmp_path_factory.mktemp("cooperative-python")
    output=prepare(ROOT / "sandbox/python/workflow_cooperation_math",work,"python")
    def build(name,label):
        cli(work,"build","--workspace",work / "vibeflow_config.jsonc","--config",
            work / f"project/configs/{name}.jsonc","--out-dir",output / label)
        return load_bundle(output / label)
    bundles={name:build(name,name) for name in ("a","b","c")}
    faulty={}
    for fault in FAULTS:
        set_fault(work,"python",fault)
        faulty[fault]=build("a",fault)
    shutil.rmtree(work / "project")
    return bundles,faulty,output

@pytest.mark.parametrize("execution",["plan","block","compiled"])
@async_case
async def test_cooperative_formula_isolation_and_cancellation(cooperative_bundles,execution):
    bundles,faulty,output=cooperative_bundles
    result=await exercise(bind_bundles(bundles,output / execution,execution))
    verify_rows(result["rows"])
    verify_cancelled(result["cancelled"])

@async_case
async def test_cooperative_independent_oracle_rejects_wrong_user_graphs(cooperative_bundles):
    bundles,faulty,output=cooperative_bundles
    for fault,wrong in FAULTS.items():
        scope=bind_bundles({**bundles,"a":faulty[fault]},output / ("wrong-"+fault),"compiled")
        try:
            ended=await asyncio.wait_for(scope.run(reference("a"),CASES[0]),15)
            assert ended["state"]=="succeeded",ended
            actual=ended["outputs"]["computed"]["result"]
            assert actual==wrong and actual!=expected(CASES[0]),(fault,ended)
        finally:await scope.aclose()
