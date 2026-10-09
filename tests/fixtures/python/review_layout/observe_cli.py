"""Instrument the actual CLI renderer without replacing its rendering work."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import json
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET


def titles(text):
    root = ET.fromstring(text)
    return [{"title":item.text, "x":float(item.get("x")), "y":float(item.get("y"))}
            for item in root if item.tag.endswith("}text") and item.get("class") == "review-title"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    commands = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    args.report.parent.mkdir(parents=True, exist_ok=True)
    from vibeflow.tooling.application.python.presentation.mermaid import review_fragments as fragments
    from vibeflow.tooling.application.python.presentation.mermaid import review_svg
    from vibeflow.tooling.application.cli import main as cli_main
    frames, panels, columns = [], [], []
    original_fragment = fragments._render_fragment
    original_panel = fragments._compose_detail_panel_svg
    original_compose = review_svg._compose_svg

    def capture_fragment(title, mermaid, *positional, **options):
        index = len(frames)
        path = args.report.parent / f"fragment-{index:02d}.mmd"
        path.write_text(mermaid)
        record = {"title":title, "direction":mermaid.splitlines()[0], "mermaid_path":str(path),
                  "resource_groups":re.findall(r"\b(resource_(?:plugins|base_lib|host_extensions))@", mermaid),
                  "has_resource_nodes":"vf_resource_" in mermaid}
        frames.append(record)
        result = original_fragment(title, mermaid, *positional, **options)
        record.update(width=result.width, height=result.height)
        return result

    def capture_panel(parent, children, **options):
        result = original_panel(parent, children, **options)
        panels.append({"parent":parent.title, "children":[item.title for item in children],
                       "positions":titles(result)})
        return result

    def capture_columns(value, **options):
        columns.extend([[item.title for item in group] for group in value])
        return original_compose(value, **options)

    fragments._render_fragment = review_svg._render_fragment = capture_fragment
    fragments._compose_detail_panel_svg = capture_panel
    review_svg._compose_svg = capture_columns
    started = time.perf_counter()
    error = None
    with args.report.with_suffix(".stdout.txt").open("w") as stdout:
        with args.report.with_suffix(".stderr.txt").open("w") as stderr:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                try:
                    code = cli_main(commands)
                except Exception as caught:
                    error, code = repr(caught), 2
    payload = {"exit_code":code, "error":error, "frames":frames, "panels":panels,
               "columns":columns, "seconds":time.perf_counter()-started, "arguments":commands}
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"report":str(args.report), "exit_code":code, "error":error}))
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

