from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from typing import Any, Callable


SANDBOX_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SANDBOX_ROOT.parents[1]
PROJECT_ROOT = SANDBOX_ROOT / "project"
CONFIG_ROOT = PROJECT_ROOT / "configs"
WORKSPACE_PATH = SANDBOX_ROOT / "vibeflow_config.jsonc"
REPORT_ROOT = SANDBOX_ROOT / "reports"
SOURCE_ROOT = REPOSITORY_ROOT / "src"
DISTRIBUTION_KERNEL_ARCHIVE = (
    REPOSITORY_ROOT / "kernel" / "vibeflow-kernel.zip"
)
REPOSITORY_PUPPETEER_ROOT = REPOSITORY_ROOT / "tools" / "mermaid-renderer"
DISTRIBUTION_PUPPETEER_ROOT = (
    REPOSITORY_ROOT / "kernel" / "tools" / "mermaid-renderer"
)
DEFAULT_PUPPETEER_ROOT = (
    REPOSITORY_PUPPETEER_ROOT
    if REPOSITORY_PUPPETEER_ROOT.is_dir()
    else DISTRIBUTION_PUPPETEER_ROOT
)


def _activate_vibeflow_kernel() -> None:
    """Prefer the colocated source tree or distributed kernel archive."""

    for candidate in (SOURCE_ROOT, DISTRIBUTION_KERNEL_ARCHIVE):
        if candidate.exists():
            sys.path.insert(0, str(candidate))
            return
    raise ImportError(
        "cannot locate VibeFlow: expected repository src/ or "
        f"distributed kernel archive at {DISTRIBUTION_KERNEL_ARCHIVE}"
    )


_activate_vibeflow_kernel()

from vibeflow.aot import (  # noqa: E402
    ProjectBuildRequest,
    ProjectBuildResult,
    build_project_aot,
)
from vibeflow.aot.errors import AotBuildError, ProjectBuildError  # noqa: E402


@dataclass(frozen=True)
class CaseResult:
    name: str
    status: str
    detail: str = ""
    payload: Any = None


class CaseSkipped(RuntimeError):
    pass


class BuildCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._items: dict[str, ProjectBuildResult] = {}
        self._requests: dict[str, tuple[str, ...]] = {}

    def build(
        self,
        key: str,
        config: str,
        *,
        target: str = "node",
        profile: str = "single-esm",
        html_template: Path | None = None,
        app_entry: Path | None = None,
    ) -> ProjectBuildResult:
        signature = (
            config,
            target,
            profile,
            str(html_template.resolve()) if html_template else "",
            str(app_entry.resolve()) if app_entry else "",
        )
        cached = self._items.get(key)
        if cached is not None:
            if self._requests[key] != signature:
                raise AssertionError(
                    f"build cache key {key!r} was reused for another request"
                )
            return cached
        result = build_project_aot(
            ProjectBuildRequest(
                workspace=WORKSPACE_PATH,
                config=CONFIG_ROOT / config,
                out_dir=self.root / key,
                target=target,
                profile=profile,
                html_template=html_template,
                app_entry=app_entry,
            )
        )
        self._items[key] = result
        self._requests[key] = signature
        return result


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def run_node(
    entry: Path,
    body: str,
    *,
    before_import: str = "",
    timeout: int = 30,
) -> Any:
    script = f"""
import {{ pathToFileURL }} from "node:url";
const moduleUrl = pathToFileURL({json.dumps(str(entry.resolve()))}).href;
{before_import}
const workflow = await import(moduleUrl);
const assert = (condition, message) => {{
  if (!condition) throw new Error(message);
}};
{body}
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=entry.parent,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Node consumer failed for {entry.name}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"Node consumer did not emit one JSON value: {completed.stdout!r}"
        ) from exc


def run_browser(
    web_dir: Path,
    *,
    puppeteer_root: Path,
    expected: str,
) -> dict[str, str]:
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
  const before = await page.$eval("#output", element => element.textContent ?? "");
  if (before !== "") throw new Error(`workflow auto-started: ${{before}}`);
  await page.click("#run");
  await page.waitForFunction(
    expected => document.querySelector("#output")?.textContent === expected,
    {{}},
    {json.dumps(expected)},
  );
  const after = await page.$eval("#output", element => element.textContent ?? "");
  process.stdout.write(JSON.stringify({{ before, after }}));
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
            raise AssertionError(
                completed.stderr.strip() or completed.stdout.strip()
            )
        return json.loads(completed.stdout)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def assert_equal(actual: Any, expected: Any, *, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_deterministic(first: Path, second: Path) -> dict[str, int]:
    first_files = _file_bytes(first)
    second_files = _file_bytes(second)
    changed = sorted(
        name
        for name in set(first_files) | set(second_files)
        if first_files.get(name) != second_files.get(name)
    )
    if changed:
        raise AssertionError(f"non-deterministic AOT outputs: {changed}")
    return {
        "files": len(first_files),
        "bytes": sum(len(value) for value in first_files.values()),
    }


def diagnostic_codes(error: BaseException) -> set[str]:
    codes: set[str] = set()
    code = getattr(error, "code", None)
    if isinstance(code, str):
        codes.add(code)
    diagnostics = getattr(error, "diagnostics", ())
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            continue
        diagnostic_code = diagnostic.get("code")
        if isinstance(diagnostic_code, str):
            codes.add(diagnostic_code)
    return codes


def expect_build_failure(
    builder: Callable[[], ProjectBuildResult],
    *,
    expected_code: str,
) -> dict[str, Any]:
    try:
        builder()
    except (AotBuildError, ProjectBuildError) as exc:
        codes = diagnostic_codes(exc)
        if expected_code not in codes:
            raise AssertionError(
                f"expected {expected_code}, got {sorted(codes)}: {exc}"
            ) from exc
        return {"code": expected_code, "diagnostics": sorted(codes)}
    raise AssertionError(f"build unexpectedly succeeded; wanted {expected_code}")


def skip_case(reason: str) -> None:
    raise CaseSkipped(reason)


def execute_cases(
    cases: list[tuple[str, Callable[[], Any]]],
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for name, case in cases:
        try:
            payload = case()
        except CaseSkipped as exc:
            result = CaseResult(name=name, status="SKIP", detail=str(exc))
        except Exception as exc:
            result = CaseResult(name=name, status="FAIL", detail=str(exc))
        else:
            result = CaseResult(name=name, status="PASS", payload=payload)
        results.append(result)
        suffix = f": {result.detail}" if result.detail else ""
        print(f"{result.status} {name}{suffix}")
    return results


def write_report(results: list[CaseResult]) -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "total": len(results),
        "passed": sum(item.status == "PASS" for item in results),
        "failed": sum(item.status == "FAIL" for item in results),
        "skipped": sum(item.status == "SKIP" for item in results),
        "results": [asdict(item) for item in results],
    }
    (REPORT_ROOT / "summary.json").write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    rows = [
        "# TypeScript sandbox report",
        "",
        f"- Total: {payload['total']}",
        f"- Passed: {payload['passed']}",
        f"- Failed: {payload['failed']}",
        f"- Skipped: {payload['skipped']}",
        "",
        "| Case | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for result in results:
        detail = result.detail.replace("|", "\\|").replace("\n", " ")
        rows.append(f"| `{result.name}` | {result.status} | {detail} |")
    (REPORT_ROOT / "summary.md").write_text(
        "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def validate_environment(*, puppeteer_root: Path, skip_browser: bool) -> None:
    missing = [
        name
        for name in ("typescript", "esbuild")
        if not (PROJECT_ROOT / "node_modules" / name).exists()
    ]
    if missing:
        raise EnvironmentError(
            "missing project-local toolchain "
            f"{missing}; run `npm ci` in {PROJECT_ROOT}"
        )
    try:
        completed = subprocess.run(
            ["node", "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise EnvironmentError("Node.js is not available") from exc
    if completed.returncode != 0:
        raise EnvironmentError("Node.js is not available")
    if not skip_browser and not (
        puppeteer_root / "node_modules" / "puppeteer"
    ).exists():
        raise EnvironmentError(
            f"Puppeteer is missing under {puppeteer_root}; install the "
            "colocated renderer dependencies or use "
            "--skip-browser"
        )


def _file_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


__all__ = [
    "BuildCache",
    "CONFIG_ROOT",
    "CaseResult",
    "DEFAULT_PUPPETEER_ROOT",
    "PROJECT_ROOT",
    "REPOSITORY_ROOT",
    "assert_deterministic",
    "assert_equal",
    "execute_cases",
    "expect_build_failure",
    "run_browser",
    "run_node",
    "skip_case",
    "validate_environment",
    "write_report",
]
