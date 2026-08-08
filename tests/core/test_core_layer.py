"""Characterization tests for the language-neutral Core boundary."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from vibeflow.targets.python.project.compiler import GraphCompiler as PythonGraphCompiler
from vibeflow.core.compiler import GraphCompileError, GraphCompiler, compile_core
from vibeflow.core.config.graph import parse_graph_config_data
from vibeflow.core.contracts import DataProvider
from vibeflow.core.constants import (
    EFFECT_SCOPE_GLOBAL_STATE,
    FLOW_KIND_GLOBAL_STATE,
    FLOW_KIND_PROCESS,
    TARGET_FEATURE_EXECUTION_LOCKS,
    TARGET_FEATURE_GLOBAL_STATE,
)
from vibeflow.core.flow import (
    EdgeSpec,
    ExecutionLockSpec,
    GraphConfig,
    GraphConfigError,
    NodeSpec,
    NodesetSpec,
)
from vibeflow.core.inspection import build_architecture_report
from vibeflow.core.models import (
    CoreCompileRequest,
    ImplementationFact,
    ImplementationFacts,
    TargetFeatureSet,
)


def _graph() -> GraphConfig:
    return GraphConfig(
        nodes=(
            NodeSpec(id="first", type_used="fixture.first"),
            NodeSpec(id="second", type_used="fixture.second"),
        ),
        edges=(EdgeSpec("first", "second"),),
    )


def _facts() -> ImplementationFacts:
    return ImplementationFacts(
        (
            ImplementationFact("fixture.second", flow_kind=FLOW_KIND_PROCESS),
            ImplementationFact("fixture.first", flow_kind=FLOW_KIND_PROCESS),
        ),
        strict=True,
    )


def _nested_global_state_graph() -> GraphConfig:
    return parse_graph_config_data(
        {
            "nodesets": [
                {
                    "type_key": "fixture.inner",
                    "display_name": "Inner",
                    "description": "Contains the global-state implementation.",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            {"id": "state", "type_used": "fixture.state", "display_name": "State", "description": "Owns the nested global state."},
                        ]
                    },
                },
                {
                    "type_key": "fixture.outer",
                    "display_name": "Outer",
                    "description": "Calls the inner nodeset.",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            {"id": "inner", "type_used": "fixture.inner", "display_name": "Inner", "description": "Calls the inner nodeset."},
                        ]
                    },
                },
            ],
            "pipeline": {
                "nodes": [
                    {"id": "outer", "type_used": "fixture.outer", "display_name": "Outer", "description": "Calls the outer nodeset."},
                ]
            },
        }
    )


def test_compile_core_accepts_only_static_facts_and_is_deterministic() -> None:
    request = CoreCompileRequest(
        graph=_graph(),
        implementation_facts=_facts(),
        target_features=TargetFeatureSet(
            target="fixture",
            features=frozenset({"graph", "condition"}),
        ),
    )

    first = compile_core(request)
    second = compile_core(request)

    assert first == second
    assert first.workflow.graph == request.graph
    assert first.workflow.graph is not request.graph
    assert first.graph.order == ("first", "second")
    assert first.graph.flow_kinds == {
        "first": FLOW_KIND_PROCESS,
        "second": FLOW_KIND_PROCESS,
    }
    assert first.workflow.implementation_facts.to_dict() == {
        "strict": True,
        "nodes": [item.to_dict() for item in _facts().nodes],
    }


def test_pure_graph_compiler_rejects_missing_strict_implementation_fact() -> None:
    with pytest.raises(GraphCompileError, match="unknown type_used 'fixture.second'"):
        GraphCompiler().compile(
            _graph(),
            implementation_facts=ImplementationFacts(
                (ImplementationFact("fixture.first", flow_kind="process"),),
                strict=True,
            ),
        )


def test_python_registry_adapter_matches_pure_compiler_output() -> None:
    class Registered:
        flow_kind = FLOW_KIND_PROCESS

    class Registry:
        def require(self, type_key: str) -> type[Registered]:
            if type_key not in {"fixture.first", "fixture.second"}:
                raise KeyError(type_key)
            return Registered

    adapted = PythonGraphCompiler().compile(_graph(), registry=Registry())
    pure = GraphCompiler().compile(_graph(), implementation_facts=_facts())

    assert adapted == pure


def test_importing_core_does_not_load_target_or_tooling_layers() -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = """
import json
import sys
sys.path.insert(0, 'src')
import vibeflow.core
forbidden = ('vibeflow.runtime', 'vibeflow.aot', 'vibeflow.workspace', 'vibeflow.rendering')
print(json.dumps(sorted(name for name in sys.modules if name.startswith(forbidden))))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == []


