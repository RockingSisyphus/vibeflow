"""Python Target plugin and policy behavior boundaries."""

from __future__ import annotations
from tests.fixtures.support.declarations import native_registry

import os
from pathlib import Path
import subprocess
import sys

import pytest

from vibeflow.targets.python.project import plugins as target_plugins
from vibeflow.targets.python.project import policy as target_policy


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = PROJECT_ROOT / "src"


def _run_isolated(source: str) -> None:
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), existing) if part
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_target_plugin_and_policy_imports_do_not_load_outer_boundaries() -> None:
    _run_isolated(
        """
import sys
import vibeflow.targets.python.project.plugins
import vibeflow.targets.python.project.policy

forbidden = (
    "vibeflow.aot",
    "vibeflow.config",
    "vibeflow.policy",
    "vibeflow.runtime",
    "vibeflow.tooling",
)
loaded = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
)
assert loaded == [], loaded
"""
    )


def test_registry_preserves_priority_name_order_and_duplicate_messages() -> None:
    class Plugin:
        pass

    registry = target_plugins.PluginRegistry()
    beta = Plugin()
    alpha = Plugin()
    early = Plugin()
    registry.register(beta, name="beta", priority=20)
    registry.register(alpha, name="alpha", priority=20)
    registry.register(early, name="early", priority=10)

    assert registry.runtime_plugins() == (early, alpha, beta)
    assert [item.name for item in registry.descriptors()] == [
        "early",
        "alpha",
        "beta",
    ]

    with pytest.raises(ValueError, match="^duplicate runtime plugin: alpha$"):
        registry.register(Plugin(), name="alpha")

    replacement = Plugin()
    registry.register(
        replacement,
        name="alpha",
        priority=5,
        conflict="replace",
    )
    assert registry.runtime_plugins() == (replacement, early, beta)


def test_planned_plugin_is_not_imported_instantiated_or_registered(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "plugin-imported"
    source = tmp_path / "planned_plugin.py"
    source.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n"
        "raise RuntimeError('planned plugin must never import')\n",
        encoding="utf-8",
    )

    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.project.descriptor_loader import load_workflow_plugins
    (tmp_path / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    config = tmp_path / "main.jsonc"
    config.write_text(__import__("json").dumps({"plugins":[{"source":{"kind":"file","ref":"planned_plugin.py"},"status":"planned","id":"future"}], "pipeline":{"nodes":[]}}))
    loaded = load_workflow_plugins(load_project_workspace(config),config)
    assert loaded.catalogs.plugins.available() == ()
    assert loaded.records[0]["loaded"] is False
    assert not marker.exists()


def test_numeric_rule_defaults_are_pure_and_do_not_mutate_other_checks() -> None:
    first = target_policy.default_effective_policy()
    second = target_policy.default_effective_policy()
    target_policy.merge_policy(first.data, {"node_source": {"max_lines": 20}})
    assert first.to_purity_policy().max_source_lines == 20
    assert second.to_purity_policy().max_source_lines == 500
    assert first.sources == ("kernel.default_policy",)


def test_review_hooks_are_removed_from_lifecycle_registry() -> None:
    class OldPolicyPlugin:
        def extend_policy(self, _policy):
            raise AssertionError("old review hooks must not execute")

    registry = target_plugins.PluginRegistry()
    with pytest.raises(ValueError, match="unknown plugin type: policy"):
        registry.register(OldPolicyPlugin(), plugin_type="policy")
    assert not hasattr(registry, "policy_plugins")
    assert not hasattr(target_policy, "apply_policy_plugins")
    assert not hasattr(target_policy, "apply_policy_to_findings")


def test_selected_ruleset_can_allow_print_without_changing_process_identity() -> None:
    from tests.fixtures.support.rule_inspection import node_document
    from vibeflow.core.descriptors import DescriptorCatalogs
    from vibeflow.core.rules import RuleCall, RuleRelation, RulesetDescriptor
    from vibeflow.targets.python.project.registry import NodeRegistry
    from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules
    from vibeflow.targets.python.quality.source_context import (
        PythonSourceFile, PythonSourceNode, build_python_source_context,
    )
    from vibeflow.core.descriptors.decode import decode_resource as parse_descriptor_manifest

    source = PythonSourceFile.parse("/fixture/demo_node.py", "demo_node", '''
class DemoNode:
    def run_pure(self, inputs, params):
        print("a selected terminal operation")
        return {"demo.out": 1}
''')
    terminal = RulesetDescriptor("project.print", (RuleCall("base", ruleset_id="vibeflow.process"),), (
        RuleRelation("$self", "base/effects", "overrides", params={"effect_scope": "terminal"}),
        RuleRelation("$self", "base/imports", "overrides", params={"effect_scope": "terminal"}),
    ))
    catalogs = DescriptorCatalogs.empty()
    catalogs.rulesets.register(terminal)

    def check(selection):
        descriptor = parse_descriptor_manifest(node_document(rulesets=selection))
        assert descriptor.flow_kind == "process"
        registry = native_registry()
        registry.register(descriptor)
        registry.rule_catalogs = (*registry.rule_catalogs, catalogs)
        context = build_python_source_context((PythonSourceNode(descriptor, source.path, "DemoNode"),), (source,))
        return execute_python_node_rules(registry, context)

    rejected = check(["vibeflow.process"])
    assert any(item.code == "NODE.EFFECT.CALL_FORBIDDEN" for item in rejected.findings)
    allowed = check(["project.print"])
    assert not any(item.severity == "error" for item in allowed.findings)
    assert allowed.effect_scopes["demo.node"] == "terminal"
    assert any(invocation.results for invocation in allowed.executions)
