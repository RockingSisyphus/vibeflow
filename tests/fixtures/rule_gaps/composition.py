"""Domain bundle Rules composed with native branch, Nodeset, and Loop flows."""

from __future__ import annotations

from pathlib import Path

from composition_support import observe


def _spec(target, form, variant="normal", branch="left"):
    normal = variant == "normal"
    code = "EXAMPLE.MODEL.ONE_BLOCK" if variant == "missing_model" else "EXAMPLE.MODEL.LOCATION"
    node_type = "example.model" if variant == "missing_model" else "example.transform"
    prefix = [] if form == "branch" else ["stage" if form == "nodeset" else "loop"]
    model_paths = [["left", "model"], ["right", "model"]] if form == "branch" else [[*prefix, "model"]]
    paths = model_paths if variant == "missing_model" else [[*prefix, "transform"]]
    metrics = {"exit_code": 0 if normal else 1, "json_output": True,
               "runtime_exit_code": 0 if normal else 1, "runtime_values_written": normal,
               "selected_model_paths": model_paths}
    if normal:
        metrics.update(numeric_result=10 if form == "branch" and branch == "right" else 7,
                       architecture_tags=["model_block"], architecture_fill="#cceeff",
                       mermaid_light_blue=True, svg_valid=True, svg_light_blue=True,
                       svg_model_count=2 if form == "branch" else 1,
                       svg_model_fills=["#cceeff"] * (2 if form == "branch" else 1),
                       diagram_exit_codes=[0, 0, 0])
        if target == "python":
            metrics["runtime_model_count"] = 1
    else:
        metrics.update(domain_definition_ids=["example.model_definition"], domain_owner_types=[node_type],
                       domain_call_paths=paths, domain_source_files=[
                           "nodes/domain_nodes.py" if variant == "missing_model" and target == "python" else
                           "nodes/model.ts" if variant == "missing_model" else
                           "base_lib/domain_helpers/illegal_model.py" if target == "python" else "nodes/transform_helper.ts"])
    expected = {"should_accept": normal, "codes": [] if normal else [{"code": code, "severity": "error"}],
                "metrics": metrics}
    if not normal:
        expected["located_codes"] = [code]
    suffix = variant + ("_" + branch if form == "branch" and normal else "")
    return {"id": f"composition.{target}.{form}.{suffix}", "title": f"{target}: {form} domain composition ({suffix})",
            "family": "domain-native-composition", "classification": "new_feature", "expected": expected,
            "target": target, "form": form, "variant": variant, "branch": branch, "domain_code": code,
            "notes": "Each conditional branch wraps the same model Node type in a native Nodeset with distinct external output keys; this preserves the native global key invariant." if form == "branch" else ""}


def case_specs():
    return [_spec(target, form, variant, branch)
            for target in ("python", "javascript") for form in ("branch", "nodeset", "loop")
            for variant, branch in (("normal", "left"), ("missing_model", "left"), ("helper_model", "left"))
            + ((("normal", "right"),) if form == "branch" else ())]


def run_cases(work_root: Path, variant: str = "current", toolchain_root: Path | None = None) -> list[dict]:
    if variant != "current":
        raise ValueError("composition gaps only evaluate the current kernel")
    return [observe(work_root, spec, toolchain_root) for spec in case_specs()]