def test_global_state_requires_target_feature_and_derives_effect_scope() -> None:
    graph = GraphConfig(nodes=(NodeSpec("state", "fixture.state"),))
    facts = ImplementationFacts(
        (ImplementationFact("fixture.state", flow_kind=FLOW_KIND_GLOBAL_STATE),),
        strict=True,
    )

    with pytest.raises(GraphCompileError) as exc_info:
        compile_core(
            CoreCompileRequest(
                graph=graph,
                implementation_facts=facts,
                target_features=TargetFeatureSet(target="javascript"),
            )
        )

    assert exc_info.value.rule_id == "TARGET.FEATURE.UNSUPPORTED"
    assert exc_info.value.details == {
        "target": "javascript",
        "feature": TARGET_FEATURE_GLOBAL_STATE,
        "nodes": ["state"],
    }

    compilation = compile_core(
        CoreCompileRequest(
            graph=graph,
            implementation_facts=facts,
            target_features=TargetFeatureSet(
                target="python",
                features=frozenset({TARGET_FEATURE_GLOBAL_STATE}),
            ),
        )
    )
    compiled = compilation.graph
    assert compiled.effect_scopes == {"state": EFFECT_SCOPE_GLOBAL_STATE}
    assert compiled.runtime_dispatches == {"state": None}
    assert compiled.contains_global_state is True
    assert [item.rule_id for item in compilation.findings] == [
        "GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED"
    ]
    report = build_architecture_report(graph, compiled=compiled)
    assert report["contains_global_state"] is True
    assert "root_exclusive" not in report
    assert report["execution_lock"] is None
    report_node = report["nodes"][0]
    assert report_node["flow_kind"] == FLOW_KIND_GLOBAL_STATE
    assert report_node["effect_scope"] == EFFECT_SCOPE_GLOBAL_STATE
    assert report_node["execution_lock"] is None
    assert report_node["contains_global_state"] is True


def test_nested_nodeset_global_state_propagates_to_root_and_feature_gate() -> None:
    graph = _nested_global_state_graph()
    facts = ImplementationFacts(
        (ImplementationFact("fixture.state", flow_kind=FLOW_KIND_GLOBAL_STATE),),
        strict=True,
    )

    with pytest.raises(GraphCompileError) as exc_info:
        compile_core(
            CoreCompileRequest(
                graph=graph,
                implementation_facts=facts,
                target_features=TargetFeatureSet(target="javascript"),
            )
        )

    assert exc_info.value.rule_id == "TARGET.FEATURE.UNSUPPORTED"
    assert exc_info.value.details == {
        "target": "javascript",
        "feature": TARGET_FEATURE_GLOBAL_STATE,
        "nodes": ["outer.inner.state"],
    }

    compilation = compile_core(
        CoreCompileRequest(
            graph=graph,
            implementation_facts=facts,
            target_features=TargetFeatureSet(
                target="python",
                features=frozenset({TARGET_FEATURE_GLOBAL_STATE}),
            ),
        )
    )
    compiled = compilation.graph
    assert compiled.contains_global_state is True
    warning = next(
        item
        for item in compilation.findings
        if item.rule_id
        == "GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED"
    )
    assert warning.source == "outer.inner.state"

    architecture = build_architecture_report(graph, compiled=compiled)
    assert architecture["contains_global_state"] is True
    assert architecture["summary"]["contains_global_state"] is True


