"""Audit saved real-browser DOM evidence against the declared resource presentation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def audit(project, *, hidden=False):
    browser = json.loads((project / "browser.json").read_text())
    nodes = browser["nodes"]
    titles = [item["title"] for item in browser["fragments"]]
    failures = []
    expected = ["main pipeline", "plugins", "base_lib"]
    if titles[:3] != expected:
        failures.append("browser resource columns lost their declared order")
    if browser["root"] != "flowchart-review-columns" or not nodes:
        failures.append("browser did not render the formal SVG")
    if any(item["width"] <= 0 or item["height"] <= 0 for item in nodes):
        failures.append("browser observed invisible node geometry")
    for title, identity, fill, shape in (
        ("base_lib", "id: demo.math", "rgb(200, 228, 255)", "path"),
        ("plugins", "id: demo", "rgb(236, 212, 255)", "path"),
    ):
        matches = [item for item in nodes if item["fragments"] == [title] and identity in item["text"] ]
        if len(matches) != 1 or not any(s["fill"] == fill and s["tag"] == shape for item in matches for s in item["shapes"]):
            failures.append("browser colour or shape differs from the declared resource: " + identity)
    rule_nodes = [item for item in nodes if "Rule:" in item["text"] or "Ruleset:" in item["text"]]
    if rule_nodes:
        failures.append("user diagrams must not render Rule/Ruleset definitions")
    for title in expected[1:]:
        entries = [item for item in nodes if item["fragments"] == [title]]
        if len(entries) != 2 or sum(item["text"] == title for item in entries) != 1:
            failures.append("a directory must contain one parent and one selected child: " + title)
    for item in nodes:
        if any(token in item["text"] for token in ("reference", "owners:", "support.ts", "Node types")):
            failures.append("browser observed internal audit details: " + item["text"])
    business = [item for item in nodes if item["fragments"] and item["fragments"][0] not in {*expected[1:], "capabilities"}]
    if any("vf_resource_" in item["id"] for item in business):
        failures.append("resource nodes leaked into a business fragment")
    concrete_model_calls = [item for item in business if "-flowchart-vf_model-" in item["id"]]
    if bool(concrete_model_calls) == hidden:
        failures.append("hidden Nodeset body did not follow expand:false")
    return {"artifact_root": str(project), "titles": titles, "nodes": len(nodes), "rule_nodes": len(rule_nodes),
            "concrete_model_calls": len(concrete_model_calls), "screenshot": str(project / "graph.png"),
            "passed": not failures, "failures": failures}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    rows = [audit(args.work / identifier, hidden=hidden) for identifier, hidden in (
        ("js.sections.review.default", False), ("js.expand.outer.false", True))]
    report = {"scope": "Saved Puppeteer DOM, computed shapes/colours and screenshots of the real formal CLI SVGs", "passed": all(row["passed"] for row in rows), "cases": rows}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "cases": len(rows)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
