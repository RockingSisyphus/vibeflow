"""Real Rule plans consume import parameters without lifting effect categories."""

import pytest

from vibeflow.core.rules import RuleCall, RuleRelation, RuleDescriptor, RulesetDescriptor, compile_ruleset, execute_rule_plan
from vibeflow.targets.python.project.policy import EffectivePolicy, default_effective_policy
from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan, source_rule_defaults
from vibeflow.targets.shared.bindings import native_binding
from vibeflow.tooling.application.python.project.effective_policy import resolve_effective_policy
from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins
from tests.targets.python.test_source_effect_parameters import _resource_context


def _plan(rule_id, *, policy=None, configured=None, defaults=None, override=None, effect_scope=None):
    catalog = load_builtin_plugins("python").catalogs
    rules = {item.id:item for item in catalog.rules}
    handlers = {item.id:native_binding(catalog, "rule", item.id) for item in catalog.rules}
    from dataclasses import replace
    if defaults is not None:
        rules[rule_id] = replace(rules[rule_id], params_defaults={**rules[rule_id].params_defaults,"policy":defaults})
    if configured is not None:
        rules = source_rule_defaults(rules, configured, handlers=handlers)
    params = {} if policy is None else {"policy":policy}
    if effect_scope is not None:
        params["effect_scope"] = effect_scope
    calls = [RuleCall("check", rule_id=rule_id, params=params)]
    relations = ()
    if override is not None:
        rules["test.marker"] = RuleDescriptor("test.marker")
        calls.append(RuleCall("marker", rule_id="test.marker"))
        from vibeflow.core.rules import RuleResult
        handlers["test.marker"] = lambda *_:RuleResult()
        relations = (RuleRelation("marker","check","overrides",params={"policy":override}),)
    ruleset = RulesetDescriptor("test.import.policy", calls=tuple(calls), relations=relations)
    plan = complete_source_policy_plan(compile_ruleset(ruleset, rules=rules, rulesets={ruleset.id:ruleset}), configured, handlers=handlers)
    return plan, handlers


def _execute(rule_id, text="import example.module\n", **kwargs):
    plan, handlers = _plan(rule_id, **kwargs)
    context = _resource_context("base_lib", text)
    result = execute_rule_plan(plan, context, handlers=handlers)
    params = result.to_dict()["plan"]["calls"][0]["params"]
    return result, params


@pytest.mark.parametrize("configured", [None, default_effective_policy().to_purity_policy()])
def test_effects_and_imports_have_distinct_native_defaults(configured):
    effects, params = _execute("vibeflow.no_side_effects", "import importlib\n", configured=configured)
    assert effects.findings == ()
    assert params["policy"] == {"imports":{"allowed_roots":[], "banned_roots":[],
        "allowed_modules":["urllib.parse","vibeflow"], "banned_modules":[]}}
    imports, params = _execute("vibeflow.import_side_effects", "import importlib\n", configured=configured)
    assert imports.findings == ()
    assert params["policy"] == {"imports":{name:[] for name in ("allowed_roots","banned_roots","allowed_modules","banned_modules")}}


@pytest.mark.parametrize("rule_id", ["vibeflow.no_side_effects", "vibeflow.import_side_effects"])
@pytest.mark.parametrize("policy,denied", [
    ({"imports":{"banned_roots":["example"]}}, True),
    ({"imports":{"banned_roots":["example"],"allowed_roots":["example"]}}, False),
    ({"imports":{"banned_roots":["example"],"allowed_modules":["example.module"]}}, False),
    ({"imports":{"banned_roots":["example"],"allowed_roots":["example"],"allowed_modules":["example"],"banned_modules":["example.module"]}}, True),
])
def test_import_policy_precedence_is_applied_by_both_handlers(rule_id, policy, denied):
    result, params = _execute(rule_id, policy=policy)
    assert bool(result.findings) == denied
    assert params["policy"]["imports"]["banned_roots"] == ["example"]
    assert all(item.definition_id == rule_id for item in result.findings)