def test_effective_execution_lock_suppresses_uncoordinated_global_warning() -> None:
    facts = ImplementationFacts(
        (ImplementationFact("fixture.state", flow_kind=FLOW_KIND_GLOBAL_STATE),),
        strict=True,
    )
    features = TargetFeatureSet(
        target="python",
        features=frozenset(
            {TARGET_FEATURE_GLOBAL_STATE, TARGET_FEATURE_EXECUTION_LOCKS}
        ),
    )
    child_unlocked = GraphConfig(nodes=(NodeSpec("state", "fixture.state"),))
    child_locked = GraphConfig(
        nodes=(NodeSpec("state", "fixture.state"),),
        execution_lock=ExecutionLockSpec("project.block"),
    )
    graphs = (
        GraphConfig(
            nodes=(NodeSpec("state", "fixture.state"),),
            execution_lock=ExecutionLockSpec("project.root"),
        ),
        GraphConfig(
            nodes=(
                NodeSpec(
                    "state",
                    "fixture.state",
                    execution_lock=ExecutionLockSpec("project.node"),
                ),
            ),
        ),
        GraphConfig(
            nodes=(NodeSpec("group", "fixture.group"),),
            nodesets={
                "fixture.group": NodesetSpec(
                    "fixture.group",
                    "Group",
                    "The child block owns the lock.",
                    (),
                    (),
                    child_locked,
                )
            },
        ),
        GraphConfig(
            nodes=(
                NodeSpec(
                    "group",
                    "fixture.group",
                    execution_lock=ExecutionLockSpec("project.ancestor"),
                ),
            ),
            nodesets={
                "fixture.group": NodesetSpec(
                    "fixture.group",
                    "Group",
                    "The invocation owns the lock.",
                    (),
                    (),
                    child_unlocked,
                )
            },
        ),
    )

    for graph in graphs:
        compilation = compile_core(
            CoreCompileRequest(
                graph=graph,
                implementation_facts=facts,
                target_features=features,
                known_nodesets=frozenset(graph.nodesets),
            )
        )
        assert not any(
            finding.rule_id
            == "GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED"
            for finding in compilation.findings
        )


def test_planned_nodeset_trees_do_not_create_execution_or_lock_facts() -> None:
    graph = parse_graph_config_data(
        {
            "nodesets": [
                {
                    "type_key": "fixture.planned_definition",
                    "display_name": "Planned Definition",
                    "description": "The entire definition is architecture-only.",
                    "status": "planned",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            {
                                "id": "state",
                                "type_used": "fixture.state",
                                "display_name": "State",
                                "description": "Would own state in the planned definition.",
                                "execution_lock": {"key": "ignored-child-lock"},
                            },
                        ]
                    },
                },
                {
                    "type_key": "fixture.implemented_definition",
                    "display_name": "Implemented Definition",
                    "description": "Used only by a planned call site.",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            {"id": "state", "type_used": "fixture.state", "display_name": "State", "description": "Owns state in the implemented definition."},
                        ]
                    },
                },
                {
                    "type_key": "fixture.planned_child",
                    "display_name": "Planned Child",
                    "description": "Contains only a planned global-state child.",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            {
                                "id": "future_state",
                                "type_used": "planned.state",
                                "status": "planned",
                                "flow_kind": FLOW_KIND_GLOBAL_STATE,
                                "display_name": "Future State",
                                "description": "Represents planned global state.",
                                "requires": [],
                                "provides": [],
                            },
                        ]
                    },
                },
            ],
            "pipeline": {
                "nodes": [
                    {
                        "id": "planned_definition_call",
                        "type_used": "fixture.planned_definition",
                        "display_name": "Planned Definition",
                        "description": "Calls the planned nodeset definition.",
                        "async": "detached",
                        "execution_lock": {"key": "ignored-planned-lock"},
                    },
                    {
                        "id": "planned_call",
                        "type_used": "fixture.implemented_definition",
                        "status": "planned",
                        "flow_kind": "predefined",
                        "display_name": "Planned Call",
                        "description": "Represents a planned call to an implemented nodeset.",
                        "requires": [],
                        "provides": [],
                        "execution_lock": {"key": "ignored-call-lock"},
                    },
                    {
                        "id": "planned_child_call",
                        "type_used": "fixture.planned_child",
                        "display_name": "Planned Child Call",
                        "description": "Calls the nodeset containing a planned child.",
                    },
                ]
            },
        }
    )
    facts = ImplementationFacts(
        (ImplementationFact("fixture.state", flow_kind=FLOW_KIND_GLOBAL_STATE),),
        strict=True,
    )

    compiled = compile_core(
        CoreCompileRequest(
            graph=graph,
            implementation_facts=facts,
            target_features=TargetFeatureSet(target="javascript"),
        )
    ).graph

    assert compiled.contains_global_state is False
    assert compiled.providers == {}
    assert compiled.consumers == {}


