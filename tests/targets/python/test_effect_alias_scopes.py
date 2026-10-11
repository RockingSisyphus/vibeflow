"""Effect aliases retain local identity across scope boundaries and joins."""

from textwrap import indent

import pytest

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.core.rules import RuleContext
from vibeflow.targets.python.quality import PythonSource
from vibeflow.targets.python.rules.node.effects import no_side_effects
from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context


KINDS = ("python_source", "node", "base_lib", "plugin")
FORMS = ("list", "set", "dict", "generator")
SCOPES = ("none", "terminal", "python_io", "global_state", "trusted")


def _comp(form, target, value, iterable="objects"):
    if form == "list":
        return "[" + value + " for " + target + " in " + iterable + "]"
    if form == "set":
        return "{" + value + " for " + target + " in " + iterable + "}"
    if form == "dict":
        return "{0: " + value + " for " + target + " in " + iterable + "}"
    return "(" + value + " for " + target + " in " + iterable + ")"


def _context(kind, body, *, parameters="objects, flag=False", prefix="import sys\n"):
    text = prefix + "def task(" + parameters + "):\n" + indent(body, "    ") + "\n"
    if kind == "node":
        text += "class Task:\n    def run_pure(self, inputs, params):\n        task(())\n        return {}\n"
    parsed = PythonSourceFile.parse("/virtual/effect_alias_scopes.py", "effect_alias_scopes", text)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Effect alias identity probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    nodes = (PythonSourceNode(descriptor, parsed.path, "Task"),) if kind == "node" else ()
    sources = build_python_source_context(nodes, (parsed,))
    facts = {"source_context":sources, "node_catalog":(),
        "source_owners":({"kind":kind, "id":"example.task", "role":"entry", "path":parsed.path,
                          "symbol":"Task" if kind == "node" else ""},)}
    if kind == "python_source":
        facts.update(python_source=PythonSource(parsed.module, "effect_alias_scopes.py", parsed.path, text), source_file=parsed)
    elif kind == "base_lib":
        facts.update(base_lib_file=parsed, resource_symbol="")
    elif kind == "plugin":
        facts.update(resource_source_file=parsed, resource_symbol="")
    return RuleContext(subject={"kind":kind, "id":"example.task", "type_key":"example.task"}, target="python", facts=facts)


