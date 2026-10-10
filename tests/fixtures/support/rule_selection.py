"""Shared assertions for two public SDK projects; no mock Rule handlers."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter

REPOSITORY = Path(__file__).resolve().parents[3]


def run(fixture, work, toolchain=None):
    started = perf_counter()
    project = work / "project"
    shutil.copytree(fixture / "project", project, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    shutil.copy2(fixture / "vibeflow_config.jsonc", work / "vibeflow_config.jsonc")
    target = fixture.parent.name
    if target == "javascript":
        modules = toolchain / "node_modules" if toolchain else None
        if modules and modules.is_dir():
            (project / "node_modules").symlink_to(modules.resolve(), target_is_directory=True)
        else:
            subprocess.run(["npm", "ci", "--ignore-scripts"], cwd=project, check=True)
    observations = []
    for name in ("default", "dynamic", "empty"):
        command = [sys.executable, "-m", "vibeflow", "validate", "--workspace", str(work / "vibeflow_config.jsonc"),
                   "--config", str(project / "configs" / (name + ".jsonc")), "--json"]
        result = subprocess.run(command, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(REPOSITORY / "src"), "PYTHONDONTWRITEBYTECODE":"1"})
        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads(result.stdout)
        (work / (name + "-health.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        proofs = [item for item in report["warnings"] if item["rule_id"].startswith("SELECTION.")]
        graphs = [item["details"] for item in proofs if item["rule_id"] == "SELECTION.GRAPH"]
        local_all = [item["details"] for item in proofs if item["rule_id"] == "SELECTION.LOCAL"]
        local = [item for item in local_all if item["phase"] == "static"]
        assert Counter(tuple(item["path"]) for item in local_all if item["phase"] == "import") == Counter([("direct",)]), local_all
        expected = {"default":[(),("left",),("right",),("takeover",)],
                    "dynamic":[(),("takeover",)], "empty":[("takeover",)]}[name]
        assert Counter(tuple(item["entry"]) for item in graphs) == Counter(expected), graphs
        assert all(item["label"] == ("selection.child" if item["entry"] == ["takeover"] else "selection.whole" if name == "dynamic" else "selection.default") for item in graphs), graphs
        covered = [tuple(graph["path"]) for item in graphs for graph in item["graphs"]]
        expected_covered = [(),("left",),("right",),("takeover",)] if name != "empty" else [("takeover",)]
        assert Counter(covered) == Counter(expected_covered), graphs
        assert all(item["phase"] == "static" and "muted" in item["background_nodes"] for item in graphs), graphs
        root_proof = next((item for item in graphs if item["entry"] == []), None)
        if root_proof:
            assert "takeover" in root_proof["graphs"][0]["nodes"] and "muted" in root_proof["graphs"][0]["nodes"], root_proof
        assert Counter(tuple(item["path"]) for item in local) == Counter([
            ("direct",),("left","local"),("right","local"),("takeover","local"),("muted","local")]), local
        assert all(not item["forbidden"] and item["phase"] == "static" for item in local), local
        observations.append({"config":name,"graph_executions":len(graphs),"covered_paths":covered,
                             "local_paths":[item["path"] for item in local]})
    payload = {"status":"PASS","target":target,"seconds":round(perf_counter()-started,3),"observations":observations}
    (work / "report.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    print(f"{target} rule selection: PASS configs=3 report={work / 'report.json'}")
    return payload


def main(fixture):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--toolchain-root", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vibeflow-rule-selection-") as temporary:
        work = args.work_dir.resolve() if args.work_dir else Path(temporary)
        work.mkdir(parents=True,exist_ok=True)
        run(fixture,work,args.toolchain_root)
