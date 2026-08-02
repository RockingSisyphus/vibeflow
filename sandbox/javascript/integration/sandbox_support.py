from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Thread
from typing import Any, Callable


SOURCE_SANDBOX_ROOT = Path(__file__).resolve().parent


def _find_environment_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        source_checkout = (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "src" / "vibeflow").is_dir()
        )
        distribution = (
            (candidate / "run.py").is_file()
            and (candidate / "kernel" / "vibeflow-kernel.zip").is_file()
        )
        if source_checkout or distribution:
            return candidate
    raise ImportError(
        "cannot locate VibeFlow; expected a source checkout or a built distribution"
    )


REPOSITORY_ROOT = _find_environment_root(SOURCE_SANDBOX_ROOT)
SANDBOX_ROOT = Path(
    os.environ.get("VIBEFLOW_SANDBOX_RUNTIME_ROOT", SOURCE_SANDBOX_ROOT)
).resolve()
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

from vibeflow.tooling.application.javascript.build import (  # noqa: E402
    ProjectBuildRequest,
    ProjectBuildResult,
    build_project_aot,
)
from vibeflow.targets.javascript.frontend.errors import AotBuildError  # noqa: E402
from vibeflow.tooling.application.javascript.build import ProjectBuildError  # noqa: E402


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


