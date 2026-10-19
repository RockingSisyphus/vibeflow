from __future__ import annotations

import html
from importlib.resources import files
import json
import math
import unicodedata
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
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
    enhance_labels: bool = True,
) -> Path:
    """Render SVG with project-local Mermaid dependencies over loopback HTTP."""

    _validate_positive_int("max_text_size", max_text_size)
    _validate_positive_int("max_edges", max_edges)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    mmdc = _find_mmdc()
    _ensure_mermaid_cli_compat()
    node = shutil.which("node")
    if node is None:
        raise MermaidRenderError("Node.js not found; install Node.js to render Mermaid SVG")
    errors: list[tuple[str, str]] = []
    skipped_snap = _snap_chromium_candidates()
    with tempfile.TemporaryDirectory(prefix="vibeflow-mermaid-") as temp_dir:
        temp = Path(temp_dir)
        input_path = temp / "graph.mmd"
        config_path = temp / "puppeteer.json"
        mermaid_config_path = temp / "mermaid.json"
        # Materialize both resources together: distribution kernels are ZIP-imported.
        for name in ("mermaid_http.mjs", "http_assets.mjs"):
            (temp / name).write_bytes(files(__package__).joinpath(name).read_bytes())
        supervisor = temp / "process_supervisor.py"
        supervisor.write_bytes(files("vibeflow.tooling.application").joinpath(supervisor.name).read_bytes())
        input_path.write_text(mermaid_text, encoding="utf-8")
        _write_mermaid_config(
            mermaid_config_path,
            max_text_size=max_text_size,
            max_edges=max_edges,
            html_labels=html_labels,
            node_padding=_doublecircle_padding(mermaid_text),
        )
        for attempt, (label, executable_path) in enumerate(_puppeteer_launch_options(), 1):
            if output.exists():
                output.unlink()
            _write_puppeteer_config(config_path, executable_path=executable_path)
            process_state = temp / f"process-{attempt}.json"
            command = [
                sys.executable, "-B", str(supervisor),
                "--state", str(process_state),
                "--timeout", str(timeout_seconds + 5), "--",
                node,
                str(temp / "mermaid_http.mjs"),
                "--renderer-cli",
                str(mmdc.resolve()),
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
                "--timeout",
                str(timeout_seconds),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds + 20)
            if completed.returncode == 0:
                if not output.exists():
                    raise MermaidRenderError(f"Mermaid renderer did not create {output}")
                _raise_on_error_svg(output)
                if enhance_labels and not html_labels:
                    _enhance_svg_labels(output)
                return output
            state = process_state.read_text() if process_state.exists() else "not available"
            detail = (f"Renderer supervisor returncode={completed.returncode}; process state: {state}\n"
                      f"stderr:\n{completed.stderr or '(empty)'}\nstdout:\n{completed.stdout or '(empty)'}")
            errors.append((label, detail))
    raise MermaidRenderError(_format_render_errors(errors, skipped_snap=skipped_snap))


def is_mermaid_svg_renderer_available() -> bool:
    try:
        _find_mmdc()
        return True
    except MermaidRenderError:
        return False


def _find_mmdc() -> Path:
    executable = "mmdc.cmd" if _is_windows() else "mmdc"
    for renderer_root in _renderer_roots():
        local = renderer_root / "node_modules" / ".bin" / executable
        if local.exists():
            return local
    found = shutil.which("mmdc")
    if found:
        return Path(found)
    raise MermaidRenderError(
        "Mermaid CLI not found; run `npm ci` in `tools/mermaid-renderer` "
        "for a source checkout or `kernel/tools/mermaid-renderer` for a distribution package"
    )


def _ensure_mermaid_cli_compat() -> None:
    for renderer_root in _renderer_roots():
        dist = renderer_root / "node_modules" / "mermaid" / "dist"
        expected = dist / "mermaid.esm.mjs"
        fallback = dist / "mermaid.core.mjs"
        if not expected.exists() and fallback.exists():
            expected.write_text(fallback.read_text(encoding="utf-8"), encoding="utf-8")


def _renderer_roots() -> tuple[Path, ...]:
    root = _repo_root()
    configured = os.environ.get("VIBEFLOW_MERMAID_RENDERER_ROOT", "").strip()
    roots: list[Path] = []
    if configured:
        roots.append(Path(configured).expanduser().resolve())
    roots.extend(
        (
        root / "tools" / "mermaid-renderer",
        root / "kernel" / "tools" / "mermaid-renderer",
        )
    )
    return tuple(dict.fromkeys(roots))


