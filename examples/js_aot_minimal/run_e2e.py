from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
from threading import Thread

from vibeflow.aot import ProjectBuildRequest, build_project_aot


EXAMPLE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = EXAMPLE_ROOT.parents[1]
PROJECT_ROOT = EXAMPLE_ROOT / "project"
WORKSPACE_PATH = EXAMPLE_ROOT / "vibeflow_config.jsonc"
CONFIG_PATH = PROJECT_ROOT / "configs/greeting.jsonc"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def _build(out_dir: Path, *, target: str, profile: str):
    return build_project_aot(
        ProjectBuildRequest(
            workspace=WORKSPACE_PATH,
            config=CONFIG_PATH,
            out_dir=out_dir,
            target=target,
            profile=profile,
            html_template=(
                PROJECT_ROOT / "web/index.template.html"
                if profile == "web-app"
                else None
            ),
            app_entry=(
                PROJECT_ROOT / "web/app.ts"
                if profile == "web-app"
                else None
            ),
        )
    )


def _run_node(entry: Path) -> None:
    script = f"""
import {{ pathToFileURL }} from "node:url";
const moduleUrl = pathToFileURL({json.dumps(str(entry))}).href;
const workflow = await import(moduleUrl);
const result = await workflow.runWorkflowAsync(
  {{ name: "  Ada   Lovelace " }},
  {{ capabilities: {{ "example.clock": {{ now: async () => 123 }} }} }},
);
if (result.greeting !== "Hello, Ada Lovelace! (123)") {{
  throw new Error(`unexpected result: ${{JSON.stringify(result)}}`);
}}
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)


def _assert_deterministic(first: Path, second: Path) -> None:
    first_files = {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    if first_files != second_files:
        changed = sorted(
            key
            for key in set(first_files) | set(second_files)
            if first_files.get(key) != second_files.get(key)
        )
        raise RuntimeError(f"non-deterministic AOT outputs: {changed}")


def _run_browser(web_dir: Path, *, puppeteer_root: Path) -> None:
    handler = partial(_QuietHandler, directory=str(web_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/index.html"
    script = f"""
import puppeteer from "puppeteer";
const browser = await puppeteer.launch({{
  headless: true,
  args: ["--no-sandbox", "--disable-setuid-sandbox"],
}});
try {{
  const page = await browser.newPage();
  await page.goto({json.dumps(url)}, {{ waitUntil: "networkidle0" }});
  const before = await page.$eval("#output", element => element.value);
  if (before !== "") throw new Error("web-app invoked the workflow automatically");
  await page.click("#run");
  await page.waitForFunction(
    () => document.querySelector("#output")?.value.startsWith("Hello, VibeFlow!"),
  );
}} finally {{
  await browser.close();
}}
"""
    try:
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            cwd=puppeteer_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr or completed.stdout)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--puppeteer-root",
        type=Path,
        default=REPOSITORY_ROOT / "tools/mermaid-renderer",
    )
    parser.add_argument("--skip-browser", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="vibeflow-js-aot-e2e-") as raw:
        root = Path(raw)
        module = _build(root / "module", target="node", profile="esm-module")
        single_a = _build(root / "single-a", target="node", profile="single-esm")
        single_b = _build(root / "single-b", target="node", profile="single-esm")
        web = _build(root / "web", target="browser", profile="web-app")

        _run_node(module.entry)
        _run_node(single_a.entry)
        _assert_deterministic(single_a.out_dir, single_b.out_dir)
        runtime_js = [
            path
            for path in single_a.out_dir.rglob("*.js")
            if path.name != single_a.entry.name
        ]
        if runtime_js:
            raise RuntimeError(f"single-esm emitted companion chunks: {runtime_js}")
        if not args.skip_browser:
            _run_browser(web.out_dir, puppeteer_root=args.puppeteer_root.resolve())

    print("JS AOT end-to-end: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
