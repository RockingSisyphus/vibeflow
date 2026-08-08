from __future__ import annotations

from vibeflow.core.descriptors import NodeCatalog, NodeDescriptor
from vibeflow.targets.javascript.frontend.facts import (
    implementation_facts_from_catalog,
)
from vibeflow.tooling.project.descriptor_loader import parse_descriptor_manifest


def _descriptor(*, completion: str = "immediate") -> NodeDescriptor:
    parsed = parse_descriptor_manifest(
        {
            "kind": "node",
            "type_key": "demo.fetch",
            "display_name": "Fetch",
            "category": "demo",
            "description": "Fetch one value.",
            "version": "1.0.0",
            "flow_kind": "terminal",
            "contract": {
                "requires": [],
                "provides": [],
            },
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser"],
                    "completion": completion,
                    "source": {
                        "kind": "file",
                        "ref": "src/fetch.ts",
                        "export": "run",
                    },
                }
            ],
        },
        expected_kind="node",
    )
    assert isinstance(parsed, NodeDescriptor)
    return parsed


def test_javascript_descriptors_supply_core_execution_facts() -> None:
    facts = implementation_facts_from_catalog(
        NodeCatalog((_descriptor(completion="suspend"),)),
        target="browser",
    )

    assert facts.strict is True
    assert facts.get("demo.fetch").to_dict() == {
        "type_key": "demo.fetch",
        "flow_kind": "terminal",
        "effect_scope": "none",
        "runtime_dispatch": None,
        "completion": "suspend",
        "schedule": "inline",
        "executor": "event_loop",
        "source_kind": "file",
            "source_ref": "src/fetch.ts",
            "source_export": "run",
            "requires": [],
            "provides": [],
        }


def test_target_mismatch_keeps_contract_fact_for_precise_frontend_error() -> None:
    facts = implementation_facts_from_catalog(
        NodeCatalog((_descriptor(),)),
        target="node",
    )

    fact = facts.get("demo.fetch")
    assert fact is not None
    assert fact.flow_kind == "terminal"
    assert fact.source_ref == ""
