"""Real SDK, CLI, Mermaid/SVG and execution checks for JavaScript review sections."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from tests.fixtures.adaptation_regressions.common import run_cli, run_command, row, write_json
from tests.fixtures.adaptation_regressions.js_fixtures import project, native_shape, cli_args, cli_summary, check_cli, edit
from tests.fixtures.javascript.resource_sections.audit_browser import audit as audit_browser

CASES = (
    ("js.sections.review.default", "review", "nested", "default"),
    ("js.sections.review.rules", "review", "nested", "rules"),
    ("js.sections.mermaid.default", "export-mermaid", "serial", "default"),
    ("js.sections.mermaid.columns", "export-mermaid", "nested", "columns"),
    ("js.sections.mermaid.rules", "export-mermaid", "nested", "rules"),
    ("js.sections.svg.columns", "export-svg", "nested", "columns"),
    ("js.expand.outer.false", "review", "nested", "outer-false"),
    ("js.expand.inner.false", "export-mermaid", "nested", "inner-false"),
    ("js.expand.ascii.false", "export-ascii", "nested", "outer-false"),
    ("js.expand.shared.false", "export-mermaid", "shared", "body-false"),
    ("js.expand.loop.false", "review", "loop", "body-false"),
    ("js.expand.validate.false", "validate", "nested", "outer-false"),
    ("js.expand.health.false", "validate", "nested", "rejected"),
    ("js.expand.run.false", "build", "nested", "outer-false"),
)


def write_fixture(path, toolchain, shape, variant):
    project(path, toolchain)
    native_shape(path, shape)
    settings = json.loads((path / "vibeflow_project.jsonc").read_text())
    settings["architecture"] = {"documents": [{"workflow": "workflow.jsonc", "document": "ARCHITECTURE.jsonc"}]}
    write_json(path / "vibeflow_project.jsonc", settings)
    target = "outer.jsonc" if variant in {"outer-false", "rejected"} else "body.jsonc" if variant in {"inner-false", "body-false"} else None
    if target:
        definition = json.loads((path / target).read_text())
        definition["expand"] = False
        write_json(path / target, definition)
    if variant == "rejected":
        source = path / "plugins/demo/plugin.ts"
        text = source.read_text().replace('definePlugin,defineCapability,defineDataSchema', 'definePlugin,defineCapability,defineDataSchema,defineRule,defineRuleset')
        code = 'export const rejection=defineRule({id:"demo.hidden_check",check(){return {findings:[{code:"CASE.HIDDEN.SOURCE",reason:"A hidden diagram body still undergoes review",severity:"error",file:'+json.dumps(str(path / "nodes/node.ts"))+',line:1}]};}});\nexport const reviewSet=defineRuleset({id:"demo.hidden",calls:[{id:"check",rule_id:"demo.hidden_check"}],entrypoints:{static:["check"]}});\n'
        text = text.replace('export const plugin=', code + 'export const plugin=').replace('resources:[number]', 'resources:[number,rejection,reviewSet]')
        source.write_text(text)
        edit(path / "nodes/node.ts", 'rulesets:["vibeflow.process"]', 'rulesets:["vibeflow.process","demo.hidden"]')


def observe(args, identifier, command, shape, variant):
    work = args.work / identifier
    write_fixture(work, args.toolchain, shape, variant)
    extra = []
    suffix = ".svg" if command in {"review", "export-svg"} else ".mmd" if command == "export-mermaid" else ".txt"
    output = work / ("graph" + suffix)
    if command.startswith("export") or command == "review":
        extra += ["--output", output]
    if command in {"export-mermaid", "export-svg", "export-ascii"} and shape != "serial":
        extra.append("--expand-nodesets")
    if variant == "columns":
        extra += ["--mermaid-layout", "review-columns"]
    if variant == "rules":
        extra.append("--show-rules")
    if command == "build":
        extra += ["--target", "node", "--profile", "single-esm", "--out-dir", work / "dist"]
    result = run_cli(work, cli_args(work, command, *extra), args.kernel, name="cli", toolchain=args.toolchain, renderer=args.renderer, timeout=300)
    actual = cli_summary(result)
    actual.update({key: result[key] for key in ("command", "stdout_path", "stderr_path", "stderr")})
    if variant == "rules":
        failures = []
        if actual["exit_code"] != 2 or "unrecognized arguments: --show-rules" not in actual["stderr"]:
            failures.append("the removed internal catalog rendering option must be rejected explicitly")
        if output.exists():
            failures.append("a rejected option must not publish an internal diagram")
    else:
        failures = check_cli(actual, accepted=variant != "rejected", code="CASE.HIDDEN.SOURCE" if variant == "rejected" else None,
            require_status=command in {"review", "validate", "build"})
    if output.is_file():
        text = output.read_text()
        actual["output"] = str(output)
        actual["rule_graph_visible"] = "ruleset:" in text.lower() or "rule:" in text.lower()
        if suffix == ".svg":
            tree = ET.fromstring(text)
            actual["titles"] = [item.text for item in tree.iter() if item.tag.rsplit("}", 1)[-1] == "text" and item.get("class") == "review-title"]
            expected = ["main pipeline", "plugins", "base_lib"]
            if actual["titles"][:3] != expected:
                failures.append(f"user resource directories must retain fixed order: {actual['titles']}")
            for forbidden in ("Node types", "引用 / reference", "Rule:", "Ruleset:", "plugin_support.ts", "math_support.ts", "host_support.ts", "owners:"):
                if forbidden in text:
                    failures.append("internal resource material must not appear in the user diagram: " + forbidden)
            if variant in {"outer-false", "body-false"} and any("type_key: audit." in (title or "") for title in actual["titles"]):
                failures.append("expand:false must stop formal SVG detail recursion")
        elif suffix == ".mmd":
            actual["sections"] = [line for line in text.splitlines() if line.startswith("%% resources:")]
            if variant == "columns":
                expected = ["%% resources: plugins", "%% resources: base_lib"]
                if actual["sections"] != expected:
                    failures.append("Mermaid resources must be the workflow's direct resource directories")
            elif shape == "serial" and actual["sections"]:
                failures.append("ordinary Mermaid must retain its workflow-only default")
            for forbidden in ("Node types", "引用 / reference", "Rule:", "Ruleset:", "plugin_support.ts", "math_support.ts", "host_support.ts", "owners:"):
                if forbidden in text:
                    failures.append("internal resource material must not appear in user Mermaid: " + forbidden)
            if variant in {"body-false", "outer-false"} and "%% expanded" in text:
                failures.append("hidden definition must retain only its call box")
            if variant == "inner-false" and ("%% expanded nodeset: audit.outer" not in text or "%% expanded nodeset: audit.body" in text):
                failures.append("visible parent must not expand its hidden child")
            if variant == "inner-false" and not text.partition("%% expanded nodeset: audit.outer\n")[2].startswith("flowchart TD"):
                failures.append("a parent with folded child calls must preserve its vertical direction")
        elif variant == "outer-false" and "nodeset audit." in text:
            failures.append("ASCII must stop at the hidden definition")
    if identifier in {"js.sections.review.default", "js.expand.outer.false"} and output.is_file():
        browser = run_command(work, ["node", ROOT / "tests/fixtures/python/review_layout/browser.mjs",
            args.renderer, output, work / "graph.png"], args.kernel, name="browser", timeout=90)
        actual["browser_exit_code"] = browser["exit_code"]
        if browser["exit_code"] != 0 or not browser.get("payload"):
            failures.append("the real browser must render this formal SVG: " + browser["stderr"])
        else:
            write_json(work / "browser.json", browser["payload"])
            observed = audit_browser(work, hidden=variant == "outer-false")
            actual["browser_audit"] = observed
            failures.extend(observed["failures"])
    if command == "review" and (work / "ARCHITECTURE.jsonc").is_file():
        document = json.loads("\n".join(line for line in (work / "ARCHITECTURE.jsonc").read_text().splitlines() if not line.strip().startswith("//")))
        actual["architecture_expand"] = {key: value.get("expand") for key, value in document["nodeset_types"].items()}
        expected = {"audit.body": False if variant == "body-false" else True}
        if shape == "nested":
            expected["audit.outer"] = variant != "outer-false"
        if actual["architecture_expand"] != expected:
            failures.append("Architecture must preserve both default and explicit expand values")
        if not document["nodeset_types"]["audit.body"].get("body"):
            failures.append("hidden diagram details must remain in the machine architecture")
    if command == "build" and actual["exit_code"] == 0:
        entry = Path(actual["payload"]["entry"])
        script = 'const workflow=await import('+json.dumps(entry.as_uri())+');console.log(JSON.stringify(await workflow.runWorkflow({})));'
        execution = run_command(work, ["node", "--input-type=module", "--eval", script], args.kernel, name="run", toolchain=args.toolchain)
        actual["execution"] = {"exit_code": execution["exit_code"], "outputs": execution.get("payload")}
        if actual["execution"] != {"exit_code": 0, "outputs": {"number": 6}}:
            failures.append(f"expand:false changed executable behavior: {actual['execution']}")
    return row(identifier, "resource-sections", "User workflow resource directories and display-only Nodeset expansion",
        {"exit_code": 2 if variant == "rules" else 1 if variant == "rejected" else 0}, actual, failures, work)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, default=ROOT / "src")
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--renderer", type=Path, required=True)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    args.kernel, args.work, args.report, args.toolchain, args.renderer = (
        path.resolve() for path in (args.kernel, args.work, args.report, args.toolchain, args.renderer))
    if (args.kernel / "src/vibeflow").is_dir():
        args.kernel /= "src"
    manifest = json.loads((Path(__file__).parent / "cases.json").read_text())
    if manifest != [item[0] for item in CASES]:
        raise ValueError("the resource section cases must exactly match their stable manifest")
    if args.case and set(args.case) - set(manifest):
        parser.error("unknown case: " + ", ".join(sorted(set(args.case) - set(manifest))))
    cases = []
    for identifier, command, shape, variant in CASES:
        if args.case and identifier not in args.case:
            continue
        try:
            cases.append(observe(args, identifier, command, shape, variant))
        except Exception as error:
            cases.append(row(identifier, "resource-sections", "Observation failed", {}, {"error": type(error).__name__ + ": " + str(error)}, [str(error)], args.work / identifier))
    report = {"cases": cases, "summary": {"cases": len(cases), "matched": sum(item["matched"] for item in cases), "unmatched": sum(not item["matched"] for item in cases),
        "expected_cases": len(set(args.case)) if args.case else len(manifest),
        "observation_errors": sum("error" in item["actual"] for item in cases)}}
    write_json(args.report, report)
    print(json.dumps(report["summary"]))
    return 0 if cases and all(item["matched"] for item in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
