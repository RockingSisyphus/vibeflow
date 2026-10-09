"""Shared analysis facts retain graph identity and recursive read-only copies."""

from dataclasses import dataclass
from types import MappingProxyType

import pytest

from tests.fixtures.python.readonly_graph.probe import distinct_objects, observe, observe_mixed
from vibeflow.core.rules import RuleContext
from vibeflow.core.rules.models import readonly


@pytest.mark.parametrize("kind", ["tuple", "list", "mapping", "dataclass", "namespace"])
@pytest.mark.parametrize("depth", [4, 12])
def test_sandbox_shared_graph_preserves_identity_and_distinct_object_count(kind, depth):
    result = observe(kind, depth, RuleContext)
    assert result["matched"], result
    output_kind = {"list": "tuple", "dataclass": "Pair", "namespace": "SimpleNamespace"}.get(kind, kind)
    assert result["output_objects"] == {output_kind: depth}


def test_deep_tuple_graph_visits_each_input_once_without_path_expansion():
    visits = {}
    depth = 64

    class CountedTuple(tuple):
        def __iter__(self):
            visits[id(self)] = visits.get(id(self), 0) + 1
            # Stop a broken implementation before it allocates an exponential
            # tree. This measures traversal, independently of machine speed.
            assert sum(visits.values()) <= depth * 2
            return super().__iter__()

    shared = 1
    for _ in range(depth):
        shared = CountedTuple((shared, shared))
    frozen = RuleContext(facts={"graph": shared}).facts["graph"]
    assert len(visits) == depth
    assert set(visits.values()) == {1}
    assert distinct_objects(frozen) == {"tuple": depth}


def test_sandbox_mixed_container_aliases_readonly_and_original_mutation_isolation():
    result = observe_mixed(RuleContext)
    assert result["matched"], result


def test_tuple_children_are_frozen_without_reusing_original_mutable_values():
    original = {"values": [1]}
    shared = (original, original)
    frozen = readonly((shared, shared))
    assert frozen[0] is frozen[1]
    assert frozen[0][0] is frozen[0][1]
    assert isinstance(frozen[0][0], MappingProxyType)
    with pytest.raises(TypeError):
        frozen[0][0]["values"] = ()
    with pytest.raises(TypeError):
        frozen[0][0]["values"][0] = 2
    original["values"].append(2)
    assert frozen[0][0]["values"] == (1,)


def test_one_context_shares_a_snapshot_across_fields_and_other_contexts_are_independent():
    original = ({"values": [1]},)
    source = {"shared": original}
    first = RuleContext(facts=source, subject=source, scope=source)
    second = RuleContext(facts=source)
    assert first.facts is first.subject is first.scope
    assert first.facts["shared"] is not second.facts["shared"]
    assert first.facts["shared"][0] is not original[0]
    original[0]["values"].append(2)
    assert first.facts["shared"][0]["values"] == (1,)
    assert second.facts["shared"][0]["values"] == (1,)


@pytest.mark.parametrize("container", [tuple, list])
def test_sequence_back_reference_through_mapping_preserves_frozen_cycle(container):
    contents = {}
    original = container([contents])
    contents["back"] = original
    frozen = readonly(original)
    assert frozen[0]["back"] is frozen
    assert isinstance(frozen[0], MappingProxyType)
    with pytest.raises(TypeError):
        frozen[0]["back"] = ()


def test_sequence_back_reference_through_dataclass_keeps_one_completed_snapshot():
    @dataclass(frozen=True)
    class Fact:
        back: object = None

    fact = Fact()
    original = (fact,)
    object.__setattr__(fact, "back", original)
    frozen = readonly(original)
    assert frozen[0].back is frozen
    assert frozen[0] is not fact