def test_recursive_nodeset_cycle_is_guarded_while_finding_global_state() -> None:
    graph = parse_graph_config_data(
        {
            "nodesets": [
                {
                    "type_key": "fixture.cycle_a",
                    "display_name": "Cycle A",
                    "description": "Calls cycle B.",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            {"id": "to_b", "type_used": "fixture.cycle_b", "display_name": "To B", "description": "Calls cycle B."},
                        ]
                    },
                },
                {
                    "type_key": "fixture.cycle_b",
                    "display_name": "Cycle B",
                    "description": "Calls cycle A and contains global state.",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            {"id": "back", "type_used": "fixture.cycle_a", "display_name": "Back", "description": "Calls cycle A."},
                            {"id": "state", "type_used": "fixture.state", "display_name": "State", "description": "Owns nested global state."},
                        ]
                    },
                },
            ],
            "pipeline": {
                "nodes": [
                    {"id": "cycle", "type_used": "fixture.cycle_a", "display_name": "Cycle", "description": "Calls the recursive nodeset fixture."},
                ]
            },
        }
    )
    facts = ImplementationFacts(
        (ImplementationFact("fixture.state", flow_kind=FLOW_KIND_GLOBAL_STATE),),
        strict=True,
    )

    with pytest.raises(GraphCompileError) as exc_info:
        compile_core(
            CoreCompileRequest(
                graph=graph,
                implementation_facts=facts,
                target_features=TargetFeatureSet(target="javascript"),
            )
        )

    assert exc_info.value.rule_id == "TARGET.FEATURE.UNSUPPORTED"
    assert exc_info.value.details["nodes"] == ["cycle.to_b.state"]


def test_nested_execution_lock_requires_target_feature() -> None:
    graph = parse_graph_config_data(
        {
            "nodesets": [
                {
                    "type_key": "fixture.locked",
                    "display_name": "Locked",
                    "description": "Contains a locked child node.",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            {
                                "id": "locked",
                                "type_used": "fixture.work",
                                "display_name": "Locked Work",
                                "description": "Runs work under the child lock.",
                                "execution_lock": {"key": "child-lock"},
                            },
                        ]
                    },
                },
            ],
            "pipeline": {
                "nodes": [
                    {"id": "outer", "type_used": "fixture.locked", "display_name": "Outer", "description": "Calls the locked nodeset."},
                ]
            },
        }
    )

    with pytest.raises(GraphCompileError) as exc_info:
        compile_core(
            CoreCompileRequest(
                graph=graph,
                implementation_facts=ImplementationFacts(
                    (ImplementationFact("fixture.work", flow_kind="process"),),
                    strict=True,
                ),
                target_features=TargetFeatureSet(target="javascript"),
            )
        )

    assert exc_info.value.rule_id == "TARGET.FEATURE.UNSUPPORTED"
    assert exc_info.value.details == {
        "target": "javascript",
        "feature": TARGET_FEATURE_EXECUTION_LOCKS,
        "root": False,
        "nodes": ["outer.locked"],
    }


