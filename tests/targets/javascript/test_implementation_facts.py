from __future__ import annotations

from dataclasses import replace

import pytest

from vibeflow.block_compiler import compile_graph_plan
from vibeflow.core.compiler import compile_core
from vibeflow.core.contracts import DataProvider
from vibeflow.core.descriptors import NodeCatalog, NodeDescriptor
from vibeflow.core.flow import GraphConfig, NodeSpec, EdgeSpec
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
        {
            "kind": "node",
            "type_key": "demo.fetch",
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
        "type_key": "demo.fetch",
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


@pytest.mark.parametrize("managed", (False, True))
@pytest.mark.parametrize("neutral", (False, True))
def test_immediate_javascript_implementation_scheduling_uses_target_facts(
    managed, neutral,
) -> None:
    descriptor = _descriptor()
    descriptor = replace(descriptor, contract=replace(descriptor.contract,
        provides=(DataProvider("value", "value", display_name="Value"),),
        output_semantics={"value": ("The fetched value",)}))
    manager=replace(descriptor,type_key="demo.manager",flow_kind="task_manager",implementations=tuple(replace(item,completion="suspend") for item in descriptor.implementations))
    start=replace(_descriptor(),type_key="demo.start")
    catalog = NodeCatalog((descriptor, manager, start) if managed else (descriptor,))
    facts = (target_neutral_implementation_facts_from_catalog(catalog) if neutral
             else implementation_facts_from_catalog(catalog, target="browser"))
    graph = GraphConfig(
        nodes=(NodeSpec("start","demo.start"),NodeSpec("fetch", "demo.manager", task_targets={"work":NodeSpec("execution","demo.fetch")}),NodeSpec("end","demo.start")) if managed else (NodeSpec("fetch","demo.fetch"),),
        edges=(EdgeSpec("start","fetch"),EdgeSpec("fetch","end")) if managed else (),
        entry_mode="async" if managed else "sync",
    )
    features = TargetFeatureSet(target="browser")
    compilation = compile_core(CoreCompileRequest(graph=graph, implementation_facts=facts, target_features=features))
    plan = compile_graph_plan(compilation.workflow.graph, compilation.compiled_graph,
        implementation_facts=facts, target_features=features,task_executor="event_loop",
        call_execution_facts={("unused",):ImplementationFact("demo.fetch",executor="thread")})
    root = plan.block(plan.entry_block)
    assert root.node("fetch").completion == ("suspend" if managed else "immediate")
    assert (root.node("fetch").schedule, root.node("fetch").executor) == ("inline", "event_loop" if managed else "current")
    assert [task.executor for task in root.tasks] == (["event_loop"] if managed else [])
    bound_workflow_view(plan, build_javascript_binding_plan(plan))

    if managed:
        threaded = replace(plan, blocks=tuple(replace(root,
            nodes=tuple(replace(node,executor="thread") if node.id=="fetch" else node for node in root.nodes),
            tasks=tuple(replace(task, executor="thread") for task in root.tasks)) if block.id==root.id else block for block in plan.blocks))
        with pytest.raises(AotPlanError, match="thread_executor") as error:
            bound_workflow_view(threaded, build_javascript_binding_plan(threaded))
        assert error.value.code == "TARGET.FEATURE.UNSUPPORTED"
