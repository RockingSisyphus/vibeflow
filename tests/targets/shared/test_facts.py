"""Prepared views preserve identity, immutability and mutable-extra isolation."""
from dataclasses import dataclass
from types import SimpleNamespace
import pytest
from vibeflow.targets.shared.facts import FactStore, fact_key


def test_capture_and_derive_freeze_inputs_and_share_owned_snapshots():
    store = FactStore('python')
    raw = {'sources':[{'path':'node.py','text':'x=1'}],'settings':{'limit':1}}
    view = store.capture(raw)
    again = store.capture(raw)
    assert view is again
    changed = view.derive({'settings':{'limit':2}})
    assert changed.identity != view.identity
    assert changed.facts['sources'] is view.facts['sources']
    assert view.context('import').facts is view.context('static').facts
    raw['sources'][0]['text'] = 'x=2'
    assert view.facts['sources'][0]['text'] == 'x=1'
    assert store.capture(raw).identity != view.identity
    with pytest.raises(TypeError):
        changed.facts['settings']['limit'] = 3


def test_unknown_mutable_facts_never_reuse_an_identity():
    store = FactStore('javascript');extra = SimpleNamespace(value=1)
    first = store.capture({'extra':extra})
    extra.value = 2
    assert store.capture({'extra':extra}).identity != first.identity
    assert first.derive({'extra':extra}).identity != first.derive({'extra':extra}).identity


def test_session_reset_does_not_change_issued_identity():
    store = FactStore('python');old = store.capture({'value':1});identity = old.identity
    store.clear();new = store.capture({'value':1})
    assert old.identity == identity and new.identity != identity
    assert FactStore('python').capture({'value':1}).identity != identity


def test_encoder_keeps_actual_types_and_mapping_key_types():
    @dataclass
    class First:
        value: int
    @dataclass
    class Second:
        value: int
    assert fact_key(First(1)) != fact_key(Second(1))
    assert fact_key({1:'value'}) != fact_key({'1':'value'})
