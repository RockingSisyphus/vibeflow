"""Observe SDK registration and native JSON controls, case by case."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys


REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY / "src"))

from vibeflow.core.config.node import merge_node_config, normalize_node_config_spec
from vibeflow.targets.python import NodeRegistry
from vibeflow.targets.python.sdk import Plugin, node


CASES = (
    ("string", "string", "a"),
    ("integer", "integer", 1),
    ("boolean", "boolean", True),
    ("empty_array", "array", []),
    ("array", "array", ["a"]),
    ("empty_object", "object", {}),
    ("object", "object", {"a": 1}),
    ("number", "number", 1.5),
    ("null", "null", None),
    ("nested_array", "array", [["a"], []]),
    ("array_of_objects", "array", [{"a": 1}]),
    ("object_with_array", "object", {"a": ["x"]}),
    ("object_with_object", "object", {"a": {"b": 1}}),
    ("mixed_nested", "array", [{"a": [1, {"b": []}]}]),
)


def type_tree(value):
    tree = {"type": type(value).__name__}
    if isinstance(value, (list, tuple)):
        tree["items"] = [type_tree(item) for item in value]
    elif hasattr(value, "items"):
        tree["fields"] = {key: type_tree(item) for key, item in value.items()}
    return tree


def error_record(error):
    return {"status": "FAIL", "error_type": type(error).__name__, "error": str(error)}


def raw_control(schema_type, value):
    """Use original JSON values to isolate configuration normalization."""
    spec = normalize_node_config_spec({"value": {"type": schema_type}}, {"value": deepcopy(value)})
    first = merge_node_config(spec, None)
    second = merge_node_config(spec, None)
    explicit = merge_node_config(spec, {"value": deepcopy(value)})
    result = {"status": "PASS", "default_types": type_tree(first["value"]),
              "override_types": type_tree(explicit["value"])}
    if isinstance(value, (list, dict)):
        before = deepcopy(second["value"])
        if isinstance(value, list):
            first["value"].append("first-invocation-mutation")
        else:
            first["value"]["first-invocation-mutation"] = True
        result["default_isolation"] = {
            "status": "PASS" if second["value"] == before else "FAIL",
            "same_container": first["value"] is second["value"],
            "second_before": before, "second_after": deepcopy(second["value"]),
            "scope": "two Core merge_node_config calls; not two completed workflow runs",
        }
    return result


def observe(case_id, schema_type, value):
    schema = {"value": {"type": schema_type}}

    @node(type_key=f"probe.{case_id}", contract={
        "params_schema": schema, "params_defaults": {"value": value},
    }, rulesets=["vibeflow.process"])
    class Probe:
        def run_pure(self, inputs, params):
            return {}

    contribution = Plugin(id=f"probe.{case_id}", resources=[Probe]).contributions()
    descriptor = contribution.resources[0].descriptor
    snapshot = descriptor.to_dict()["contract"]["params_defaults"]["value"]
    result = {
        "id": case_id, "schema_type": schema_type, "original": value,
        "expected_registration": "PASS", "sdk_types": type_tree(descriptor.contract.params_defaults["value"]),
        "descriptor_json_roundtrip": json.loads(json.dumps(snapshot)) == value,
    }
    registry = NodeRegistry()
    try:
        registry.register(descriptor, Probe)
    except Exception as error:
        result.update(error_record(error))
        result["registered_config"] = {"status": "BLOCKED_BY_REGISTRATION"}
    else:
        result["status"] = "PASS"
        result["registered_config"] = {
            "status": "PASS", "default_types": type_tree(registry.merge_config(descriptor.type_key, None)["value"]),
            "override_types": type_tree(registry.merge_config(descriptor.type_key, {"value": deepcopy(value)})["value"]),
        }
    result["native_json_control"] = raw_control(schema_type, value)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY,
                              capture_output=True, text=True, check=True).stdout.strip()
    cases = [observe(*case) for case in CASES]
    report = {
        "schema": "vibeflow.sdk-defaults-observation.v1", "revision": revision,
        "python": sys.version, "implementation": str(REPOSITORY / "src"),
        "exit_code_meaning": "0 means observations completed; inspect every case status",
        "summary": {"cases": len(cases), "registered": sum(case["status"] == "PASS" for case in cases),
                    "registration_failures": sum(case["status"] == "FAIL" for case in cases)},
        "cases": cases,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
