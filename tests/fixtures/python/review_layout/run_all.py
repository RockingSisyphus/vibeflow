#!/usr/bin/env python3
"""Strict formal-CLI layout observations over a selected VibeFlow kernel."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from tests.fixtures.python.review_layout.fixtures import write_project

CASES = json.loads((HERE / "cases.json").read_text())
RESOURCE_TITLES = {"plugins", "base_lib", "host_extensions"}


def user_resource_failures(text):
    return ["implementation details leaked into the user diagram: " + marker
            for marker in ("vf_resource_", "reference", "Node types", "Rule:", "Ruleset:", "contributes", " (type)")
            if marker in text]


def xml_titles(path):
    root = ET.parse(path).getroot()
    return [{"title":item.text, "x":float(item.get("x")), "y":float(item.get("y"))}
            for item in root if item.tag.endswith("}text") and item.get("class") == "review-title"]


def verify_sequence(text, identifiers):
    positions = [text.find(identifier + "@") for identifier in identifiers]
    return all(value >= 0 for value in positions) and positions == sorted(positions)


def verify_expanded(project, observation):
    failures = []
    frames = observation["frames"]
    columns = observation["columns"]
    if len(frames) != 9:
        failures.append(f"expected nine real Mermaid fragments, observed {len(frames)}")
    if len(columns) != 4 or columns[:3] != [["main pipeline"], ["plugins"], ["base_lib"]] or len(columns[-1]) != 2:
        failures.append("root columns must remain workflow, selected plugins, selected base_lib, then Nodeset/Loop panels")
    main = [item for item in frames if item["title"] == "main pipeline"]
    parents = [item for item in frames if item["title"] == "parent flow"]
    leaves = [item for item in frames if item["title"] not in {"main pipeline", "parent flow", *RESOURCE_TITLES}]
    if len(main) != 1 or main[0]["direction"] != "flowchart TD":
        failures.append("outer workflow must be vertical TD")
    if len(parents) != 2 or any(item["direction"] != "flowchart TD" for item in parents):
        failures.append("each parent body with children must be vertical TD")
    if len(leaves) != 4 or any(item["direction"] != "flowchart LR" for item in leaves):
        failures.append("each concrete leaf body must be horizontal LR")
    for frame in main + parents + leaves:
        if frame["resource_groups"] or frame["has_resource_nodes"]:
            failures.append("resource leakage into business fragment: " + frame["title"])
        if frame["title"] == "main pipeline":
            order = ["start", "outer_a", "outer_b", "loop", "end"]
        elif frame["title"] == "parent flow":
            order = ["outer_start", "inner_a", "inner_b", "inner_c", "outer_end"]
        else:
            order = ["a_start", "left", "right", "a_end"] if "layout.leaf_a" in frame["title"] else ["b_start", "middle", "b_end"]
        if not verify_sequence(Path(frame["mermaid_path"]).read_text(), order):
            failures.append("declared node order changed: " + frame["title"])
    resources = [item for item in frames if item["title"] in RESOURCE_TITLES]
    if [item["title"] for item in resources] != ["plugins", "base_lib"]:
        failures.append("missing the ordered user resource directories")
    else:
        text = "\n".join(Path(item["mermaid_path"]).read_text() for item in resources)
        if not all(value in text for value in ("id: layout.helper", "id: layout.resources", "resource_plugins -.-> resource_plugins_0", "resource_base_lib -.-> resource_base_lib_0")):
            failures.append("user resource directories lost a selected library or plugin package")
        if any(value in text for value in ("layout.resources.compiler", "layout.resources.runtime", "resource_plugins_1@")):
            failures.append("one selected plugin package must not become separate implementation cards")
        failures.extend(user_resource_failures(text))
        if any(item["direction"] != "flowchart LR" for item in resources):
            failures.append("user resource directories must preserve their native LR direction")
    if len(observation["panels"]) != 2:
        failures.append("missing nested parent/children panels")
    for panel in observation["panels"]:
        positions = panel["positions"]
        if len(positions) != 3 or positions[0]["title"] != "parent flow" or not (positions[0]["x"] < positions[1]["x"] == positions[2]["x"] and positions[0]["y"] == positions[1]["y"] < positions[2]["y"]):
            failures.append("child Nodesets must stack on the right of their parent")
        if len(panel["children"]) != 2 or "calls: 2" not in panel["children"][0] or not all(name in panel["children"][0] for name in ("inner_a", "inner_b")):
            failures.append("repeated leaf calls lost their shared-definition panel and invocation labels")
    positions = xml_titles(project / "graph.svg")
    if len(positions) != 5 or not (all(positions[index]["x"] < positions[index+1]["x"] for index in range(3)) and positions[3]["x"] == positions[4]["x"] and len({position["y"] for position in positions[:4]}) == 1 and positions[3]["y"] < positions[4]["y"]):
        failures.append("actual SVG root panel order or Nodeset vertical stacking changed")
    if not any("calls: 2" in row["title"] and "outer_a" in row["title"] and "outer_b" in row["title"] for row in positions):
        failures.append("repeated outer calls lost their shared-definition label")
    return failures


def verify_browser(browser, *, expanded):
    failures = []
    nodes = browser.get("nodes", [])
    if not nodes or any(item["width"] <= 0 or item["height"] <= 0 for item in nodes):
        failures.append("browser did not observe visible SVG node geometry")
    if not expanded:
        if not all(any(group in item["id"] for item in nodes) for group in ("resource_plugins", "resource_base_lib")):
            failures.append("ordinary SVG lost explicit Plugin/BaseLib resources")
        return failures
    if browser.get("root") != "flowchart-review-columns":
        failures.append("formal expanded SVG lost review-columns root semantics")
    def name(item):
        match = re.search(r"-flowchart-(.+)-[0-9]+$", item["id"])
        value = match.group(1) if match else ""
        return "end" if value == "n_end" else value

    main = {name(item):item for item in nodes if item["fragments"] == ["main pipeline"]}
    root_ids = ["start", "outer_a", "outer_b", "loop", "end"]
    if any(identifier not in main for identifier in root_ids):
        failures.append("browser could not locate actual outer workflow nodes")
    else:
        ys = [main[name]["y"] for name in root_ids]
        if ys != sorted(ys) or len(set(ys)) != len(ys):
            failures.append("actual outer workflow geometry is not top-to-bottom")
    for frame in browser.get("fragments", []):
        if frame["title"] not in RESOURCE_TITLES and any(
                re.search(r"-flowchart-(?:resource_|vf_resource_)", identifier) for identifier in frame["nodes"]):
            failures.append("actual SVG resource leakage into business fragment: " + frame["title"])
    for identity, fill in (("id: layout.helper","rgb(255, 230, 179)"),
                           ("id: layout.resources","rgb(217, 230, 255)")):
        section = "base_lib" if "layout.helper" in identity else "plugins"
        matches = [item for item in nodes if item["fragments"] == [section] and identity in item["text"] and "reference" not in item["text"]]
        if len(matches) != 1 or not any(shape["tag"] == "polygon" and shape["fill"] == fill
                                      for item in matches for shape in item["shapes"]):
            failures.append("actual resource hexagon or declared colour changed: " + identity)
    failures.extend(user_resource_failures("\n".join(item["text"] for item in nodes)))
    parents = {}
    for item in nodes:
        if item["fragments"] and item["fragments"][-1] == "parent flow":
            parents.setdefault(tuple(item["fragments"]),{})[name(item)] = item
    for parent in parents.values():
        expected = ["outer_start", "inner_a", "inner_b", "inner_c", "outer_end"]
        if any(identifier not in parent for identifier in expected):
            failures.append("browser could not locate actual nested parent nodes")
        else:
            ys = [parent[identifier]["y"] for identifier in expected]
            if ys != sorted(ys) or len(set(ys)) != len(ys):
                failures.append("actual nested parent geometry is not top-to-bottom")
    pairs = [(item, next((other for other in nodes if name(other) == "right" and
                        other["fragments"] == item["fragments"]),None))
             for item in nodes if name(item) == "left"]
    if len(pairs) != 2 or any(right is None or left["x"] >= right["x"] for left,right in pairs):
        failures.append("actual leaf step geometry is not left-to-right")
    for left, right in pairs:
        for item, fill in ((left,"rgb(214, 234, 255)"), (right,"rgb(189, 232, 208)")):
            if item is None:
                continue
            shapes = [shape for shape in item["shapes"] if shape["fill"] == fill]
            if not shapes or not any(shape["tag"] == "rect" and float(shape.get("rx") or 0) > 0 for shape in shapes):
                failures.append("actual leaf colour override or rounded shape changed: " + item["id"])
    return failures


def observe(identifier, args):
    project = args.work / identifier
    write_project(project)
    output = project / ("graph.mmd" if ".mermaid." in identifier else "graph.svg")
    if ".review." in identifier:
        command = "review"
    elif ".mermaid." in identifier:
        command = "export-mermaid"
    else:
        command = "export-svg"
    expanded = ".review." in identifier or ".expanded_svg." in identifier
    commands = [command, "--workspace", str(project.parent / "vibeflow_config.jsonc"),
                "--config", str(project / "workflow.jsonc"), "--output", str(output)]
    if ".expanded_svg." in identifier:
        commands.append("--expand-nodesets")
    env = {**os.environ, "PYTHONPATH":str(args.kernel), "PYTHONNOUSERSITE":"1",
           "PYTHONDONTWRITEBYTECODE":"1", "VIBEFLOW_MERMAID_RENDERER_ROOT":str(args.renderer)}
    report = project / "observation.json"
    result = subprocess.run([sys.executable, "-B", str(HERE / "observe_cli.py"),
        "--report", str(report), "--", *commands], cwd=project, env=env,
        capture_output=True, text=True, timeout=300)
    if result.returncode or not report.is_file():
        raise RuntimeError("CLI instrumentation failed: " + result.stdout + result.stderr)
    observation = json.loads(report.read_text())
    failures = []
    if observation["error"] is not None or observation["exit_code"] != 0 or not output.is_file():
        failures.append("formal CLI failed before the target layout could be observed")
    elif expanded:
        failures.extend(verify_expanded(project, observation))
        if command == "review":
            document = json.loads("\n".join(line for line in (project/"ARCHITECTURE.jsonc").read_text().splitlines()
                                          if not line.strip().startswith("//")))
            nodes = {item["id"]:item for item in document["nodeset_types"]["layout.leaf_a"]["body"]["nodes"]}
            left, right = nodes["left"]["presentation"], nodes["right"]["presentation"]
            if left["values"]["fill"] != "#d6eaff" or left["values"]["shape"] != "rounded" or left["sources"]["fill"] != "node":
                failures.append("Architecture lost the Node's declared colour, shape or source")
            if right["values"]["fill"] != "#bde8d0" or right["sources"]["fill"] != "call" or right["values"]["shape"] != "rounded":
                failures.append("Architecture lost the legal call colour override or preserved Node shape")
    elif command == "export-mermaid":
        text = output.read_text()
        if text.splitlines()[0] != "flowchart TD" or not all(value in text for value in ("resource_plugins@", "resource_base_lib@")):
            failures.append("ordinary Mermaid export lost explicit resources or default direction")
    if output.suffix == ".svg" and output.is_file() and observation["exit_code"] == 0:
        browser = subprocess.run(["node", str(HERE / "browser.mjs"), str(args.renderer),
            str(output), str(project / "graph.png")], capture_output=True, text=True, timeout=90)
        if browser.returncode:
            failures.append("real browser evidence failed: " + browser.stderr[-1000:])
        else:
            data = json.loads(browser.stdout)
            (project / "browser.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")
            failures.extend(verify_browser(data, expanded=expanded))
    evidence = args.report.parent / "evidence" / args.report.stem / identifier
    evidence.mkdir(parents=True, exist_ok=True)
    for source in project.iterdir():
        if source.suffix in {".svg", ".png", ".mmd"} or source.name in {"observation.json", "browser.json", "ARCHITECTURE.jsonc", "observation.stdout.txt", "observation.stderr.txt"}:
            shutil.copy2(source, evidence / source.name)
    return {"id":identifier, "expected":{"cli_exit_code":0, "resources_only_in_resource_panel":expanded,
            "workflow":"TD", "leaf":"LR" if expanded else None, "parent_with_children":"TD" if expanded else None},
            "actual":observation, "matched":not failures, "failures":failures,
            "artifact_root":str(project), "evidence":str(evidence)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, default=ROOT / "src")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--renderer", type=Path, required=True)
    args = parser.parse_args()
    if (args.kernel / "src/vibeflow").is_dir():
        args.kernel /= "src"
    args.kernel, args.work, args.report, args.renderer = [path.resolve() for path in (args.kernel,args.work,args.report,args.renderer)]
    results, errors = [], []
    for identifier in CASES:
        try:
            row = observe(identifier,args)
            results.append(row)
            print(identifier, "PASS" if row["matched"] else "FAIL: " + "; ".join(row["failures"]),flush=True)
        except Exception as error:
            errors.append({"id":identifier, "error":repr(error)})
            print(identifier, "OBSERVATION ERROR", repr(error),flush=True)
    report = {"schema":"vibeflow.review-layout.v1", "kernel":str(args.kernel), "renderer":str(args.renderer),
              "expected_cases":CASES, "cases":results, "observation_errors":errors,
              "summary":{"cases":len(results), "matched":sum(row["matched"] for row in results),
                         "unmatched":sum(not row["matched"] for row in results), "observation_errors":len(errors)},
              "matched":len(results)==len(CASES) and not errors and all(row["matched"] for row in results)}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    return 0 if report["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
