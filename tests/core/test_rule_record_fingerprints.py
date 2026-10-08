"""Shared outputs remain bounded while cache keys retain input semantics."""

from dataclasses import dataclass
from collections.abc import Mapping

import pytest

from vibeflow.core.rules import RuleRecord
from vibeflow.core.rules.fingerprint import _ContentDigest, cacheable_record_value, record_inputs_fingerprint, value_fingerprint


def dag(depth):
    value = 1
    for _ in range(depth):
        value = (value, value)
    return value


def distinct(value):
    seen, pending = set(), [value]
    while pending:
        item = pending.pop()
        if isinstance(item, (tuple, Mapping)) and id(item) not in seen:
            seen.add(id(item))
            pending.extend(item.values() if isinstance(item, Mapping) else item)
    return len(seen)


def test_deep_record_snapshot_and_fingerprint_visit_shared_objects_once():
    record = RuleRecord("graph", dag(128))
    assert distinct(record.value) == 128
    assert record.value[0] is record.value[1]
    eligibility = {}
    assert cacheable_record_value(record.value, eligibility)
    assert len(eligibility) == 128
    digest = _ContentDigest()
    digest.visit(record.value)
    assert len(digest.memo) == 128


def test_mixed_sharing_is_read_only_and_detached_from_inputs():
    shared = {"items": [{"value": 1}]}
    record = RuleRecord("graph", (shared, shared))
    assert record.value[0] is record.value[1]
    assert distinct(record.value) == 4
    with pytest.raises(TypeError):
        record.value[0]["items"][0]["value"] = 2
    shared["items"][0]["value"] = 9
    assert record.value[0]["items"][0]["value"] == 1


def test_native_frozen_record_sharing_and_type_are_preserved():
    @dataclass(frozen=True)
    class Evidence:
        value: object
    shared = Evidence({"value": [1]})
    record = RuleRecord("graph", (shared, shared))
    assert type(record.value[0]) is Evidence
    assert record.value[0] is record.value[1]
    assert record_inputs_fingerprint({"data": record}) is None


def test_cycles_through_mutable_children_still_fail():
    child = []
    parent = (child,)
    child.append(parent)
    with pytest.raises(ValueError, match="cyclic"):
        RuleRecord("graph", parent)


def test_equal_shared_and_unfolded_contents_have_the_same_fingerprint():
    def tree(depth):
        return 1 if not depth else (tree(depth - 1), tree(depth - 1))
    assert value_fingerprint(dag(8)) == value_fingerprint(tree(8))
    assert value_fingerprint({"b": 2, "a": 1}) == value_fingerprint({"a": 1, "b": 2})


@pytest.mark.parametrize("left,right", [(1, 1.0), (1, True), (-0.0, 0.0), ((1, 1), (1, 2))])
def test_numeric_and_leaf_differences_remain_distinct(left, right):
    assert value_fingerprint(left) != value_fingerprint(right)


def test_record_port_and_type_ids_are_part_of_the_key():
    value = RuleRecord("one", {"value": 7})
    first = record_inputs_fingerprint({"data": value})
    assert first != record_inputs_fingerprint({"other": value})
    assert first != record_inputs_fingerprint({"data": RuleRecord("two", value.value)})


def test_temporary_dataclass_projections_do_not_alias_by_recycled_ids():
    @dataclass(frozen=True)
    class Evidence:
        value: int
    objects = [Evidence(index) for index in range(20)]
    assert value_fingerprint(objects) == value_fingerprint([{"value": index} for index in range(20)])
    assert value_fingerprint(objects) != value_fingerprint(list(reversed(objects)))


def test_final_record_json_boundary_still_uses_ordinary_arrays():
    assert RuleRecord("graph", dag(2)).to_dict() == {"type_id": "graph", "value": [[1, 1], [1, 1]]}
