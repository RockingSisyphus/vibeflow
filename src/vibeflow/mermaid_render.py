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
    with tempfile.TemporaryDirectory(prefix="vibeflow-mermaid-") as temp_dir:
        temp = Path(temp_dir)
        input_path = temp / "graph.mmd"
        config_path = temp / "puppeteer.json"
        mermaid_config_path = temp / "mermaid.json"
        input_path.write_text(mermaid_text, encoding="utf-8")
        _write_puppeteer_config(config_path)
        _write_mermaid_config(
            mermaid_config_path,
            max_text_size=max_text_size,
            max_edges=max_edges,
            html_labels=html_labels,
        )
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
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Mermaid CLI failed").strip()
        raise MermaidRenderError(detail)
    if not output.exists():
        raise MermaidRenderError(f"Mermaid CLI did not create {output}")
    _raise_on_error_svg(output)
    return output


def is_mermaid_svg_renderer_available() -> bool:
    try:
        _find_mmdc()
        return _find_chromium() is not None
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


def _write_puppeteer_config(path: Path) -> None:
    config: dict[str, object] = {"args": ["--no-sandbox", "--disable-setuid-sandbox"]}
    chromium = _find_chromium()
    if chromium:
        config["executablePath"] = chromium
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_mermaid_config(path: Path, *, max_text_size: int, max_edges: int, html_labels: bool) -> None:
    # foreignObject labels disappear in several SVG viewers/chat renderers.
    # Native SVG text is less fancy but reliably visible.
    config = {
        "maxTextSize": max_text_size,
        "maxEdges": max_edges,
        "htmlLabels": html_labels,
        "flowchart": {"htmlLabels": html_labels},
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


def _find_chromium() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _repo_root() -> Path:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if parent.suffix == ".zip":
            return parent.parent.parent
    return module_path.parents[2]


def _is_windows() -> bool:
    return __import__("os").name == "nt"
