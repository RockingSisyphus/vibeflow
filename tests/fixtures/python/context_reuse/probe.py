"""Measure frozen-fact traversal when deriving RuleContext subjects."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from time import perf_counter
from types import MappingProxyType
from unittest.mock import patch


def observe():
    from vibeflow.core.rules import RuleContext
    from vibeflow.core.rules import models
    facts = {"analysis": [{"values": list(range(8))} for _ in range(1000)]}
    base = RuleContext(facts=facts, subject={"definition_id": "probe.first"}, scope={"files": ["nodes.py"]})
    results = []
    for name, change in (
        ("subject", {"subject": {"type_key": "probe.second"}}),
        ("phase", {"phase": "run"}),
        ("fact_overlay", {"facts": {**base.facts, "metrics": {"lines": [1]}}}),
        ("source_projection", {"facts": dict(base.facts), "scope": {"files": base.scope["files"]}}),
    ):
        visits = 0
        original = models.readonly
        def counted(value, memo=None):
            nonlocal visits
            visits += 1
            return original(value, memo)
        started = perf_counter()
        with patch.object(models, "readonly", counted):
            derived = replace(base, **change)
        elapsed = perf_counter() - started
        protected = False
        try:
            derived.facts["analysis"][0]["values"][0] = 99
        except TypeError:
            protected = True
        results.append({"id": name, "readonly_visits": visits, "seconds": elapsed,
            "analysis_reused": derived.facts["analysis"] is base.facts["analysis"],
            "facts_reused": derived.facts is base.facts,
            "protected": protected,
            "matched": visits < 40 and derived.facts["analysis"] is base.facts["analysis"] and protected})
    original = {"items": [1]}
    derived = replace(base, facts={**base.facts, "new": MappingProxyType(original)})
    original["items"].append(2)
    isolated = derived.facts["new"]["items"] == (1,)
    results.append({"id":"external_shallow_proxy", "matched":isolated, "isolated":isolated})
    return {"schema":"vibeflow.context-reuse.v1", "cases":results,
            "matched":all(item["matched"] for item in results), "implementation":models.__file__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, default=Path(__file__).resolve().parents[4] / "src")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.kernel.resolve()))
    result = observe()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
