"""Observe one group inside the caller's isolated current-kernel process."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import signal
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--toolchain", type=Path)
    args = parser.parse_args()
    import common
    args.output.parent.mkdir(parents=True, exist_ok=True)
    journal = args.output.with_suffix(".partial.jsonl")
    if args.output.exists() or journal.exists():
        parser.error("observation output already exists; use a new work/output path")
    journal.write_text("", encoding="utf-8")
    common.OBSERVATION_JOURNAL = journal
    def terminate(number, _frame):
        raise SystemExit(128 + number)
    signal.signal(signal.SIGTERM, terminate)
    source = Path(__file__).with_name(args.group + ".py")
    spec = importlib.util.spec_from_file_location("rule_gaps_cases", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        rows = module.run_cases(args.work, "current", args.toolchain)
        temp = args.output.with_suffix(".tmp")
        temp.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(args.output)
    except BaseException as error:
        failure = {"status": "interrupted" if isinstance(error, (SystemExit, KeyboardInterrupt)) else "failed",
                   "error": str(error), "traceback": traceback.format_exc(), "partial_journal": str(journal)}
        args.output.with_suffix(".error.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2))
        raise
    print(f"{args.group}: {len(rows)} observations", flush=True)


if __name__ == "__main__":
    main()