def _write_puppeteer_config(path: Path, *, executable_path: str | None = None) -> None:
    config: dict[str, object] = {"args": ["--no-sandbox", "--disable-setuid-sandbox"]}
    if executable_path:
        config["executablePath"] = executable_path
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _doublecircle_padding(mermaid_text: str) -> int:
    """Native dbl-circ uses label width for its radius, overlooking height.

    Supply native flowchart padding before layout, so edges and all bounds are
    computed by Mermaid. Half the full label height also fits the corners of
    its rectangle inside the circle; no SVG geometry or labels are replaced.
    """
    labels = re.findall(r'shape:\s*dbl-circ,\s*label:\s*"((?:\\.|[^"\\])*)"', mermaid_text, re.S)
    padding = 8
    for label in labels:
        rows = 0
        for line in html.unescape(label).replace(r"\n", "\n").splitlines():
            columns = sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in line)
            rows += max(1, math.ceil(columns * 10 / DEFAULT_FLOWCHART_WRAPPING_WIDTH))
        padding = max(padding, rows * 12 + 24)
    return padding


def _write_mermaid_config(path: Path, *, max_text_size: int, max_edges: int, html_labels: bool, node_padding: int = 8) -> None:
    # foreignObject labels disappear in several SVG viewers/chat renderers.
    # Native SVG text is less fancy but reliably visible.
    config = {
        "maxTextSize": max_text_size,
        "maxEdges": max_edges,
        "htmlLabels": html_labels,
        "flowchart": {
            "htmlLabels": html_labels,
            "padding": node_padding,
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
            raise MermaidRenderError(f"Mermaid renderer wrote an error SVG: {marker}")


_SVG_NS = "http://www.w3.org/2000/svg"
_MERMAID_CLOUD_NODE_CLASS = "vibeflowCloudNode"
_TRANSLATE_RE = re.compile(
    r"^\s*translate\(\s*"
    r"(?P<x>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?:\s*,\s*|\s+)"
    r"(?P<y>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s*\)\s*$"
)
_FIELD_PREFIXES = frozenset(
    {
        "id:",
        "type:",
        "type_used:",
        "type_key:",
        "status:",
        "when:",
        "data:",
        "stub:",
        "category:",
        "version:",
        "desc:",
        "nodeset:",
        "body:",
        "stop:",
        "max:",
        "module:",
        "class:",
        "config:",
        "external:",
        "effect_scope:",
        "execution_lock:",
    }
)


def _enhance_svg_labels(path: Path) -> None:
    try:
        ET.register_namespace("", _SVG_NS)
        tree = ET.parse(path)
        root = tree.getroot()
        changed = False
        for label_group in (*_node_groups(root), *_edge_label_groups(root)):
            is_node = "node" in _class_tokens(label_group)
            if is_node and _center_native_cloud_label(label_group):
                changed = True
            label_left = _label_left_x(label_group) if is_node else None
            for text in _label_texts(label_group):
                rows = [child for child in list(text) if _tag(child) == "tspan" and "row" in _class_tokens(child)]
                if not rows:
                    continue
                for index, row in enumerate(rows):
                    row_text = _row_text(row)
                    if not row_text:
                        continue
                    if index == 0:
                        _style_row(row, weight="700", font_size="1.05em")
                        changed = True
                        continue
                    if _is_separator_row(row_text):
                        _style_row(row, weight="700", fill="#64748b", font_size="0.92em")
                        changed = True
                        continue
                    if _is_field_row(row):
                        if label_left is not None:
                            row.set("x", _format_svg_number(label_left))
                            row.set("text-anchor", "start")
                        _style_field_prefix(row)
                        changed = True
        if changed:
            tree.write(path, encoding="unicode", xml_declaration=False)
    except Exception:
        return


def _node_groups(root: ET.Element) -> tuple[ET.Element, ...]:
    return tuple(element for element in root.iter() if _tag(element) == "g" and "node" in _class_tokens(element))


def _edge_label_groups(root: ET.Element) -> tuple[ET.Element, ...]:
    return tuple(element for element in root.iter() if _tag(element) == "g" and "edgeLabel" in _class_tokens(element))


def _label_texts(node: ET.Element) -> tuple[ET.Element, ...]:
    texts: list[ET.Element] = []
    for label in node.iter():
        if _tag(label) != "g" or "label" not in _class_tokens(label):
            continue
        texts.extend(element for element in label.iter() if _tag(element) == "text")
    return tuple(dict.fromkeys(texts))


def _label_left_x(node: ET.Element) -> float | None:
    for element in node.iter():
        if _tag(element) != "rect" or "label-container" not in _class_tokens(element):
            continue
        try:
            return float(element.get("x", "0")) + 14.0
        except ValueError:
            return None
    return None


def _center_native_cloud_label(node: ET.Element) -> bool:
    if _MERMAID_CLOUD_NODE_CLASS not in _class_tokens(node):
        return False
    label = next(
        (
            child
            for child in list(node)
            if _tag(child) == "g" and "label" in _class_tokens(child)
        ),
        None,
    )
    if label is None:
        return False
    match = _TRANSLATE_RE.fullmatch(label.get("transform", ""))
    if match is None:
        return False
    try:
        x = float(match.group("x"))
        y = float(match.group("y"))
    except ValueError:
        return False
    if abs(x) < 1e-9:
        return False
    label.set("transform", f"translate(0, {_format_svg_number(y)})")
    return True


def _style_row(row: ET.Element, *, weight: str, fill: str = "", font_size: str = "") -> None:
    for child in _inner_tspans(row):
        child.set("font-weight", weight)
        if fill:
            _append_style(child, f"fill:{fill} !important")
        if font_size:
            child.set("font-size", font_size)


def _style_field_prefix(row: ET.Element) -> None:
    for child in _inner_tspans(row):
        text = "".join(child.itertext()).strip()
        if text in _FIELD_PREFIXES:
            child.set("font-weight", "700")
            return


def _is_field_row(row: ET.Element) -> bool:
    first = next(iter(_inner_tspans(row)), None)
    return first is not None and "".join(first.itertext()).strip() in _FIELD_PREFIXES


def _is_separator_row(text: str) -> bool:
    return text.startswith("----")


def _inner_tspans(row: ET.Element) -> tuple[ET.Element, ...]:
    return tuple(child for child in list(row) if _tag(child) == "tspan")


def _row_text(row: ET.Element) -> str:
    return "".join(row.itertext()).strip()


def _append_style(element: ET.Element, declaration: str) -> None:
    existing = element.get("style", "").strip()
    if declaration in existing:
        return
    separator = ";" if existing and not existing.endswith(";") else ""
    element.set("style", f"{existing}{separator}{declaration}" if existing else declaration)


def _class_tokens(element: ET.Element) -> set[str]:
    return set(str(element.get("class", "")).split())


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _format_svg_number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


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
    lines = ["Mermaid HTTP renderer failed with all supported browser launch options."]
    if skipped_snap:
        lines.append(
            "Skipped snap Chromium because Puppeteer commonly fails to launch it with profile-lock errors: "
            + ", ".join(skipped_snap)
        )
    lines.append(
        "Run `npm ci` in `tools/mermaid-renderer` for a source checkout "
        "or `kernel/tools/mermaid-renderer` for a distribution package to install Puppeteer's browser, "
        "or install a non-snap Chrome/Chromium."
    )
    lines.append("The browser must allow HTTP to 127.0.0.1 for the temporary rendering server.")
    for label, detail in errors:
        lines.append(f"- {label}: {detail or 'Mermaid renderer failed'}")
    return "\n".join(lines)


def _repo_root() -> Path:
    module_path = Path(__file__).resolve()
    package_root: Path | None = None
    for parent in module_path.parents:
        if parent.suffix == ".zip":
            archive_directory = parent.parent
            return (
                archive_directory.parent
                if archive_directory.name == "kernel"
                else archive_directory
            )
        if (parent / "tools" / "mermaid-renderer" / "package.json").is_file():
            return parent
        if (parent / "kernel" / "tools" / "mermaid-renderer" / "package.json").is_file():
            return parent
        if parent.name == "vibeflow":
            package_root = parent
    if package_root is not None:
        package_container = package_root.parent
        if package_container.name in {"src", "kernel"}:
            return package_container.parent
        return package_container
    return module_path.parent


def _is_windows() -> bool:
    return os.name == "nt"