def run_browser_long_host(
    web_dir: Path,
    *,
    puppeteer_root: Path,
    module_entry: str | None,
) -> dict[str, Any]:
    """Exercise a permanent Host/Port workflow in a real browser page."""

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
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.goto({json.dumps(url)}, {{ waitUntil: "networkidle0" }});
  const payload = await page.evaluate(async moduleEntry => {{
    const state = globalThis.__vibeflowBrowserHarness;
    const assert = (condition, message) => {{
      if (!condition) throw new Error(message);
    }};
    const delay = milliseconds => new Promise(
      resolve => setTimeout(resolve, milliseconds),
    );
    const waitUntil = async (predicate, label, timeout = 5000) => {{
      const deadline = performance.now() + timeout;
      while (!predicate()) {{
        if (performance.now() >= deadline) {{
          throw new Error(`timed out waiting for ${{label}}`);
        }}
        await delay(10);
      }}
    }};
    const messages = kind => state.messages.filter(
      item => item && item.kind === kind,
    );

    assert(state.messages.length === 0, "page import produced host messages");
    const resolvedWorkflow = moduleEntry
      ? await import(new URL(moduleEntry, location.href).href)
      : await new Promise(resolve => {{
          document.dispatchEvent(new CustomEvent(
            "vibeflow-sandbox-request-workflow",
            {{ detail: {{ resolve }} }},
          ));
        }});
    assert(
      typeof resolvedWorkflow?.createWorkflowHost === "function",
      "workflow host factory is unavailable",
    );
    const afterImport = [...state.messages];
    assert(afterImport.length === 0, "module import started host work");

    const first = resolvedWorkflow.createWorkflowHost();
    const second = resolvedWorkflow.createWorkflowHost();
    const afterCreate = [...state.messages];
    assert(afterCreate.length === 0, "createWorkflowHost registered active work");

    window.postMessage({{
      kind: "vibeflow-sandbox-input",
      hostId: 1,
      value: 999,
    }}, "*");
    await waitUntil(
      () => messages("vibeflow-sandbox-input").length === 1,
      "pre-start message delivery",
    );

    await first.start();
    await waitUntil(
      () => messages("vibeflow-sandbox-lifecycle").filter(
        item => item.phase === "start",
      ).length === 1,
      "first Host Extension start",
    );
    window.postMessage({{
      kind: "vibeflow-sandbox-bind",
      hostId: 1,
    }}, "*");
    await waitUntil(
      () => messages("vibeflow-sandbox-bound").some(item => item.hostId === 1),
      "first Host Extension binding",
    );

    await second.start();
    await waitUntil(
      () => messages("vibeflow-sandbox-lifecycle").filter(
        item => item.phase === "start",
      ).length === 2,
      "second Host Extension start",
    );
    window.postMessage({{
      kind: "vibeflow-sandbox-bind",
      hostId: 2,
    }}, "*");
    await waitUntil(
      () => messages("vibeflow-sandbox-bound").some(item => item.hostId === 2),
      "second Host Extension binding",
    );

    for (const [hostId, value] of [[1, 4], [1, 7], [2, 10]]) {{
      window.postMessage({{
        kind: "vibeflow-sandbox-input",
        hostId,
        value,
      }}, "*");
    }}
    await waitUntil(
      () => messages("vibeflow-sandbox-input").length === 4,
      "queued browser inputs",
    );

    const firstInvocation = first.runWorkflowAsync({{}});
    const secondInvocation = second.runWorkflowAsync({{}});
    const observe = invocation => invocation.then(
      () => "completed",
      error => error?.code ?? String(error),
    );
    const firstObserved = observe(firstInvocation);
    const secondObserved = observe(secondInvocation);

    await waitUntil(() => {{
      const outputs = messages("vibeflow-sandbox-output");
      const waiting = messages("vibeflow-sandbox-waiting");
      return (
        outputs.length === 3
        && waiting.some(item => item.hostId === 1 && item.receiveCount === 3)
        && waiting.some(item => item.hostId === 2 && item.receiveCount === 2)
      );
    }}, "Port outputs and pending receives");

    const outputsBeforeStop = messages("vibeflow-sandbox-output");
    const firstOutputs = outputsBeforeStop
      .filter(item => item.hostId === 1)
      .map(item => item.value);
    const secondOutputs = outputsBeforeStop
      .filter(item => item.hostId === 2)
      .map(item => item.value);
    assert(
      JSON.stringify(firstOutputs) === "[14,23]",
      `first host outputs leaked or changed: ${{JSON.stringify(firstOutputs)}}`,
    );
    assert(
      JSON.stringify(secondOutputs) === "[32]",
      `second host outputs leaked or changed: ${{JSON.stringify(secondOutputs)}}`,
    );

    await Promise.all([first.stop(), second.stop()]);
    const failureCodes = await Promise.all([firstObserved, secondObserved]);
    await Promise.all([first.stop(), second.stop()]);
    await waitUntil(
      () => messages("vibeflow-sandbox-lifecycle").filter(
        item => item.phase === "stop",
      ).length === 2,
      "idempotent Host Extension stops",
    );
    await delay(50);

    assert(
      JSON.stringify(failureCodes) === '["VF_ABORTED","VF_ABORTED"]',
      `unexpected cancellation codes: ${{JSON.stringify(failureCodes)}}`,
    );
    assert(!first.started && !second.started, "stopped host reports started");
    assert(first.signal.aborted && second.signal.aborted, "host signal not aborted");
    assert(
      messages("vibeflow-sandbox-output").length === 3,
      "stop produced an additional output",
    );
    assert(
      state.unhandledRejections.length === 0,
      `unhandled rejections: ${{JSON.stringify(state.unhandledRejections)}}`,
    );
    const lifecycle = messages("vibeflow-sandbox-lifecycle");
    assert(
      lifecycle.filter(item => item.phase === "start").length === 2,
      "Host Extension started more than once",
    );
    assert(
      lifecycle.filter(item => item.phase === "stop").length === 2,
      "Host Extension stopped more than once",
    );
    return {{
      afterImport,
      afterCreate,
      failureCodes,
      firstOutputs,
      secondOutputs,
      waiting: messages("vibeflow-sandbox-waiting").map(item => ({{
        hostId: item.hostId,
        receiveCount: item.receiveCount,
      }})),
      lifecycle: lifecycle.map(item => ({{
        hostId: item.hostId,
        phase: item.phase,
      }})),
      unhandledRejections: state.unhandledRejections,
    }};
  }}, {json.dumps(module_entry)});
  if (pageErrors.length > 0) {{
    throw new Error(`browser page errors: ${{JSON.stringify(pageErrors)}}`);
  }}
  process.stdout.write(JSON.stringify({{ ...payload, pageErrors }}));
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
            timeout=90,
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
    expected_owner_id: str | None = None,
    expected_owner_kind: str | None = None,
    expected_file: Path | None = None,
    expected_line: int | None = None,
    expected_column: int | None = None,
) -> dict[str, Any]:
    try:
        builder()
    except (AotBuildError, ProjectBuildError) as exc:
        codes = diagnostic_codes(exc)
        if expected_code not in codes:
            raise AssertionError(
                f"expected {expected_code}, got {sorted(codes)}: {exc}"
            ) from exc
        matching = [
            item
            for item in getattr(exc, "diagnostics", ())
            if isinstance(item, dict) and item.get("code") == expected_code
        ]
        if any(
            value is not None
            for value in (
                expected_owner_id,
                expected_owner_kind,
                expected_file,
                expected_line,
                expected_column,
            )
        ):
            if not matching:
                raise AssertionError(
                    f"{expected_code} did not include a structured diagnostic"
                ) from exc
            diagnostic = matching[0]
            owner = diagnostic.get("owner")
            if expected_owner_id is not None:
                if not isinstance(owner, dict) or owner.get("id") != expected_owner_id:
                    raise AssertionError(
                        f"{expected_code} owner id: expected {expected_owner_id!r}, "
                        f"got {owner!r}"
                    ) from exc
            if expected_owner_kind is not None:
                if not isinstance(owner, dict) or owner.get("kind") != expected_owner_kind:
                    raise AssertionError(
                        f"{expected_code} owner kind: expected {expected_owner_kind!r}, "
                        f"got {owner!r}"
                    ) from exc
            if expected_file is not None:
                actual_file = diagnostic.get("file")
                actual_resolved = (
                    Path(actual_file).resolve()
                    if isinstance(actual_file, str)
                    else None
                )
                if actual_resolved != expected_file.resolve():
                    raise AssertionError(
                        f"{expected_code} file: expected {expected_file.resolve()}, "
                        f"got {actual_file!r}"
                    ) from exc
            if expected_line is not None and diagnostic.get("line") != expected_line:
                raise AssertionError(
                    f"{expected_code} line: expected {expected_line}, "
                    f"got {diagnostic.get('line')!r}"
                ) from exc
            if expected_column is not None and diagnostic.get("column") != expected_column:
                raise AssertionError(
                    f"{expected_code} column: expected {expected_column}, "
                    f"got {diagnostic.get('column')!r}"
                ) from exc
        return {
            "code": expected_code,
            "diagnostics": sorted(codes),
            "location": (
                {
                    "file": matching[0].get("file"),
                    "line": matching[0].get("line"),
                    "column": matching[0].get("column"),
                }
                if matching
                else None
            ),
        }
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


def prepare_temporary_puppeteer(destination: Path) -> Path:
    """Install the browser driver beside the temporary Sandbox workspace."""

    destination.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(DEFAULT_PUPPETEER_ROOT / name, destination / name)
    try:
        completed = subprocess.run(
            ["npm", "ci"], cwd=destination, check=False, text=True
        )
    except FileNotFoundError as exc:
        raise EnvironmentError("npm is not available") from exc
    if completed.returncode != 0:
        raise EnvironmentError(
            "temporary Puppeteer install failed with status "
            f"{completed.returncode}"
        )
    return destination


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
    "prepare_temporary_puppeteer",
    "run_browser",
    "run_browser_long_host",
    "run_node",
    "skip_case",
    "validate_environment",
    "write_report",
]