def test_nested_execution_locks_must_reuse_the_active_core_key() -> None:
    def locked_graph(child_key: str) -> GraphConfig:
        return parse_graph_config_data(
            {
                "nodesets": [
                    {
                        "type_key": "fixture.locked",
                        "display_name": "Locked",
                        "description": "Contains a locked child node.",
                        "requires": [],
                        "provides": [],
                        "pipeline": {
                            "nodes": [
                                {
                                    "id": "locked",
                                    "type_used": "fixture.work",
                                    "display_name": "Locked Work",
                                    "description": "Runs work under the nested lock.",
                                    "execution_lock": {"key": child_key},
                                },
                            ]
                        },
                    },
                ],
                "pipeline": {
                    "execution_lock": {"key": "root-lock"},
                    "nodes": [
                        {"id": "outer", "type_used": "fixture.locked", "display_name": "Outer", "description": "Calls the locked nodeset."},
                    ],
                },
            }
        )

    facts = ImplementationFacts(
        (ImplementationFact("fixture.work", flow_kind="process"),),
        strict=True,
    )
    features = TargetFeatureSet(
        target="fixture",
        features=frozenset({TARGET_FEATURE_EXECUTION_LOCKS}),
    )

    with pytest.raises(GraphCompileError) as exc_info:
        compile_core(
            CoreCompileRequest(
                graph=locked_graph("child-lock"),
                implementation_facts=facts,
                target_features=features,
            )
        )

    assert exc_info.value.rule_id == "GRAPH.EXECUTION_LOCK.NESTED_KEY_CONFLICT"
    assert exc_info.value.details == {
        "subject": "node 'outer.locked'",
        "parent_key": "root-lock",
        "child_key": "child-lock",
    }

    compilation = compile_core(
        CoreCompileRequest(
            graph=locked_graph("root-lock"),
            implementation_facts=facts,
            target_features=features,
        )
    )
    assert compilation.graph.contains_global_state is False
    assert not compilation.findings


@pytest.mark.parametrize(
    ("async_fields", "expected_rule"),
    (
        (
            {"async": "detached"},
            "GRAPH.EXECUTION_LOCK.DETACHED_FORBIDDEN",
        ),
        (
                {
                    "async": "result_key",
                    "result_key": "work.out",
                },
            "GRAPH.EXECUTION_LOCK.RESULT_UNJOINABLE",
        ),
    ),
)
def test_explicit_nodeset_lock_protects_child_async_scope(
    async_fields: dict[str, object],
    expected_rule: str,
) -> None:
    work_node = {
        "id": "work",
        "type_used": "fixture.work",
        "display_name": "Work",
        "description": "Runs asynchronous work inside the protected nodeset.",
        **async_fields,
    }
    graph = parse_graph_config_data(
        {
            "nodesets": [
                {
                    "type_key": "fixture.protected",
                    "display_name": "Protected",
                    "description": "Contains global state and asynchronous work.",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            {"id": "state", "type_used": "fixture.state", "display_name": "State", "description": "Owns protected global state."},
                            work_node,
                        ]
                    },
                },
            ],
            "pipeline": {
                "nodes": [
                    {
                        "id": "outer",
                        "type_used": "fixture.protected",
                        "display_name": "Outer",
                        "description": "Calls the protected nodeset.",
                        "execution_lock": {"key": "protected"},
                    },
                ]
            },
        }
    )
    facts = ImplementationFacts(
        (
            ImplementationFact(
                "fixture.state",
                flow_kind=FLOW_KIND_GLOBAL_STATE,
            ),
            ImplementationFact(
                "fixture.work",
                flow_kind="process",
                provides=(DataProvider("work.out", "work.out", display_name="Work Output"),),
            ),
        ),
        strict=True,
    )

    with pytest.raises(GraphCompileError) as exc_info:
        compile_core(
            CoreCompileRequest(
                graph=graph,
                implementation_facts=facts,
                target_features=TargetFeatureSet(
                    target="python",
                    features=frozenset(
                        {
                            TARGET_FEATURE_GLOBAL_STATE,
                            TARGET_FEATURE_EXECUTION_LOCKS,
                        }
                    ),
                ),
            )
        )

    assert exc_info.value.rule_id == expected_rule
    assert exc_info.value.details["owner"] == "pipeline.outer"
    assert exc_info.value.details["node"] == "work"


