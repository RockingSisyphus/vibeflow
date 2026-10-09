"""Re-run saved current CLI observations without importing business Node bodies."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", type=Path, required=True, help="Product src directory")
    parser.add_argument("--report", type=Path, help="New output file; do not overwrite audit evidence")
    args = parser.parse_args()
    evidence = Path(__file__).resolve().parent
    bootstrap = (
        "import sys,json;sys.path.insert(0,sys.argv[1]);"
        "from vibeflow.tooling.application.python.cli import main;"
        "raise SystemExit(main(json.loads(sys.argv[2])))"
    )
    observations = []
    for config in sorted((evidence / "fixtures").glob("*/*/vibeflow_config.jsonc")):
        if config.parent.parent.name.startswith("before-"):
            continue
        root = config.parent
        argv = ["validate", "--workspace", str(config), "--config",
                str(root / "workflow.jsonc"), "--json"]
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", bootstrap, str(args.product.resolve()), json.dumps(argv)],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        payload = json.loads(result.stdout)
        observations.append({
            "case": root.name, "exit": result.returncode,
            "status": payload.get("status"),
            "codes": [item.get("code", item.get("rule_id")) for item in payload.get("errors", ())],
        })
    output = json.dumps(observations, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.resolve().write_text(output)
    print(output)

if __name__ == "__main__":
    main()

