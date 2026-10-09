"""Formal Python CLI checks for user resource directories and Nodeset folding."""

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tests.fixtures.adaptation_regressions.common import run_cli, run_command, row, write_json
from tests.fixtures.python.review_layout.fixtures import write_project
from tests.fixtures.python.review_layout.run_all import user_resource_failures

HERE = Path(__file__).resolve().parent
LAYOUT = HERE.parent / "review_layout"
CASES = (
    ("py.sections.review.default", "review", "default"),
    ("py.sections.review.rules", "review", "rules"),
    ("py.sections.svg.rules", "export-svg", "rules"),
    ("py.sections.mermaid.columns", "export-mermaid", "columns"),
    ("py.sections.mermaid.rules", "export-mermaid", "rules"),
    ("py.expand.outer.false", "review", "outer-false"),
    ("py.expand.inner.false", "review", "inner-false"),
    ("py.expand.shared.false", "export-mermaid", "inner-false"),
    ("py.expand.loop.false", "export-svg", "loop-false"),
    ("py.expand.ascii.false", "export-ascii", "outer-false"),
    ("py.expand.validate.false", "validate", "outer-false"),
    ("py.expand.quality.false", "quality-check", "outer-false"),
    ("py.expand.health.false", "validate", "rejected"),
    ("py.expand.run.false", "run", "outer-false"),
)


def fixture(path, variant):
    write_project(path)
    target = "outer.jsonc" if variant in {"outer-false", "rejected"} else "leaf_a.jsonc" if variant == "inner-false" else None
    if target:
        definition = json.loads((path / target).read_text())
        definition["expand"] = False
        write_json(path / target, definition)
    if variant == "loop-false":
        definition = json.loads((path / "outer.jsonc").read_text())
        definition.update(type_key="layout.loop_body", expand=False)
        write_json(path / "loop_body.jsonc", definition)
        workflow = json.loads((path / "workflow.jsonc").read_text())
        workflow["nodeset_imports"].append({"path": "loop_body.jsonc"})
        next(node for node in workflow["pipeline"]["nodes"] if node["id"] == "loop")["loop"]["body"] = "layout.loop_body"
        write_json(path / "workflow.jsonc", workflow)
    # The custom check is real and selected, including in folded detail nodes.
    (path / "plugins/check.py").write_text('''from vibeflow.targets.python.sdk import rule, ruleset
@rule(id="layout.health", params_schema={"reject":{"type":"boolean"}}, params_defaults={"reject":False})
def health(context, inputs, params):
    return {"findings": [{"code":"CASE.HIDDEN.SOURCE", "severity":"error",
        "message":"A folded implementation still undergoes health review.",
        "file":__file__, "line":4}]} if params.get("reject") else {"findings":[]}
health_set = ruleset(id="layout.health_set", calls=[{"id":"health", "rule_id":"layout.health",
    "params":{"reject":''' + str(variant == "rejected") + '''}}], entrypoints={"static":["health"]})
''')
    plugin = path / "code_plugin.py"
    plugin.write_text(plugin.read_text().replace("from vibeflow.targets.python.sdk import Plugin",
        "from vibeflow.targets.python.sdk import Plugin\nfrom plugins.check import health, health_set")
        .replace("resources=[calculate, Start, End, Step, Right]", "resources=[calculate, Start, End, Step, Right, health, health_set]"))
    nodes = path / "nodes/steps.py"
    nodes.write_text(nodes.read_text().replace('rulesets=["vibeflow.process"]', 'rulesets=["vibeflow.process","layout.health_set"]'))