def _review(kind, body, *, scope="none", parameters="objects, flag=False", prefix="import sys\n"):
    result = no_side_effects(_context(kind, body, parameters=parameters, prefix=prefix), {}, {"effect_scope":scope})
    assert result.state == "completed"
    assert all("<local>" not in item.message for item in result.findings), result.findings
    return result


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("variant", ("value", "attribute", "nested", "lambda_default", "starred"))
def test_local_comprehension_alias_escape_preserves_object_identity(kind, form, variant):
    target, value = "sys", "(alias := sys)"
    if variant == "attribute":
        value = "(alias := sys.stdout)"
    elif variant == "lambda_default":
        value = "(lambda value=(alias := sys): value)"
    elif variant == "starred":
        target = "(item, *sys)"
    expression = _comp(form, target, value)
    if variant == "nested":
        expression = "[" + expression + " for item in objects]"
    reference = "alias" if variant == "attribute" else "alias.argv"
    result = _review(kind, "list(" + expression + ")\nreturn " + reference)
    assert result.findings == (), (kind, form, variant, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("target", ("sys", "item"))
def test_local_alias_identity_is_independent_of_target_spelling(kind, target):
    result = _review(kind, "[(alias := " + target + ") for " + target + " in objects]\nreturn alias.argv")
    assert result.findings == (), (kind, target, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("assignment", ("alias = sys", "alias: object = sys", "(alias := sys)"))
@pytest.mark.parametrize("reference", ("alias.argv", "getattr(alias, 'argv')", "vars(alias)['argv']"))
def test_function_parameter_alias_keeps_local_identity_through_assignments_and_reflection(kind, assignment, reference):
    result = _review(kind, assignment + "\nreturn " + reference, parameters="sys", prefix="import sys\n")
    assert result.findings == (), (kind, assignment, reference, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("body", (
    "[(alias := sys) for item in objects]\nreturn alias.argv",
    "[(alias := sys) for sys in objects]\nif flag:\n    alias = sys\nreturn alias.argv",
    "alias = sys\n[(alias := sys) for sys in objects]\nreturn alias.argv",
    "alias = sys\nreturn getattr(alias, 'argv')",
))
def test_real_host_aliases_and_mixed_branch_facts_stay_forbidden(kind, scope, body):
    result = _review(kind, body, scope=scope)
    assert any("sys.argv" in item.message for item in result.findings), (kind, scope, body, result.findings)


@pytest.mark.parametrize("kind", KINDS)
def test_both_branch_local_overwrites_remove_previous_host_alias_identity(kind):
    body = "alias = sys\nif flag:\n    alias = objects\nelse:\n    alias = objects\nreturn alias.argv"
    result = _review(kind, body)
    assert result.findings == (), (kind, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("leaf", ("close", "read", "write"))
def test_local_callable_alias_does_not_invent_io_from_leaf_name(kind, scope, leaf):
    body = "callback = sys." + leaf + "\nreturn callback()"
    result = _review(kind, body, scope=scope, parameters="sys")
    calls = tuple(item for item in result.findings if "banned call:" in item.message)
    assert not calls, (kind, scope, leaf, result.findings)
    assert all(item.message == "banned call: callback" for item in calls), (kind, scope, leaf, result.findings)
    assert not any("banned process" in item.message or "terminal stream" in item.message for item in result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("scope", SCOPES)
def test_local_stdout_alias_does_not_invent_terminal_or_io_identity(kind, scope):
    body = "[(alias := sys.stdout) for sys in objects]\nreturn alias.write('a')"
    result = _review(kind, body, scope=scope)
    calls = tuple(item for item in result.findings if "banned call:" in item.message)
    assert not calls, (kind, scope, result.findings)
    assert all(item.message == "banned call: alias.write" for item in calls), (kind, scope, result.findings)
    assert not any("terminal stream" in item.message for item in result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("scope", SCOPES)
def test_local_callable_alias_does_not_create_an_ffi_security_ban(kind, scope):
    result = _review(kind, "callback = sys.CDLL\nreturn callback(None)", scope=scope, parameters="sys")
    assert result.findings == (), (kind, scope, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("namespace", ("sys", "os", "builtins"))
@pytest.mark.parametrize("body", (
    "alias = NAMESPACE\nreturn alias.__dict__['argv']",
    "alias = NAMESPACE\nalias.path = []\nreturn 1",
))
def test_local_namespace_alias_does_not_create_host_namespace_or_state_identity(kind, namespace, body):
    result = _review(kind, body.replace("NAMESPACE", namespace), scope="global_state", parameters=namespace, prefix="")
    # Local objects retain local identity even when their names resemble hosts.
    assert not any("process" in item.message or "ambient module state" in item.message
                   or "dynamic module namespace" in item.message for item in result.findings), (kind, namespace, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("namespace", ("sys", "os", "builtins", "importlib", "item"))
@pytest.mark.parametrize("body", (
    "alias = ROOT\nalias2 = alias\nreturn getattr(alias2, 'argv')",
    "alias = getattr(ROOT, 'argv')\nalias2 = alias\nreturn alias2",
    "alias = vars(ROOT)\nalias2 = alias\nreturn alias2['argv']",
    "alias = getattr(ROOT, '__dict__')\nalias2 = alias\nreturn alias2['argv']",
    "alias = vars(ROOT)['argv']\nalias2 = alias\nreturn alias2",
))
def test_local_alias_chains_and_reflection_escape_without_host_spelling_identity(kind, namespace, body):
    result = _review(kind, body.replace("ROOT", namespace), parameters=namespace, prefix="")
    assert result.findings == (), (kind, namespace, body, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("module", ("__vibeflow_local__", "example_package"))
def test_imported_module_dynamic_reads_are_not_a_security_gate(kind, module):
    body = "alias = host.tools\nreturn alias.__dict__[key]"
    result = _review(kind, body, parameters="key", prefix="import " + module + " as host\n", scope="global_state")
    assert result.findings == (), (kind, module, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("host_first", (False, True))
def test_same_spelling_local_and_host_branch_aliases_keep_both_identities(kind, host_first):
    local = "[(alias := sys) for sys in objects]"
    host = "alias = sys"
    first, second = (host, local) if host_first else (local, host)
    body = "if flag:\n    " + first + "\nelse:\n    " + second + "\nreturn alias.argv"
    result = _review(kind, body)
    assert any("sys.argv" in item.message for item in result.findings), (kind, host_first, result.findings)
