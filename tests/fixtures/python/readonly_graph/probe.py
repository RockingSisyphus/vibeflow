"""Measure shared source graphs without expanding their paths in the probe."""

import argparse
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
import json
from pathlib import Path
import sys
from time import perf_counter
from types import SimpleNamespace


REPOSITORY = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Pair:
    left: object
    right: object


def children(value):
    if isinstance(value, Mapping):
        return tuple(value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return tuple(getattr(value, item.name) for item in fields(value))
    if isinstance(value, SimpleNamespace):
        return tuple(vars(value).values())
    return None


def distinct_objects(value):
    counts = {}
    seen, pending = set(), [value]
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        descendants = children(item)
        if descendants is None:
            continue
        seen.add(id(item))
        name = "mapping" if isinstance(item, Mapping) else type(item).__name__
        counts[name] = counts.get(name, 0) + 1
        pending.extend(descendants)
    return counts


def shared_graph(kind, depth):
    shared = 1
    for _ in range(depth):
        if kind == "tuple":
            shared = (shared, shared)
        elif kind == "list":
            shared = [shared, shared]
        elif kind == "mapping":
            shared = {"left": shared, "right": shared}
        elif kind == "dataclass":
            shared = Pair(shared, shared)
        elif kind == "namespace":
            shared = SimpleNamespace(left=shared, right=shared)
        else:
            raise ValueError(kind)
    return shared


def sharing_preserved(value, depth):
    for _ in range(depth):
        if isinstance(value, Mapping):
            left, right = value["left"], value["right"]
        elif isinstance(value, (tuple, list)):
            left, right = value
        else:
            left, right = value.left, value.right
        if left is not right:
            return False
        value = left
    return value == 1


def observe(kind, depth, context_type):
    original = shared_graph(kind, depth)
    started = perf_counter()
    frozen = context_type(facts={"graph": original}).facts["graph"]
    seconds = perf_counter() - started
    # Large broken results are already identified by their lost sharing.
    output_counts = distinct_objects(frozen) if depth <= 12 or sharing_preserved(frozen, depth) else None
    return {"id": f"{kind}.{depth}", "kind": kind, "depth": depth,
            "input_objects": distinct_objects(original), "output_objects": output_counts,
            "seconds": seconds, "sharing_preserved": sharing_preserved(frozen, depth),
            "matched": sharing_preserved(frozen, depth)}


def observe_mixed(context_type):
    payload = {"values": [1, {"labels": ["original"]}]}
    pair = (payload, payload)
    source = {"pair": pair, "again": pair, "list": [pair, payload],
              "set": {"a"}, "frozen_set": frozenset({"b"})}
    original = {"first": source, "second": source, "set_alias": source["set"],
                "frozen_set_alias": source["frozen_set"]}
    frozen = context_type(facts=original).facts
    item = frozen["first"]
    aliases = (item is frozen["second"] and item["pair"] is item["again"]
               and item["pair"] is item["list"][0]
               and item["pair"][0] is item["pair"][1] is item["list"][1]
               and item["set"] is frozen["set_alias"]
               and item["frozen_set"] is frozen["frozen_set_alias"])
    blocked = []
    for container, key, value in ((item, "new", 1), (item["pair"], 0, {}),
                                   (item["pair"][0], "values", ()),
                                   (item["pair"][0]["values"], 0, 2)):
        try:
            container[key] = value
        except TypeError:
            blocked.append(True)
        else:
            blocked.append(False)
    payload["values"][1]["labels"].append("changed")
    source["set"].add("changed")
    isolated = (item["pair"][0]["values"][1]["labels"] == ("original",)
                and item["set"] == frozenset({"a"}))
    return {"id": "mixed.containers", "sharing_preserved": aliases,
            "mutation_blocked": all(blocked), "snapshot_isolated": isolated,
            "matched": aliases and all(blocked) and isolated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, help="source directory or released kernel ZIP")
    parser.add_argument("--depths", type=int, nargs="+", default=[4, 8, 12, 16, 20])
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str((args.kernel or REPOSITORY / "src").resolve()))
    from vibeflow.core.rules import RuleContext
    from vibeflow.core.rules import models

    cases = [observe("tuple", depth, RuleContext) for depth in args.depths]
    cases.extend(observe(kind, 12, RuleContext) for kind in ("list", "mapping", "dataclass", "namespace"))
    cases.append(observe_mixed(RuleContext))
    report = {"schema": "vibeflow.readonly-sharing.v1", "python": sys.version,
              "implementation": models.__file__, "cases": cases,
              "matched": all(case["matched"] for case in cases)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
