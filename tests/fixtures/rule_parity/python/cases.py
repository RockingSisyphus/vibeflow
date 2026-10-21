"""Run Python baseline-rule observations against the caller-selected kernel.

No VibeFlow import happens while loading this module.  The parent chooses
PYTHONPATH and calls this in a separate process for each kernel variant.
"""

from pathlib import Path
import runpy


def run_cases(work_root: Path, variant: str, toolchain_root: Path | None = None) -> list[dict]:
    if variant not in {"baseline", "current"}:
        raise ValueError(f"unknown kernel variant: {variant}")
    del toolchain_root  # Python cases do not require the JavaScript toolchain.
    directory = Path(__file__).parent
    runner = runpy.run_path(str(directory / "fixture.py"))["observe"]
    specs = []
    for filename in (
        "node_specs.py", "library_specs.py", "source_specs.py", "coupling_specs.py",
        "authority_variants.py", "numeric_variants.py", "effect_variants.py",
        "ownership_variants.py", "library_variants.py", "import_variants.py",
    ):
        specs.extend(runpy.run_path(str(directory / filename))["case_specs"]())
    # Preserve baseline expectations; current-only changes follow the approved product boundary.
    retired_ids = {
        "python.contract.decision_missing_route": "B08",
        "python.contract.overlap": "B08",
        "python.contract.example_outputs_removed": "B08",
        "python.metrics.recursive_helper": "B04",
        "python.purity.dynamic_eval": "B06",
        "python.purity.setattr": "B05",
        "python.purity.resource_field": "B05",
        "python.purity.internal_while": "B04",
        "python.purity.dynamic_output": "B02",
        "python.purity.undeclared_output": "B02",
        "python.purity.missing_output": "B02",
        "python.purity.runtime_dispatch": "B03",
        "python.imports.alias_eval": "B06",
        "python.imports.ffi_policy_allow": "B06",
        "python.helpers.same_file_input_mutation": "B01",
        "python.helpers.cross_file_input_mutation": "B01",
        "python.library.scan_dynamic_namespace": "B06",
    }
    for suffix in ("eval_builtin_alias", "eval_assignment_alias", "dynamic_import_alias", "globals_lookup", "locals_lookup", "vars_sensitive", "dunder_sensitive", "ffi_root_alias", "callback_hook"):
        retired_ids["python.variant.effect." + suffix] = "B06"
    for suffix in ("get_alias", "conditional_alias", "helper_position", "helper_keyword", "helper_chain", "class_helper_position", "class_helper_keyword"):
        retired_ids["python.variant.ownership." + suffix] = "B01"
    for suffix in ("namespace_locals", "namespace_sensitive"):
        retired_ids["python.variant.library." + suffix] = "B06"
    if variant=="current":
        specs=[spec for spec in specs if spec["id"]!="python.source.formal_effects"]
    for spec in specs:
        if spec["id"] in retired_ids:
            spec["expected"].setdefault("variants", {})["current"] = {
                "should_accept": True, "codes": [], "located_codes": [], "message_contains": [],
            }
            spec["classification"] = "approved_change"
            spec["notes"] = retired_ids[spec["id"]] + ": default inference retired; historical baseline expectation is retained."
    for spec in specs:
        if spec["id"] in {"python.purity.generator", "python.variant.syntax.yield_from"}:
            spec["expected"].setdefault("variants", {})["current"] = {
                "should_accept": False,
                "codes": [{"code": "NODE.CONTRACT.GENERATOR_RUN_PURE", "severity": "error"}],
            }
            spec["notes"] = "B10: real generator entry ABI remains rejected by the independent interface Rule."
    work_root = Path(work_root).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    return [runner(work_root, variant, spec) for spec in specs]
