"""Real-CLI memory observations; generated projects are temporary.

Requires psutil. Run with --toolchain pointing to a directory containing
node_modules/typescript (7.0.2) and node_modules/esbuild (0.28.1).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import psutil

REPO = Path(__file__).resolve().parents[4]


def write_project(directory, target, count, split, toolchain):
    root = directory / "project"
    (root / "nodes").mkdir(parents=True)
    (root / "configs").mkdir()
    def write(path, value):
        path.write_text(json.dumps(value, indent=2) + "\n")
    write(directory / "vibeflow_config.jsonc", {"roots": [{"id": "probe", "path": "project"}]})
    write(directory / "project_rules.jsonc", {"rulesets": []})
    write(root / "root_rules.jsonc", {"rulesets": []})
    config = {"project_target": target, "architecture": {"documents": [
        {"workflow": "configs/main.jsonc", "document": "ARCHITECTURE.jsonc"}]}}
    if target == "javascript":
        config["javascript"] = {"package_root": ".", "external_packages": []}
        write(root / "package.json", {"type": "module", "private": True})
        (root / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    write(root / "vibeflow_project.jsonc", config)
    blocks = []
    for index in range(count):
        descriptor = dict(node_type="vibeflow.node", id=f"probe.n{index}",
                          display_name=f"Empty {index}", description="Empty diagnostic node.",
                          rulesets=["vibeflow.process"], flow_kind="terminal", contract={})
        if target == "javascript":
            block = (f"function run{index}(): Readonly<Record<never, never>> {{ return {{}}; }}\n"
                     f"export const n{index} = defineNode({{{json.dumps(descriptor)[1:-1]}, run:run{index}}});\n")
            prefix = 'import {defineNode} from "@vibeflow/plugin";\n'
            suffix = "ts"
        else:
            block = (f"@node(**{descriptor!r})\nclass N{index}:\n"
                     "    def run_pure(self, inputs, params):\n        return {}\n\n")
            prefix = "from vibeflow.targets.python.sdk import node\n"
            suffix = "py"
        if split:
            (root / "nodes" / f"n{index}.{suffix}").write_text(prefix + block)
        else:
            blocks.append(block)
    if not split:
        (root / "nodes" / f"all.{suffix}").write_text(prefix + "".join(blocks))
    nodes = []
    for index in range(count):
        node = {"id": f"n{index}", "definition_id": f"probe.n{index}",
                "display_name": f"Empty {index}", "description": "Empty diagnostic node."}
        if index:
            node["similar_to"] = {"node": "n0", "relationship": "copy",
                                  "reason": "All diagnostic nodes intentionally return an empty object."}
        nodes.append(node)
    write(root / "configs/main.jsonc", {"pipeline": {"nodes": nodes,
        "edges": [[f"n{i}", f"n{i+1}"] for i in range(count-1)], "outputs": []}})
    return root


def observe(directory, target, count, split, command, kernel, toolchain, temp, mode):
    root = write_project(directory, target, count, split, toolchain)
    args = [sys.executable, "-m", "vibeflow", command, "--workspace",
            str(directory / "vibeflow_config.jsonc"), "--config", str(root / "configs/main.jsonc"),
            "--preview-root", str(directory / "preview")]
    if command == "build":
        args += ["--out-dir", str(directory / "dist")]
        if target == "javascript":
            args += ["--target", "node", "--profile", "single-esm"]
    env = {**os.environ, "PYTHONPATH": str(kernel), "PYTHONDONTWRITEBYTECODE": "1",
           "TMPDIR": str(temp), "TMP": str(temp), "TEMP": str(temp)}
    # Registered architecture is a prerequisite for Python build. Generate it
    # outside the measurement for both targets, using a separate CLI process.
    seed = subprocess.run([sys.executable, "-m", "vibeflow", "export-architecture",
        "--workspace", str(directory / "vibeflow_config.jsonc"), "--config", str(root / "configs/main.jsonc"),
        "--output", str(root / "ARCHITECTURE.jsonc")], cwd=directory, env=env, capture_output=True, text=True)
    if seed.returncode:
        raise RuntimeError("fixture architecture generation failed: " + seed.stdout[-4000:] + seed.stderr[-2000:])
    peak_rss, peak_tsc, peak_driver_tsc = 0, 0, 0
    tsc_pids, commands = set(), set()
    timeline = []
    start = time.monotonic()
    with (directory / "stdout").open("w+") as output, (directory / "stderr").open("w+") as errors:
        process = subprocess.Popen(args, cwd=directory, env=env, stdout=output, stderr=errors)
        parent = psutil.Process(process.pid)
        try:
            while process.poll() is None:
                family = []
                try:
                    descendants = parent.children(recursive=True)
                except psutil.Error:
                    descendants = []
                for child in [parent, *descendants]:
                    try:
                        family.append((child.pid, child.ppid(), child.memory_info().rss, child.cmdline(), child.status()))
                    except psutil.Error:
                        pass
                tsc = [item for item in family if "--api" in item[3] and any("tsc" in word for word in item[3])]
                drivers = {pid for pid, _, _, argv, _ in family if "--session" in argv and any("toolchain_driver.mjs" in word for word in argv)}
                driver_tsc = [item for item in tsc if item[1] in drivers]
                peak_rss = max(peak_rss, sum(item[2] for item in family))
                peak_tsc = max(peak_tsc, len(tsc))
                peak_driver_tsc = max(peak_driver_tsc, len(driver_tsc))
                tsc_pids.update(item[0] for item in tsc)
                commands.update(" ".join(item[3][:3]) for item in family[1:])
                state = (len(tsc), len(driver_tsc))
                if not timeline or state != tuple(timeline[-1][1:]):
                    timeline.append([round(time.monotonic()-start, 3), *state])
                if time.monotonic()-start > 180:
                    raise TimeoutError("diagnostic CLI exceeded 180 seconds")
                time.sleep(0.03)
        finally:
            if process.poll() is None:
                for child in reversed(descendants):
                    try: child.terminate()
                    except psutil.Error: pass
                process.terminate()
                process.wait(timeout=10)
        output.seek(0)
        stdout = output.read()
        errors.seek(0)
        stderr = errors.read()
    try:
        payload = json.loads(stdout)
    except ValueError:
        payload = {"raw": stdout[-5000:]}
    alive = []
    for pid in tsc_pids:
        try:
            if psutil.Process(pid).status() != psutil.STATUS_ZOMBIE:
                alive.append(pid)
        except psutil.Error:
            pass
    return dict(target=target, nodes=count, files=count if split else 1, command=command, mode=mode,
                exit_code=process.returncode, seconds=round(time.monotonic()-start, 3),
                peak_rss_mib=round(peak_rss/2**20, 1), peak_tsc=peak_tsc,
                peak_tsc_under_session_driver=peak_driver_tsc, surviving_tsc=alive,
                tsc_count_timeline=timeline, child_commands=sorted(commands),
                result={key:payload[key] for key in ["status", "published", "failed_stage", "entry", "error", "warnings"] if key in payload},
                stderr=stderr if process.returncode else "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    temp_root = Path("/home/rockingsisyphus/ai-tmp")
    if not temp_root.is_mount():
        raise RuntimeError("AI temporary filesystem is not mounted")
    results = []
    with tempfile.TemporaryDirectory(prefix="ts-retention-", dir=temp_root) as temporary:
        temp = Path(temporary)
        if args.smoke:
            cases = [("current", target, 8, True, "build") for target in ["javascript", "python"]]
        else:
            cases = [("current", target, count, split, command) for target in ["javascript", "python"]
                     for count, split in [(8, False), (8, True), (12, True)] for command in ["build", "review"]]
        for index, (mode, target, count, split, command) in enumerate(cases):
            directory = temp / f"case-{index}"
            result = observe(directory, target, count, split, command, REPO / "src", args.toolchain.resolve(), temp, mode)
            # Strip ephemeral paths from durable output; preserve structural evidence.
            result = json.loads(json.dumps(result).replace(str(temp), "<temporary>"))
            results.append(result)
            args.output.write_text(json.dumps({"repository_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
                "python": sys.version, "node": subprocess.check_output(["node", "-v"], text=True).strip(),
                "toolchain": {name:json.loads((args.toolchain / "node_modules" / name / "package.json").read_text())["version"] for name in ["typescript", "esbuild"]},
                "sampling_seconds": 0.03, "results": results}, ensure_ascii=False, indent=2)+"\n")
            print(json.dumps({key: result[key] for key in ["mode", "target", "nodes", "files", "command", "exit_code", "seconds", "peak_rss_mib", "peak_tsc", "peak_tsc_under_session_driver", "surviving_tsc"]}), flush=True)
            if result["exit_code"]:
                print(json.dumps(result["result"], ensure_ascii=False)[:6000], flush=True)


if __name__ == "__main__":
    main()
