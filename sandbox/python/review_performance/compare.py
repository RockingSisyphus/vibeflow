"""Compare fresh-process observations without importing the inspected kernel."""

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

REPRESENTATIVE = ("shared-8-1", "shared-32-4", "shared-80-8")
COUNTERS = ("calls", "presentation_calls", "rules", "compiled_graphs",
            "parsing_counts", "compilation_counts")


def normalized(value, root):
    if isinstance(value, str):
        return value.replace(root, "<fixture>")
    if isinstance(value, dict):
        return {normalized(key, root): normalized(child, root)
                for key, child in value.items()}
    if isinstance(value, list):
        return [normalized(child, root) for child in value]
    return value


def serial(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def diagnostics(value, prefix=""):
    if not isinstance(value, dict):
        return []
    if isinstance(value.get("errors"), list) and isinstance(value.get("warnings"), list):
        report = {"scope": prefix, "status": value.get("status"),
                  "errors": value["errors"], "warnings": value["warnings"],
                  "skipped": value.get("skipped", [])}
        nested = [item for index, child in enumerate(value.get("reports", []))
                  for item in diagnostics(child, prefix + f"/reports/{index}")]
        return [report, *nested]
    return [item for key in ("health", "validation")
            for item in diagnostics(value.get(key), prefix + "/" + key)]


def output_snapshot(case):
    root = Path(case["artifact_root"])
    output = (root / "observation.stdout.txt").read_text()
    payload = None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        pass
    reports = diagnostics(payload)
    if not reports:
        runtime = root / "runs" / "observed" / "health_report.json"
        if runtime.exists():
            reports = diagnostics(json.loads(runtime.read_text()), "/run/health_report")
    return {"cli_status": payload.get("status") if isinstance(payload, dict) else None,
            "diagnostics_available": bool(reports),
            "diagnostics": normalized(reports, str(root))}


def stable_counts(cases):
    variants = {}
    for field in COUNTERS:
        values = [normalized(case.get(field, {}), case["artifact_root"]) for case in cases]
        stable = len({serial(value) for value in values}) == 1
        variants[field] = {"stable": stable, "value": values[0] if stable else values}
    return variants


def diagnose(before, after):
    before_cases = {(case["id"], case.get("iteration", 0)): case for case in before["cases"]}
    after_cases = {(case["id"], case.get("iteration", 0)): case for case in after["cases"]}
    comparisons = []
    for key in sorted(before_cases.keys() & after_cases.keys()):
        old, new = before_cases[key], after_cases[key]
        old_output, new_output = output_snapshot(old), output_snapshot(new)
        old_findings = Counter(serial(finding) for report in old_output["diagnostics"]
                               for field in ("errors", "warnings", "skipped")
                               for finding in report[field])
        new_findings = Counter(serial(finding) for report in new_output["diagnostics"]
                               for field in ("errors", "warnings", "skipped")
                               for finding in report[field])
        comparisons.append({"id": key[0], "iteration": key[1],
            "exit_codes": [old["exit_code"], new["exit_code"]],
            "exit_code_equal": old["exit_code"] == new["exit_code"],
            "cli_status_equal": old_output["cli_status"] == new_output["cli_status"],
            "diagnostics_available": old_output["diagnostics_available"] and new_output["diagnostics_available"],
            "reports_equal": old_output["diagnostics"] == new_output["diagnostics"],
            "findings_before": sum(old_findings.values()),
            "findings_after": sum(new_findings.values()),
            "removed_findings": [json.loads(item) for item in (old_findings - new_findings).elements()],
            "added_findings": [json.loads(item) for item in (new_findings - old_findings).elements()]})
    return {"case_sets_equal": before_cases.keys() == after_cases.keys(),
            "before_only": sorted(before_cases.keys() - after_cases.keys()),
            "after_only": sorted(after_cases.keys() - before_cases.keys()),
            "compared": len(comparisons),
            "available_diagnostic_comparisons": sum(item["diagnostics_available"] for item in comparisons),
            "cases": comparisons}


def comparison(before_path, after_path, stage):
    before, after = (json.loads(path.read_text()) for path in (before_path, after_path))
    rows = []
    for identifier in REPRESENTATIVE:
        old = [case for case in before["cases"] if case["id"] == identifier]
        new = [case for case in after["cases"] if case["id"] == identifier]
        before_time = statistics.median(case["seconds"] for case in old)
        after_time = statistics.median(case["seconds"] for case in new)
        rows.append({"id": identifier, "before_iterations": len(old), "after_iterations": len(new),
            "before_samples_seconds": [case["seconds"] for case in old],
            "after_samples_seconds": [case["seconds"] for case in new],
            "before_median_seconds": before_time, "after_median_seconds": after_time,
            "speedup_ratio": before_time / after_time,
            "latency_reduction_percent": 100 * (1 - after_time / before_time),
            "before_counts": stable_counts(old), "after_counts": stable_counts(new),
            "inclusive_stage_medians_seconds": {
                phase: {"before": statistics.median(case.get("inclusive_seconds", {}).get(phase, 0) for case in old),
                        "after": statistics.median(case.get("inclusive_seconds", {}).get(phase, 0) for case in new)}
                for phase in sorted({phase for case in (*old, *new) for phase in case.get("inclusive_seconds", {})})}})
    return {"schema": "vibeflow.review-performance.comparison.v1", "stage": stage,
        "inputs": {"before": str(before_path), "after": str(after_path)},
        "input_matched": {"before": before["matched"], "after": after["matched"]},
        "input_observation_errors": {"before": before["observation_errors"], "after": after["observation_errors"]},
        "input_failed_cases": {name: [{"id": case["id"], "iteration": case.get("iteration", 0),
                                       "failures": case["failures"]}
                                      for case in batch["cases"] if not case["matched"]]
                               for name, batch in (("before", before), ("after", after))},
        "fresh_process_medians": rows, "diagnostic_comparison": diagnose(before, after),
        "boundaries": [
            "All recorded iterations execute the real CLI in separate Python processes; caches do not persist between commands.",
            "Medians are descriptive local results from three runs per representative fixture, not a portable performance guarantee.",
            "Inclusive stage times overlap and must not be added into a wall-clock time breakdown.",
            "The AST copy counter observes source_context.deepcopy; zero does not claim that the entire kernel performs no deepcopy or that public rule AST views have lost isolation.",
            "The aggregate ast.parse counter also includes generated/fingerprint parsing; parsing_counts records project filenames separately.",
            "Only fixture path prefixes are normalized in diagnostic comparisons; codes, severity, locations, reasons, details and multiplicity remain significant.",
            "Commands without structured health reports are compared for exit code and structured CLI status, not claimed to have full diagnostic equivalence.",
            "This audit uses standalone VibeFlow fixtures; it does not establish downstream training or MNIST acceptance.",
            "An intermediate batch with a failed parsing-count assertion is evidence for investigation and is not final acceptance."]}


def draft(data):
    rows = ["# VibeFlow performance evidence draft", "", f"Stage: `{data['stage']}`.", ""]
    if not data["input_matched"]["after"]:
        rows += ["The compared after-batch has failed assertions and is intermediate evidence.",
                 "Its known quality-check source parse count failure is retained in the machine report.",
                 "Use the subsequent full-verification report for final acceptance.", ""]
    rows += [
            "| Fresh-process fixture | Before median | After median | Speedup | Latency reduction |",
            "| --- | ---: | ---: | ---: | ---: |"]
    for item in data["fresh_process_medians"]:
        rows.append(f"| {item['id']} | {item['before_median_seconds']:.3f}s | {item['after_median_seconds']:.3f}s | "
                    f"{item['speedup_ratio']:.2f}x | {item['latency_reduction_percent']:.1f}% |")
    rows += ["", "Each group contains three independently launched CLI processes.", "",
             "| Fixture | Captured Target AST copies | Public tree reads | Public node reads | Compile | Presentation compile/bind/rule plan |",
             "| --- | ---: | ---: | ---: | ---: | --- |"]
    for item in data["fresh_process_medians"]:
        old = item["before_counts"]["calls"]["value"]
        new = item["after_counts"]["calls"]["value"]
        before_p = item["before_counts"]["presentation_calls"]["value"]
        after_p = item["after_counts"]["presentation_calls"]["value"]
        pair = lambda key: f"{old.get(key, 0)} → {new.get(key, 0)}"
        presentation = " / ".join(f"{before_p.get(key, 0)} → {after_p.get(key, 0)}"
                                  for key in ("compile", "bind", "rule_plan"))
        rows.append(f"| {item['id']} | {pair('ast_copy')} | {pair('tree_reads')} | {pair('node_reads')} | {pair('compile')} | {presentation} |")
    comparison = data["diagnostic_comparison"]
    different = [item for item in comparison["cases"] if not item["reports_equal"]
                 or not item["exit_code_equal"] or not item["cli_status_equal"]]
    rows += ["", f"Cases compared: {comparison['compared']}; structured diagnostics available: "
             f"{comparison['available_diagnostic_comparisons']}; differences: {len(different)}.", ""]
    rows += ["- " + value for value in data["boundaries"]]
    return "\n".join(rows) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--stage", default="intermediate-quality-parse-count-failed")
    args = parser.parse_args()
    result = comparison(args.before, args.after, args.stage)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    if args.draft:
        args.draft.write_text(draft(result))
    print(json.dumps({"stage": result["stage"], "inputs_matched": result["input_matched"],
        "timings": [{key: row[key] for key in ("id", "before_median_seconds", "after_median_seconds", "speedup_ratio")}
                    for row in result["fresh_process_medians"]],
        "diagnostic_cases": result["diagnostic_comparison"]["available_diagnostic_comparisons"],
        "differences": [{"id": row["id"], "removed": len(row["removed_findings"]),
                         "added": len(row["added_findings"])}
                       for row in result["diagnostic_comparison"]["cases"] if not row["reports_equal"]]}, indent=2))


if __name__ == "__main__":
    main()
