from __future__ import annotations

from dataclasses import replace

import pytest

from vibeflow.block_compiler import compile_graph_plan
from vibeflow.core.compiler import compile_core
from vibeflow.core.contracts import DataProvider
from vibeflow.core.descriptors import NodeCatalog, NodeDescriptor
from vibeflow.core.flow import GraphConfig, NodeCallSpec, EdgeSpec
from vibeflow.core.models import CoreCompileRequest, ImplementationFact, ImplementationFacts, TargetFeatureSet
from vibeflow.targets.javascript.frontend.facts import (
    implementation_facts_from_catalog,
    target_neutral_implementation_facts_from_catalog,
)
from vibeflow.targets.javascript.frontend.bindings import build_javascript_binding_plan
from vibeflow.targets.javascript.frontend.emission_view import bound_workflow_view
from vibeflow.targets.javascript.frontend.errors import AotPlanError
from vibeflow.core.descriptors.decode import decode_resource as parse_descriptor_manifest


def _descriptor(*, completion: str = "immediate") -> NodeDescriptor:
    parsed = parse_descriptor_manifest(
        {'node_type': 'vibeflow.node',
            "kind": "node",
            'id': "demo.fetch",
            "display_name": "Fetch",

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
        "definition_id": "demo.fetch",
        "flow_kind": "terminal",
        "effect_scope": "unconstrained",
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


@pytest.mark.parametrize("suspend", (False, True))
@pytest.mark.parametrize("neutral", (False, True))
def test_javascript_ordinary_call_scheduling_uses_target_facts(suspend, neutral):
    descriptor = _descriptor(completion="suspend" if suspend else "immediate")
    catalog = NodeCatalog((descriptor,))
    facts = (target_neutral_implementation_facts_from_catalog(catalog) if neutral
             else implementation_facts_from_catalog(catalog,target="browser"))
    graph = GraphConfig(nodes=(NodeCallSpec("fetch","demo.fetch"),),entry_mode="async" if suspend else "sync")
    features = TargetFeatureSet(target="browser")
    compilation = compile_core(CoreCompileRequest(graph=graph,implementation_facts=facts,target_features=features))
    plan = compile_graph_plan(compilation.workflow.graph,compilation.compiled_graph,
        implementation_facts=facts,target_features=features)
    root = plan.block(plan.entry_block)
    assert root.node("fetch").completion == ("suspend" if suspend else "immediate")
    assert (root.node("fetch").schedule,root.node("fetch").executor) == ("inline","event_loop" if suspend else "current")
    bound_workflow_view(plan,build_javascript_binding_plan(plan))
    threaded = replace(plan,blocks=(replace(root,nodes=(replace(root.nodes[0],executor="thread"),)),))
    with pytest.raises(AotPlanError,match="thread_executor"):
        bound_workflow_view(threaded,build_javascript_binding_plan(threaded))
