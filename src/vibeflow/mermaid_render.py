from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


class MermaidRenderError(RuntimeError):
    pass


DEFAULT_MERMAID_MAX_TEXT_SIZE = 200_000
EXPANDED_MERMAID_MAX_TEXT_SIZE = 500_000
DEFAULT_MERMAID_MAX_EDGES = 2_000
EXPANDED_MERMAID_MAX_EDGES = 5_000
DEFAULT_FLOWCHART_NODE_SPACING = 80
DEFAULT_FLOWCHART_RANK_SPACING = 90
DEFAULT_FLOWCHART_WRAPPING_WIDTH = 360
DEFAULT_FLOWCHART_DIAGRAM_PADDING = 24

_MERMAID_ERROR_TEXT_MARKERS = (
    "Maximum text size in diagram exceeded",
    "Edge limit exceeded",
    "Syntax error in text",
    "Parse error on line",
)


def render_mermaid_svg(
    mermaid_text: str,
    output_path: str | Path,
    *,
    theme: str = "default",
    background: str = "transparent",
    timeout_seconds: int = 60,
    max_text_size: int = DEFAULT_MERMAID_MAX_TEXT_SIZE,
    max_edges: int = DEFAULT_MERMAID_MAX_EDGES,
    html_labels: bool = False,
) -> Path:
    """Render Mermaid source to SVG using the project-local Mermaid CLI."""

    _validate_positive_int("max_text_size", max_text_size)
    _validate_positive_int("max_edges", max_edges)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    mmdc = _find_mmdc()
    _ensure_mermaid_cli_compat()
    errors: list[tuple[str, str]] = []
    skipped_snap = _snap_chromium_candidates()
    with tempfile.TemporaryDirectory(prefix="vibeflow-mermaid-") as temp_dir:
        temp = Path(temp_dir)
        input_path = temp / "graph.mmd"
        config_path = temp / "puppeteer.json"
        mermaid_config_path = temp / "mermaid.json"
        input_path.write_text(mermaid_text, encoding="utf-8")
        _write_mermaid_config(
            mermaid_config_path,
            max_text_size=max_text_size,
            max_edges=max_edges,
            html_labels=html_labels,
        )
        for label, executable_path in _puppeteer_launch_options():
            if output.exists():
                output.unlink()
            _write_puppeteer_config(config_path, executable_path=executable_path)
            command = [
                str(mmdc),
                "--input",
                str(input_path),
                "--output",
                str(output),
                "--theme",
                theme,
                "--backgroundColor",
                background,
                "--configFile",
                str(mermaid_config_path),
                "--puppeteerConfigFile",
                str(config_path),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
            if completed.returncode == 0:
                if not output.exists():
                    raise MermaidRenderError(f"Mermaid CLI did not create {output}")
                _raise_on_error_svg(output)
                return output
            detail = (completed.stderr or completed.stdout or "Mermaid CLI failed").strip()
            errors.append((label, detail))
    raise MermaidRenderError(_format_render_errors(errors, skipped_snap=skipped_snap))


def is_mermaid_svg_renderer_available() -> bool:
    try:
        _find_mmdc()
        return True
    except MermaidRenderError:
        return False


def _find_mmdc() -> Path:
    repo_root = _repo_root()
    local = repo_root / "tools" / "mermaid-renderer" / "node_modules" / ".bin" / ("mmdc.cmd" if _is_windows() else "mmdc")
    if local.exists():
        return local
    found = shutil.which("mmdc")
    if found:
        return Path(found)
    raise MermaidRenderError("Mermaid CLI not found; run `npm install` in tools/mermaid-renderer")


def _ensure_mermaid_cli_compat() -> None:
    dist = _repo_root() / "tools" / "mermaid-renderer" / "node_modules" / "mermaid" / "dist"
    expected = dist / "mermaid.esm.mjs"
    fallback = dist / "mermaid.core.mjs"
    if not expected.exists() and fallback.exists():
        expected.write_text(fallback.read_text(encoding="utf-8"), encoding="utf-8")


def _write_puppeteer_config(path: Path, *, executable_path: str | None = None) -> None:
    config: dict[str, object] = {"args": ["--no-sandbox", "--disable-setuid-sandbox"]}
    if executable_path:
        config["executablePath"] = executable_path
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_mermaid_config(path: Path, *, max_text_size: int, max_edges: int, html_labels: bool) -> None:
    # foreignObject labels disappear in several SVG viewers/chat renderers.
    # Native SVG text is less fancy but reliably visible.
    config = {
        "maxTextSize": max_text_size,
        "maxEdges": max_edges,
        "htmlLabels": html_labels,
        "flowchart": {
            "htmlLabels": html_labels,
            "nodeSpacing": DEFAULT_FLOWCHART_NODE_SPACING,
            "rankSpacing": DEFAULT_FLOWCHART_RANK_SPACING,
            "wrappingWidth": DEFAULT_FLOWCHART_WRAPPING_WIDTH,
            "diagramPadding": DEFAULT_FLOWCHART_DIAGRAM_PADDING,
        },
        "markdownAutoWrap": False,
    }
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _raise_on_error_svg(path: Path) -> None:
    svg_text = path.read_text(encoding="utf-8", errors="ignore")
    visible_text = _strip_svg_tags(svg_text)
    for marker in _MERMAID_ERROR_TEXT_MARKERS:
        if marker in visible_text:
            raise MermaidRenderError(f"Mermaid CLI wrote an error SVG: {marker}")


def _strip_svg_tags(svg_text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", svg_text)
    return " ".join(html.unescape(text).split())


def _validate_positive_int(name: str, value: int) -> None:
    if not isinstance(value, int) or value <= 0:
        raise MermaidRenderError(f"Mermaid {name} must be a positive integer")


def _puppeteer_launch_options() -> list[tuple[str, str | None]]:
    options: list[tuple[str, str | None]] = [("Puppeteer bundled browser", None)]
    options.extend((path, path) for path in _system_browser_candidates())
    return options


def _system_browser_candidates() -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if not found or _is_snap_chromium(found) or found in seen:
            continue
        candidates.append(found)
        seen.add(found)
    return candidates


def _find_chromium() -> str | None:
    candidates = _system_browser_candidates()
    return candidates[0] if candidates else None


def _snap_chromium_candidates() -> list[str]:
    candidates: list[str] = []
    for name in ("chromium", "chromium-browser"):
        found = shutil.which(name)
        if found and _is_snap_chromium(found):
            candidates.append(found)
    return candidates


def _is_snap_chromium(path: str) -> bool:
    browser_path = Path(path)
    return browser_path.name in {"chromium", "chromium-browser"} and browser_path.as_posix().startswith("/snap/")


def _format_render_errors(errors: list[tuple[str, str]], *, skipped_snap: list[str]) -> str:
    lines = ["Mermaid CLI failed to render SVG with all supported browser launch options."]
    if skipped_snap:
        lines.append(
            "Skipped snap Chromium because Puppeteer commonly fails to launch it with profile-lock errors: "
            + ", ".join(skipped_snap)
        )
    lines.append("Run `npm install` in tools/mermaid-renderer to install Puppeteer's browser, or install a non-snap Chrome/Chromium.")
    for label, detail in errors:
        first_line = detail.splitlines()[0] if detail else "Mermaid CLI failed"
        lines.append(f"- {label}: {first_line}")
    return "\n".join(lines)


def _repo_root() -> Path:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if parent.suffix == ".zip":
            return parent.parent.parent
    return module_path.parents[2]


def _is_windows() -> bool:
    return __import__("os").name == "nt"
