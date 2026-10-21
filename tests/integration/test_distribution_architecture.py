"""Architecture freshness through real launchers from extracted release ZIPs."""

import json
import os
import subprocess
import sys
import zipfile

import pytest

from distribution.build import ARCHIVE_ROOT_NAME, build_release_set
from vibeflow.tooling.project.config_loader import strip_jsonc_comments


@pytest.fixture(scope="module")
def releases(tmp_path_factory):
    root = tmp_path_factory.mktemp("architecture-releases")
    return build_release_set(
        root / "collaborative",
        autonomous_output=root / "autonomous",
        archive_dir=root / "archives",
        run_self_check=False,
    )


@pytest.fixture(params=["collaborative", "autonomous"])
def distribution(releases, request, tmp_path):
    with zipfile.ZipFile(getattr(releases, request.param).archive) as archive:
        archive.extractall(tmp_path)
    root = tmp_path / ARCHIVE_ROOT_NAME
    _command(root, ["npm", "ci", "--prefix", "javascript_project"])
    return root


def _command(root, arguments, *, expected=0, hash_seed=None):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if hash_seed is not None:
        environment["PYTHONHASHSEED"] = str(hash_seed)
    completed = subprocess.run(arguments, cwd=root, env=environment,
                               text=True, capture_output=True, check=False)
    assert completed.returncode == expected, completed.stdout + completed.stderr
    return completed


def _architecture(root, *, check=False, config="main.jsonc", output="ARCHITECTURE.jsonc", hash_seed=None):
    # -I ignores PYTHONHASHSEED; the launcher already pins its own ZIP kernel.
    return _command(root, [sys.executable, "run.py", "architecture",
        "--config", "javascript_project/configs/" + config,
        "--output", "javascript_project/" + output, *(["--check"] if check else [])], hash_seed=hash_seed)


def test_javascript_architecture_immediate_check_passes(distribution):
    _architecture(distribution)
    _architecture(distribution, check=True)


def test_javascript_architecture_repeated_exports_are_identical(distribution):
    output = distribution / "javascript_project/ARCHITECTURE.jsonc"
    _architecture(distribution)
    first = output.read_bytes()
    _architecture(distribution)
    assert output.read_bytes() == first
    document = json.loads(strip_jsonc_comments(first.decode("utf-8")))
    states = document["rule_checks"]["facts"]["source_load_states"]
    assert states["nodes/process_payload.ts"] == "loaded"
    assert not any("vibeflow-js-resources-" in path for path in states)


def test_javascript_architecture_still_detects_workflow_changes(distribution):
    _architecture(distribution)
    config = distribution / "javascript_project/configs/main.jsonc"
    document = json.loads(strip_jsonc_comments(config.read_text(encoding="utf-8")))
    document["pipeline"]["nodes"][2]["description"] = "Changed processing description"
    config.write_text(json.dumps(document), encoding="utf-8")
    completed = _command(distribution, [sys.executable, "-I", "run.py", "architecture",
        "--config", "javascript_project/configs/main.jsonc",
        "--output", "javascript_project/ARCHITECTURE.jsonc", "--check"], expected=1)
    assert json.loads(completed.stdout)["code"] == "ARCHITECTURE.DOCUMENT.STALE"


def test_planned_nodeset_architecture_is_identical_across_hash_seeds(distribution):
    # Call order differs from both import order and alphabetical order.
    names = ("zeta", "alpha", "epsilon", "beta", "gamma", "delta")
    project = distribution / "javascript_project"
    directory = project / "configs/planned_nodesets"
    directory.mkdir()
    nodes = [{"id": "start", "definition_id": "minimal.start", "display_name": "Start",
              "description": "Starts the planned Nodeset order regression."}]
    for name in names:
        document = {"type_key": "repro." + name, "display_name": name,
            "description": "Transparent planned Nodeset for order regression.",
            "status": "planned", "planned_behavior": "transparent", "requires": [], "provides": []}
        (directory / (name + ".jsonc")).write_text(json.dumps(document), encoding="utf-8")
        nodes.append({"id": name, "definition_id": document["type_key"], "display_name": name,
            "description": document["description"], "status": "planned", "planned_behavior": "transparent",
            "flow_kind": "process", "requires": [], "provides": []})
    nodes.append({"id": "end", "definition_id": "minimal.end", "display_name": "End",
                  "description": "Ends the planned Nodeset order regression."})
    document = {"pipeline": {"inputs": [], "outputs": [], "nodes": nodes,
        "edges": [[left["id"], right["id"]] for left, right in zip(nodes, nodes[1:])]},
        "plugins": [{"source": {"kind": "file", "ref": "plugins/code_plugin/plugin.ts", "export": "plugin"}}],
        "nodeset_imports": [{"path": "planned_nodesets/" + name + ".jsonc"} for name in reversed(names)]}
    (project / "configs/planned_order.jsonc").write_text(json.dumps(document), encoding="utf-8")
    options = {"config": "planned_order.jsonc", "output": "PLANNED_ORDER_ARCHITECTURE.jsonc"}
    _architecture(distribution, hash_seed=1, **options)
    output = project / options["output"]
    first = output.read_bytes()
    checks = json.loads(strip_jsonc_comments(first.decode("utf-8")))["rule_checks"]
    assert [finding["object_id"] for finding in checks["findings"]
            if finding["code"] == "GRAPH.PLANNED.NODESET"] == ["repro." + name for name in names]
    for seed in (1, 2, 3, "random"):
        _architecture(distribution, check=True, hash_seed=seed, **options)
        _architecture(distribution, hash_seed=seed, **options)
        # Compare the whole document, including every subject, Rule finding and events record.
        assert output.read_bytes() == first
