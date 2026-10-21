"""One fresh interpreter per helper-source stage; no module cache is shared."""
import json
import os
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPOSITORY), str(REPOSITORY / "src")]
sys.dont_write_bytecode = True
from tests.fixtures.support.artifacts import artifact_directory
from tests.fixtures.support.addition_sandboxes import value, events, PLUGIN_EXPECTED, assert_artifacts
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.tooling.application.python.project.core import build_workspace_environment
from vibeflow.tooling.application.python.workspace_service import _prepare_workspace_graph, run_workspace_checked
from vibeflow.tooling.project.workspace_loader import load_workspace_config

work = Path(sys.argv[1])
os.chdir(work)
output = artifact_directory(work)
loaded = load_workspace_config(work / "vibeflow_config.jsonc")
observations = []
for config_name, expected_values in PLUGIN_EXPECTED[work.name].items():
    inputs, result = {"a": 2}, expected_values[0]
    config = work / "project/configs" / (config_name + ".jsonc")
    marker = work / "hooks.jsonl"
    before = len(events(marker)) if marker.exists() else 0
    checked = run_workspace_checked(config, workspace=loaded, initial=inputs, run_root=output / "runs", run_id=config_name, runtime_options=RuntimeOptions(trace="full"))
    assert value(checked.context, "result") == result
    hooks = events(marker)[before:]
    kinds = [item["hook"] for item in hooks]
    assert "after_compile" in kinds and kinds.count("before_nodeset") == 1 and kinds.count("after_run") == 1
    assert kinds.count("before_node") == kinds.count("after_node") == 5, hooks
    assert_artifacts(checked.run_dir)
    environment = build_workspace_environment(loaded, config_path=config)
    prepared = _prepare_workspace_graph(config, workspace=loaded, env=environment)
    libraries = prepared.resources.base_libs
    assert len(libraries) == 1 and libraries[0].id == "addition.math", libraries
    files = libraries[0].descriptor.implementations[0].implementation_files
    assert [Path(item.ref).name for item in files] == ["math_support.py"]
    node = environment.registry.descriptor("addition.add")
    assert [Path(item.ref).name for item in node.implementations[0].implementation_files] == ["node_support.py"]
    declarations = [item.declaration for item in prepared.plugin_registry.descriptors()]
    assert declarations and all(
        [Path(item.ref).name for item in declaration.implementations[0].implementation_files] == ["plugin_support.py"]
        for declaration in declarations
    )
    if config_name == "default":
        for a, wanted in zip([10, -2], expected_values[1:]):
            runtime = PipelineRuntime(prepared.graph, registry=environment.registry, plugin_registry=prepared.plugin_registry, run_dir=output / "runtime" / str(a))
            context = runtime.run({"a": a})
            assert value(context, "result") == wanted
            observations.append({"a": a, "b": 3, "result": wanted})
    observations.append({"config": config_name, "result": result, "hooks": kinds,
        "checks": {name:"PASS" for name in ("result", "compiler_and_runtime_hooks", "source_ownership", "artifacts")}})
print(json.dumps({"observations": observations}))