def observe(args, identifier, command, variant):
    path = args.work / identifier
    fixture(path, variant)
    output = path / ("graph.svg" if command in {"review", "export-svg"} else "graph.mmd" if command == "export-mermaid" else "graph.txt")
    cli = [command, "--workspace", path / "vibeflow_config.jsonc"]
    if command != "quality-check":
        cli.extend(("--config", path / "workflow.jsonc"))
    else:
        cli.extend(("--path", path, "--json"))
    if command.startswith("export") or command == "review":
        cli.extend(("--output", output))
    if command.startswith("export"):
        cli.append("--expand-nodesets")
    if variant == "rules":
        cli.append("--show-rules")
    if variant == "columns":
        cli.extend(("--mermaid-layout", "review-columns"))
    if command == "validate":
        cli.append("--json")
    if command == "run":
        cli.extend(("--run-root", path / "runs", "--run-id", "folded"))
    preparation = None
    if command in {"validate", "quality-check", "run"} and variant != "rejected":
        preparation = run_cli(path, ["export-architecture", "--workspace", path / "vibeflow_config.jsonc",
            "--config", path / "workflow.jsonc", "--output", path / "ARCHITECTURE.jsonc"],
            args.kernel, name="prepare-architecture", timeout=120)
    report = path / "observation.json"
    instrumentation = run_command(path, [sys.executable, "-B", LAYOUT / "observe_cli.py",
        "--report", report, "--", *cli], args.kernel, name="instrumentation", renderer=args.renderer, timeout=300)
    if not report.is_file():
        # Removed internal-diagram options are rejected before plugin loading.
        stdout_file, stderr_file = report.with_suffix(".stdout.txt"), report.with_suffix(".stderr.txt")
        actual = {"exit_code":instrumentation["exit_code"],
            "stdout":stdout_file.read_text() if stdout_file.is_file() else instrumentation["stdout"],
            "stderr":stderr_file.read_text() if stderr_file.is_file() else instrumentation["stderr"]}
        failures = []
        if variant != "rules" or actual["exit_code"] != 2 or "unrecognized arguments: --show-rules" not in actual["stderr"]:
            failures.append("the removed internal-diagram option must be explicitly rejected with exit 2")
        if output.exists() or (path / "ARCHITECTURE.jsonc").exists():
            failures.append("an unrecognized option must not publish a user diagram or Architecture")
        return row(identifier, "resource-sections", "CLI argument rejection", {},
            actual, failures, path)
    actual = json.loads(report.read_text())
    if preparation is not None:
        actual["preparation_exit_code"] = preparation["exit_code"]
    actual["stdout"] = report.with_suffix(".stdout.txt").read_text()
    actual["stderr"] = report.with_suffix(".stderr.txt").read_text()
    expected_exit = 1 if variant == "rejected" else 0
    failures = []
    if preparation is not None and preparation["exit_code"] != 0:
        failures.append("formal Architecture preparation failed before the target check")
    if actual["error"] is not None or actual["exit_code"] != expected_exit:
        failures.append(f"expected CLI exit {expected_exit}, got {actual['exit_code']}: {actual['error']}")
    if variant == "rejected" and "CASE.HIDDEN.SOURCE" not in actual["stdout"]:
        failures.append("the folded body must retain its selected health rule diagnostic")
    if variant == "rejected" and actual["exit_code"] == 1:
        findings = json.loads(actual["stdout"]).get("errors", [])
        if not findings or any(item.get("code") != "CASE.HIDDEN.SOURCE" or item.get("severity") != "error"
                               or not item.get("source_location", {}).get("path", "").endswith("plugins/check.py")
                               or item.get("source_location", {}).get("line") != 4 for item in findings):
            failures.append("hidden health rejection must retain only the target error, exact file and line")
    if command in {"review", "export-svg"} and output.is_file():
        actual["titles"] = [title for group in actual["columns"] for title in group]
        expected = ["main pipeline", "plugins", "base_lib"]
        if actual["titles"][:3] != expected:
            failures.append("user resource directories must follow selected plugins and base_lib before Nodeset details")
        frames = actual["frames"]
        texts = "\n".join(Path(frame["mermaid_path"]).read_text() for frame in frames)
        failures.extend(user_resource_failures(texts))
        if variant == "outer-false" and any(title not in expected for title in actual["titles"]):
            failures.append("folded Outer and Loop body must not render descendant panels")
        if variant == "inner-false" and (any("layout.leaf_a" in frame["title"] for frame in frames) or not any("layout.leaf_b" in frame["title"] for frame in frames)):
            failures.append("folded shared Leaf A must disappear while sibling Leaf B remains visible")
        if variant == "loop-false" and (any("layout.loop_body" in title for title in actual["titles"]) or not any("layout.outer" in title for title in actual["titles"])):
            failures.append("folding the Loop body must preserve independent visible Nodesets")
        for frame in frames:
            if frame["title"] in expected[1:] and frame["direction"] != "flowchart LR":
                failures.append("resource fragment direction must remain LR")
        if variant in {"default", "outer-false"}:
            browser = run_command(path, ["node", LAYOUT / "browser.mjs", args.renderer, output, path / "graph.png"], args.kernel, name="browser", timeout=90)
            if browser["exit_code"] or not browser["payload"] or not browser["payload"].get("nodes"):
                failures.append("real browser SVG inspection failed")
            else:
                write_json(path / "browser.json", browser["payload"])
                nodes = browser["payload"]["nodes"]
                failures.extend(user_resource_failures("\n".join(item.get("text", "") for item in nodes)))
                if any(item["width"] <= 0 or item["height"] <= 0 for item in nodes):
                    failures.append("actual user SVG must retain visible node geometry")
                for section, identity, fill in (("plugins", "id: layout.resources", "rgb(217, 230, 255)"),
                                                ("base_lib", "id: layout.helper", "rgb(255, 230, 179)")):
                    matches = [item for item in nodes if item["fragments"] == [section] and identity in item["text"]]
                    if len(matches) != 1 or not any(shape["tag"] == "polygon" and shape["fill"] == fill
                                                 for item in matches for shape in item["shapes"]):
                        failures.append("actual selected resource shape or colour changed: " + identity)
    elif command == "export-mermaid" and output.is_file():
        text = output.read_text()
        if variant == "columns":
            if not all(label in text for label in ('"plugins"', '"base_lib"', 'resource_plugins -.-> resource_plugins_0', 'resource_base_lib -.-> resource_base_lib_0')):
                failures.append("Mermaid must contain parent-to-selected-resource directories")
        failures.extend(user_resource_failures(text))
        if variant == "inner-false" and ("a_start@" in text or "b_start@" not in text):
            failures.append("Mermaid must stop at shared hidden Leaf A but render visible Leaf B")
    elif command == "export-ascii" and output.is_file():
        if "nodeset " in output.read_text():
            failures.append("ASCII must retain only the folded outer call boxes")
    if command == "review" and (path / "ARCHITECTURE.jsonc").is_file():
        document = json.loads("\n".join(line for line in (path / "ARCHITECTURE.jsonc").read_text().splitlines() if not line.strip().startswith("//")))
        actual["architecture_expand"] = {key: value.get("expand") for key, value in document["nodesets"].items()}
        expected = {"layout.outer": variant != "outer-false", "layout.leaf_a": variant != "inner-false", "layout.leaf_b": True}
        if actual["architecture_expand"] != expected:
            failures.append("Architecture must record explicit and default expand values")
        if not document["nodesets"]["layout.leaf_a"].get("body"):
            failures.append("Architecture must preserve the complete hidden implementation")
    if command == "run" and actual["exit_code"] == 0:
        execution = json.loads((path / "runs/folded/output_summary.json").read_text())
        expected_calls = ["outer_a.inner_a.left", "outer_b.inner_b.right", "loop.iter_0.inner_c.middle"]
        actual["executed_hidden_calls"] = [call for call in expected_calls if "runtime.qualified_node_runs." + call in execution]
        if actual["executed_hidden_calls"] != expected_calls:
            failures.append("folded Nodeset and Loop must execute all their actual internal calls")
    evidence = args.report.parent / "evidence" / args.report.stem / identifier
    evidence.mkdir(parents=True, exist_ok=True)
    for source in path.iterdir():
        if source.suffix in {".svg", ".png", ".mmd"} or source.name in {"observation.json", "browser.json", "ARCHITECTURE.jsonc", "observation.stdout.txt", "observation.stderr.txt"}:
            shutil.copy2(source, evidence / source.name)
    return row(identifier, "resource-sections", "User resource directories and display-only Nodeset folding",
        {"exit_code": expected_exit}, actual, failures, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, default=ROOT / "src")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--renderer", type=Path, required=True)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    known_cases = [identifier for identifier, _command, _variant in CASES]
    if args.case and set(args.case) - set(known_cases):
        parser.error("unknown cases: " + ", ".join(sorted(set(args.case) - set(known_cases))))
    args.kernel, args.work, args.report, args.renderer = (path.resolve() for path in (args.kernel, args.work, args.report, args.renderer))
    cases = []
    for identifier, command, variant in CASES:
        if args.case and identifier not in args.case:
            continue
        try:
            cases.append(observe(args, identifier, command, variant))
        except Exception as error:
            cases.append(row(identifier, "resource-sections", "Observation failed", {}, {"error": repr(error)}, [repr(error)], args.work / identifier))
        print(identifier, "PASS" if cases[-1]["matched"] else "FAIL: " + "; ".join(cases[-1]["failures"]), flush=True)
    expected = [identifier for identifier in known_cases if not args.case or identifier in args.case]
    report = {"expected_cases": expected, "cases": cases, "observation_errors": [case for case in cases if "error" in case["actual"] and case["actual"]["error"] is not None],
              "summary": {"cases": len(cases), "matched": sum(case["matched"] for case in cases), "unmatched": sum(not case["matched"] for case in cases)}}
    write_json(args.report, report)
    return 0 if len(cases) == len(expected) and cases and all(case["matched"] for case in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
