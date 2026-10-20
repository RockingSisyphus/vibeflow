"""Resource observations; the outer runner owns the only worker queue."""
import importlib
from pathlib import Path

FAMILIES = ("registration", "ownership", "rules", "edits", "display", "runtime")
KINDS = ("node", "base_lib", "plugin", "host_extension")
SPLIT_FAMILIES = frozenset({"edits", "display"})


def resource_jobs():
    for family in FAMILIES:
        for part in (*KINDS, "extra") if family in SPLIT_FAMILIES else (None,):
            yield family, part


def validate_counts(rows):
    counts = {family: sum(row["family"] == family for row in rows) for family in (
        "resource-registration", "resource-ownership", "resource-rules", "resource-edits", "resource-display", "resource-runtime")}
    minima = (40, 48, 32, 32, 64, 24)
    if any(actual < minimum for actual, minimum in zip(counts.values(), minima)):
        raise ValueError(f"resource matrix incomplete: {counts}")


def run_cases(work_root: Path, variant="current", toolchain_root=None, *, family, part=None):
    if variant != "current":
        raise ValueError("resource cases require the current implementation")
    module = importlib.import_module("resource_" + family)
    options = {}
    if part is not None:
        options = {"kinds": () if part == "extra" else (part,), "include_extra": part == "extra"}
    return module.run_cases(work_root / family, toolchain_root, **options)
