"""Observe one group inside the caller's isolated current-kernel process."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--toolchain", type=Path)
    args = parser.parse_args()
    source = Path(__file__).with_name(args.group + ".py")
    spec = importlib.util.spec_from_file_location("rule_gaps_cases", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    rows = module.run_cases(args.work, "current", args.toolchain)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.group}: {len(rows)} observations", flush=True)


if __name__ == "__main__":
    main()
