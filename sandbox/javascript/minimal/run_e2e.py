from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Thread


SOURCE_SANDBOX_ROOT = Path(__file__).resolve().parent


def _find_repository_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "src" / "vibeflow").is_dir()
        ):
            return candidate
    raise RuntimeError(
        "cannot locate the VibeFlow repository root; expected pyproject.toml "
        "and src/vibeflow in one parent directory"
    )


REPOSITORY_ROOT = _find_repository_root(SOURCE_SANDBOX_ROOT)
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from vibeflow.tooling.application.javascript.build import (  # noqa: E402
    ProjectBuildRequest,
    build_project_aot,
)


PROJECT_ROOT = SOURCE_SANDBOX_ROOT / "project"
WORKSPACE_PATH = SOURCE_SANDBOX_ROOT / "vibeflow_config.jsonc"
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
        default=None,
        help="use an existing Puppeteer installation instead of the temporary one",
    )
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="preserve the copied project, toolchain, and builds in .artifacts",
    )
    args = parser.parse_args()

    if args.keep_artifacts:
        work_root = SOURCE_SANDBOX_ROOT / ".artifacts"
        if work_root.exists():
            shutil.rmtree(work_root)
        work_root.mkdir(parents=True)
        result = _run(work_root, args=args)
        print(f"sandbox artifacts: {work_root}")
        return result
    with tempfile.TemporaryDirectory(prefix="vibeflow-js-aot-e2e-") as raw:
        return _run(Path(raw), args=args)


def _run(root: Path, *, args: argparse.Namespace) -> int:
    _prepare_runtime_project(root)
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
        puppeteer_root = (
            args.puppeteer_root.resolve()
            if args.puppeteer_root is not None
            else _prepare_temporary_puppeteer(root / "puppeteer")
        )
        _run_browser(web.out_dir, puppeteer_root=puppeteer_root)

    print("JS AOT end-to-end: PASS")
    return 0


def _prepare_runtime_project(root: Path) -> None:
    global PROJECT_ROOT, WORKSPACE_PATH, CONFIG_PATH
    PROJECT_ROOT = root / "project"
    shutil.copytree(
        SOURCE_SANDBOX_ROOT / "project",
        PROJECT_ROOT,
        ignore=shutil.ignore_patterns(
            "node_modules", "__pycache__", "*.pyc", ".artifacts"
        ),
    )
    WORKSPACE_PATH = root / "vibeflow_config.jsonc"
    shutil.copy2(SOURCE_SANDBOX_ROOT / "vibeflow_config.jsonc", WORKSPACE_PATH)
    CONFIG_PATH = PROJECT_ROOT / "configs/greeting.jsonc"
    try:
        completed = subprocess.run(
            ["npm", "ci"], cwd=PROJECT_ROOT, check=False, text=True
        )
    except FileNotFoundError as exc:
        raise RuntimeError("npm is not available") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"npm ci failed with status {completed.returncode}")


def _prepare_temporary_puppeteer(destination: Path) -> Path:
    source = REPOSITORY_ROOT / "tools" / "mermaid-renderer"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(source / name, destination / name)
    try:
        completed = subprocess.run(
            ["npm", "ci"], cwd=destination, check=False, text=True
        )
    except FileNotFoundError as exc:
        raise RuntimeError("npm is not available") from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"temporary Puppeteer install failed with status {completed.returncode}"
        )
    return destination


if __name__ == "__main__":
    raise SystemExit(main())
