"""运行完整整数公式或独立的平方与差距计算。"""

import argparse
import asyncio
import json
from pathlib import Path

from vibeflow.coordination import Coordinator
from vibeflow.targets.python.runtime.workflow_host import bind_workflow
from vibeflow.tooling.application.python import load_bundle


async def calculate(build_dir, x, y):
    scope = Coordinator()
    try:
        for name in ("formula", "product"):
            bundle = load_bundle(build_dir / name)
            bind_workflow(scope, bundle.workflow_descriptor, bundle.create_runtime)
        return scope.invoke_sync({
            "workflow": {"root": "formula", "path": "configs/计算完整公式.jsonc"},
            "inputs": {"x": x, "y": y},
        })["result"]
    finally:
        await scope.aclose()


def main():
    parser = argparse.ArgumentParser(description="计算 (x + y) × (x + y + 1) + 2 × (x − y) + x² + y² + |x − y|。")
    parser.add_argument("--build-dir", type=Path, required=True, help="完整公式需要 formula 和 product，独立计算只需要 score")
    parser.add_argument("--x", type=int, required=True, help="第一个整数")
    parser.add_argument("--y", type=int, required=True, help="第二个整数")
    parser.add_argument("--square-gap-only", action="store_true", help="单独运行复用 Nodeset 的工作流")
    args = parser.parse_args()
    if args.square_gap_only:
        bundle = load_bundle(args.build_dir / "score")
        result = bundle.run({"x": args.x, "y": args.y})
        output = {"平方与差距项": result.public_outputs["square_gap"]}
    else:
        output = asyncio.run(calculate(args.build_dir, args.x, args.y))
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
