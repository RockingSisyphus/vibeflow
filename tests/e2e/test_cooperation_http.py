"""Official AOT Nodes must cross the HTTP boundary from owned Python workers."""
import asyncio
from pathlib import Path
import shutil

from tests.e2e.async_cases import async_case
from tests.e2e.cooperation import CASES, prepare, reference, verify_rows
from vibeflow.coordination import WorkflowClient, WorkflowServer
from vibeflow.targets.python.runtime.workflow_host import bind_workflow, run_connected
from vibeflow.tooling.application.python import load_bundle
from tests.e2e.support import cli


@async_case
async def test_official_aot_send_from_worker_through_http_and_in_process_targets(tmp_path):
    fixture = Path(__file__).resolve().parents[2] / "sandbox/python/workflow_cooperation_math"
    output = prepare(fixture, tmp_path, "python")
    bundles = {}
    for name in ("a", "b", "c"):
        cli(tmp_path, "build", "--workspace", tmp_path / "vibeflow_config.jsonc", "--config",
            tmp_path / f"project/configs/{name}.jsonc", "--out-dir", output / name)
        bundles[name] = load_bundle(output / name)
    shutil.rmtree(tmp_path / "project")
    launches = [{**call, "caller": reference("a")} for call in bundles["a"].workflow_descriptor["calls"]
                if call["operation"] == "call"]
    for profile in ("plan", "block", "compiled"):
        server = WorkflowServer(launches=launches)
        def factory(bundle):
            def runtime(**options):
                return bundle.create_runtime(run_dir=output / profile / options["workflow_instance_id"],
                                             runtime_options={"execution": profile}, **options)
            return runtime
        for name in ("b", "c"):
            bind_workflow(server.coordinator, bundles[name].workflow_descriptor, factory(bundles[name]))
        with server:
            results = await asyncio.wait_for(asyncio.gather(*(run_connected(factory(bundles["a"]),
                workflow=reference("a"), initial=case, url=server.url) for case in CASES)), 30)
            rows = [item["computed"] for item in results]
            verify_rows(rows)
            observer = await WorkflowClient.open(server.url)
            try:
                for row in rows:
                    for role in ("a", "b"):
                        ended = await observer.wait(row["identities"][role], timeout=2)
                        assert ended["state"] == "succeeded", ended
                    assert (await observer.wait(row["identities"]["b"]))["outputs"]["computed"]["d"] == row["stages"]["d"]
            finally:
                await observer.finish()
