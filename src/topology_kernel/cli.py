from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .compiler import GraphCompiler
from .graph_config import parse_graph_config
from .mermaid import export_mermaid


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="topology-kernel")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate topology config structure and compile graph")
    validate.add_argument("--config", required=True)

    mermaid = sub.add_parser("export-mermaid", help="export topology config to Mermaid flowchart")
    mermaid.add_argument("--config", required=True)
    mermaid.add_argument("--output", required=False)
    mermaid.add_argument("--expand-nodesets", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    graph = parse_graph_config(config)
    if args.command == "validate":
        compiled = GraphCompiler().compile(graph)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "nodes": len(graph.nodes),
                    "effective_edges": [edge.pair for edge in compiled.effective_edges],
                    "loops": [loop.name for loop in compiled.loops],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "export-mermaid":
        text = export_mermaid(graph, expand_nodesets=bool(args.expand_nodesets))
        output = getattr(args, "output", None)
        if output:
            Path(output).write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2