def test_planned_global_state_is_visible_but_does_not_require_feature_or_lock() -> None:
    graph = GraphConfig(
        nodes=(
            NodeSpec(
                "future",
                "planned.future",
                status="planned",
                flow_kind=FLOW_KIND_GLOBAL_STATE,
            ),
        )
    )

    compiled = compile_core(
        CoreCompileRequest(
            graph=graph,
            target_features=TargetFeatureSet(target="javascript"),
        )
    ).graph

    assert compiled.effect_scopes == {"future": EFFECT_SCOPE_GLOBAL_STATE}
    assert compiled.contains_global_state is False


def test_uncompiled_architecture_marks_declared_implemented_global_state() -> None:
    graph = GraphConfig(
        nodes=(
            NodeSpec(
                "state",
                "fixture.state",
                flow_kind=FLOW_KIND_GLOBAL_STATE,
            ),
        )
    )

    architecture = build_architecture_report(graph)

    assert architecture["contains_global_state"] is True
    assert architecture["nodes"][0]["contains_global_state"] is True


def test_uncompiled_architecture_recurses_into_implemented_nodesets() -> None:
    child_graph = GraphConfig(
        nodes=(
            NodeSpec(
                "state",
                "fixture.state",
                flow_kind=FLOW_KIND_GLOBAL_STATE,
            ),
        )
    )
    nodeset = NodesetSpec(
        type_key="fixture.inner",
        display_name="Inner",
        description="Contains declared global state.",
        requires=(),
        provides=(),
        graph=child_graph,
    )
    graph = GraphConfig(
        nodes=(NodeSpec("outer", "fixture.inner"),),
        nodesets={"fixture.inner": nodeset},
    )

    architecture = build_architecture_report(graph)

    assert architecture["contains_global_state"] is True
    assert architecture["summary"]["contains_global_state"] is True
    assert architecture["nodes"][0]["contains_global_state"] is True


def test_execution_lock_config_is_normalized_reserved_and_feature_gated() -> None:
    graph = parse_graph_config_data(
        {
            "pipeline": {
                "execution_lock": {"key": "  trainer  "},
                "nodes": [
                    {
                        "id": "step",
                        "type_used": "fixture.first",
                        "display_name": "Step",
                        "description": "Runs under the normalized execution lock.",
                        "execution_lock": {"key": " trainer "},
                    }
                ],
            }
        }
    )
    assert graph.execution_lock == ExecutionLockSpec("trainer")
    assert graph.nodes[0].execution_lock == ExecutionLockSpec("trainer")
    architecture = build_architecture_report(graph)
    assert architecture["execution_lock"] == {
        "key": "trainer",
        "scope": "root",
    }
    assert architecture["nodes"][0]["execution_lock"] == {
        "key": "trainer",
        "scope": "node",
    }
    with pytest.raises(ValueError, match="reserved prefix"):
        ExecutionLockSpec("vibeflow.internal")

    with pytest.raises(GraphCompileError) as exc_info:
        compile_core(
            CoreCompileRequest(
                graph=graph,
                implementation_facts=ImplementationFacts(
                    (ImplementationFact("fixture.first", flow_kind="process"),),
                    strict=True,
                ),
                target_features=TargetFeatureSet(target="javascript"),
            )
        )
    assert exc_info.value.rule_id == "TARGET.FEATURE.UNSUPPORTED"
    assert exc_info.value.details["feature"] == TARGET_FEATURE_EXECUTION_LOCKS

    with pytest.raises(GraphConfigError, match="reserved prefix"):
        parse_graph_config_data(
            {
                "pipeline": {
                    "execution_lock": {"key": "vibeflow.internal"},
                    "nodes": [{"id": "step", "type_used": "fixture.first", "display_name": "Step", "description": "Exercises a reserved execution lock."}],
                }
            }
        )
