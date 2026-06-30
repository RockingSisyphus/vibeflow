from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


class MermaidRenderError(RuntimeError):
    pass


def render_mermaid_svg(
    mermaid_text: str,
    output_path: str | Path,
    *,
    theme: str = "default",
    background: str = "transparent",
    timeout_seconds: int = 60,
) -> Path:
    """Render Mermaid source to SVG using the project-local Mermaid CLI."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    mmdc = _find_mmdc()
    _ensure_mermaid_cli_compat()
    with tempfile.TemporaryDirectory(prefix="topology-kernel-mermaid-") as temp_dir:
        temp = Path(temp_dir)
        input_path = temp / "graph.mmd"
        config_path = temp / "puppeteer.json"
        mermaid_config_path = temp / "mermaid.json"
        input_path.write_text(mermaid_text, encoding="utf-8")
        _write_puppeteer_config(config_path)
        _write_mermaid_config(mermaid_config_path)
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
    return output


def is_mermaid_svg_renderer_available() -> bool:
    try:
        _find_mmdc()
        return _find_chromium() is not None
    except MermaidRenderError:
        return False


def _find_mmdc() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
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


def _write_mermaid_config(path: Path) -> None:
    # foreignObject labels disappear in several SVG viewers/chat renderers.
    # Native SVG text is less fancy but reliably visible.
    config = {"htmlLabels": False, "flowchart": {"htmlLabels": False}, "markdownAutoWrap": False}
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_chromium() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_windows() -> bool:
    return __import__("os").name == "nt"
