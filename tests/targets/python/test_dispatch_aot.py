"""A local dispatch budget survives moved bundles and call overrides."""

import json
from pathlib import Path
import shutil

from tests.fixtures.support.addition_sandboxes import workspace
from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
from vibeflow.tooling.application.python.bundle import load_bundle


def test_moved_bundle_keeps_dispatch_capacity_and_local_overrides(tmp_path):
    fixture = Path(__file__).resolve().parents[3] / "sandbox/python/graph_concurrency"
    source = tmp_path / "source"
    source.mkdir()
    config_workspace = workspace(fixture, source)
    config = source / "project/configs/concurrent.jsonc"
    data = json.loads(config.read_text())
    data["pipeline"]["nodes"][0]["config"] = {"max_concurrency": 4}
    config.write_text(json.dumps(data))
    nodes = source / "project/nodes.py"
    nodes.write_text(nodes.read_text().replace("Barrier(12)", "Barrier(2)"))
    built = build_python_aot(PythonBuildRequest(config_workspace, config, tmp_path / "built"))
    moved = tmp_path / "moved"
    built.out_dir.rename(moved)
    shutil.rmtree(source)
    bundle = load_bundle(moved)
    for count in (4, 2):
        runtime = bundle.create_runtime(run_dir=tmp_path / f"run-{count}",
            node_config_overrides={"start": {"max_concurrency": count}},
            global_config={"max_concurrency": 1})
        assert runtime._frames["start"].max_concurrency == count
        assert "max_concurrency" not in runtime._frames["start"].params
        assert runtime._frames["collect"].max_concurrency == 8
        result = runtime.run({"scenario": "success"})
        assert result.get("report")["value"] == list(range(12))
