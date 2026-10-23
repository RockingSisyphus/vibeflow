"""One real AOT bundle, exercised in Node and offline headless Chromium."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
FIXTURE = Path(__file__).resolve().parent
ROOT = FIXTURE.parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from tests.fixtures.support.workflow_cooperation import CASES, FAULTS, prepare, set_fault, verify_rows, verify_cancelled
from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
from vibeflow.targets.javascript.build.driver_session import check_scope


@check_scope
def run(work, toolchain, puppeteer=None):
    output = prepare(FIXTURE, work, "javascript", toolchain)
    def build(name, label):
        return build_project_aot(ProjectBuildRequest(work / "vibeflow_config.jsonc",
            work / f"project/configs/{name}.jsonc", output / label, "browser", "single-esm")).entry
    modules = {name: build(name, name) for name in ("a", "b", "c")}
    for fault in FAULTS:
        set_fault(work, "javascript", fault)
        modules[fault] = build("a", fault)
    imports = [f"import * as {name} from {json.dumps(path.as_posix())};" for name, path in modules.items()]
    coordinator = ROOT / "src/vibeflow/targets/javascript/resources/coordination/coordinator.mjs"
    script = output / "probe.mjs"
    script.write_text("\n".join(imports) + f'''
import {{Coordinator}} from {json.dumps(coordinator.as_posix())};
import {{verify}} from {json.dumps((FIXTURE / 'verify.mjs').as_posix())};
export function run(){{return verify(Coordinator,{{{','.join(modules)}}},{json.dumps(CASES)},{json.dumps(FAULTS)});}}
''', encoding="utf-8")
    bundle = output / "cooperative-math.js"
    done = subprocess.run([str(toolchain / "node_modules/.bin/esbuild"), str(script), "--bundle", "--platform=browser",
        "--format=iife", "--global-name=CooperativeMath", f"--outfile={bundle}"], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stdout + done.stderr
    # The deployed script must execute without the project sources or imports.
    shutil.rmtree(work / "project")
    driver = output / "node.cjs"
    driver.write_text(bundle.read_text(encoding="utf-8") + '\nCooperativeMath.run().then(result=>console.log(JSON.stringify(result))).catch(error=>{console.error(error);process.exitCode=1;});\n', encoding="utf-8")
    observations = []
    commands = [("node", ["node", str(driver)])]
    if puppeteer:
        commands.append(("chromium", ["node", str(FIXTURE / "browser.cjs"),
                         str(puppeteer / "package.json"), str(bundle)]))
    for environment, command in commands:
        done = subprocess.run(command, capture_output=True, text=True, timeout=110)
        assert done.returncode == 0, done.stdout + done.stderr
        report = json.loads(done.stdout)
        verify_rows(report["rows"])
        verify_cancelled(report["cancelled"])
        assert {item["fault"]: item["observed"] for item in report["controls"]} == FAULTS, report
        if environment == "chromium":
            assert report["headless"] and report["networkRequests"] == 0, report
        (output / f"{environment}-trace.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report.pop("events")
        observations.append({"execution": environment, "status": "PASS", **report})
    if not puppeteer:
        observations.append({"execution": "chromium", "status": "SKIP", "reason": "--puppeteer-root required"})
    return {"status": "PASS" if puppeteer else "REDUCED", "observations": observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--toolchain-root", type=Path, required=True)
    parser.add_argument("--puppeteer-root", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vibeflow-cooperative-math-") as raw:
        work = args.work_dir.resolve() if args.work_dir else Path(raw)
        work.mkdir(parents=True, exist_ok=True)
        report = run(work, args.toolchain_root.resolve(), args.puppeteer_root.resolve() if args.puppeteer_root else None)
        (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"JavaScript multi-workflow cooperative formula: {report['status']} observations={len(report['observations'])}")


if __name__ == "__main__":
    main()