def test_explicit_empty_arrays_do_not_restore_effect_import_defaults():
    result, params = _execute("vibeflow.no_side_effects", "import importlib\n", policy={"imports":{"banned_roots":[]}})
    assert result.findings == ()
    assert params["policy"]["imports"]["banned_roots"] == []
    # Calls and absolute IO effects are still checked after clearing policy bans.
    result, _ = _execute("vibeflow.no_side_effects", 'import importlib\ndef helper():\n    importlib.import_module("example")\n', policy={"imports":{"banned_roots":[]}})
    assert result.findings == ()


@pytest.mark.parametrize("text", ["import ctypes\n", "from sys import stdout\n", "from io import open\n", "from http import client\n"])
def test_policy_allowances_do_not_lift_effect_import_categories(text):
    result, _ = _execute("vibeflow.no_side_effects", text, policy={"imports":{"allowed_roots":["ctypes","sys","io","http"],
        "allowed_modules":["ctypes","sys","io","http"], "banned_roots":[],"banned_modules":[]}})
    assert {item.code for item in result.findings} == (set() if text == "import ctypes\n" else {"BASE_LIB.BANNED_IMPORT"})


@pytest.mark.parametrize("policy", [{"node_source":{"max_lines":1}}, {"audit_marker":{}},
    {"imports":{"audit_marker":[]}}, {"imports":{"banned_roots":"example"}}])
@pytest.mark.parametrize("rule_id", ["vibeflow.no_side_effects", "vibeflow.import_side_effects"])
def test_irrelevant_or_invalid_policy_is_rejected_in_actual_rule_plan(rule_id, policy):
    with pytest.raises(ValueError):
        _plan(rule_id, policy=policy)


def test_numeric_handler_does_not_accept_import_parameters():
    with pytest.raises(ValueError, match="imports"):
        _plan("vibeflow.maintainability", policy={"imports":{"banned_roots":[]}})


@pytest.mark.parametrize("section,value", [("banned_roots",[]), ("allowed_modules",[])])
def test_explicit_project_configuration_keeps_empty_fields_and_only_consumer_sections(tmp_path, section, value):
    configured = resolve_effective_policy({"policy":{"imports":{section:value},"node_source":{"max_lines":3}}},
        config_path=tmp_path / "workflow.jsonc").effective_policy.to_purity_policy()
    assert configured.configured_import_fields == frozenset({section})
    for rule_id in ("vibeflow.no_side_effects", "vibeflow.import_side_effects"):
        result, params = _execute(rule_id, configured=configured)
        assert result.findings == ()
        assert set(params["policy"]) == {"imports"}
        assert params["policy"]["imports"][section] == []


def test_whole_object_override_does_not_revive_discarded_rule_policy():
    configured = EffectivePolicy({"imports":{"banned_roots":["example"]}},("test.configuration",)).to_purity_policy()
    result, params = _execute("vibeflow.no_side_effects", configured=configured,
        defaults={"imports":{"banned_modules":["example.module"]}},
        policy={"imports":{"banned_modules":["example"]}}, override={"imports":{"allowed_roots":["example"]}})
    assert result.findings == ()
    assert params["policy"]["imports"]["banned_roots"] == ["example"]
    assert params["policy"]["imports"]["allowed_roots"] == ["example"]
    assert params["policy"]["imports"]["banned_modules"] == []


@pytest.mark.parametrize("rule_id", ["vibeflow.no_side_effects", "vibeflow.import_side_effects"])
@pytest.mark.parametrize("scope", ["unconstrained", "typo", "NONE"])
def test_unsupported_scope_is_a_real_rule_failure(rule_id, scope):
    result, _ = _execute(rule_id, effect_scope=scope)
    assert any(item.code == "RULE.EXECUTION" and scope in item.message for item in result.findings)
