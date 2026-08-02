"""Python Target plugin and policy behavior boundaries."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from vibeflow.core import HealthFinding
from vibeflow.targets.python.project import plugins as target_plugins
from vibeflow.targets.python.project import policy as target_policy
from vibeflow.targets.python.project.plugin_loader import load_plugins_from_config


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

    assert registry.policy_plugins() == (early, alpha, beta)
    assert [item.name for item in registry.descriptors()] == [
        "early",
        "alpha",
        "beta",
    ]

    with pytest.raises(ValueError, match="^duplicate policy plugin: alpha$"):
        registry.register(Plugin(), name="alpha")

    replacement = Plugin()
    registry.register(
        replacement,
        name="alpha",
        priority=5,
        conflict="replace",
    )
    assert registry.policy_plugins() == (replacement, early, beta)


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

    registry, findings = load_plugins_from_config(
        {
            "plugins": [
                {
                    "path": str(source),
                    "class": "Plugin",
                    "type": "policy",
                    "status": "planned",
                }
            ]
        },
        base_path=tmp_path,
    )

    assert findings == ()
    assert registry.descriptors() == ()
    assert not marker.exists()


def test_target_policy_merge_and_finding_application_are_pure() -> None:
    policy = target_policy.default_effective_policy()
    target_policy.merge_policy(
        policy.data,
        {
            "rules": {
                "downgrades": [
                    {
                        "rule_id": "GRAPH.SMELL.DUPLICATE_LOGIC",
                        "to": "warning",
                        "reason": "accepted",
                    }
                ],
                "exemptions": [
                    {
                        "rule_id": "GRAPH.DATA.UNCONSUMED_PROVIDER",
                        "reason": "accepted",
                    }
                ],
            }
        },
    )
    duplicate = HealthFinding(
        rule_id="GRAPH.SMELL.DUPLICATE_LOGIC",
        message="duplicate",
        severity="error",
    )
    unconsumed = HealthFinding(
        rule_id="GRAPH.DATA.UNCONSUMED_PROVIDER",
        message="unconsumed",
        severity="warning",
    )

    errors, warnings, skipped = target_policy.apply_policy_to_findings(
        (duplicate,),
        (unconsumed,),
        policy,
    )

    assert errors == ()
    assert [item.rule_id for item in warnings] == [duplicate.rule_id]
    assert [item.rule_id for item in skipped] == [unconsumed.rule_id]


def test_target_policy_hooks_follow_registry_order_and_require_relaxations() -> None:
    calls: list[str] = []

    class StrictPlugin:
        def __init__(self, name: str) -> None:
            self.name = name

        def extend_policy(self, policy):
            calls.append(self.name)
            return {"node_source": {"max_lines": policy["node_source"]["max_lines"] - 1}}

    registry = target_plugins.PluginRegistry()
    registry.register(StrictPlugin("zeta"), priority=10)
    registry.register(StrictPlugin("alpha"), priority=10)
    effective = target_policy.default_effective_policy().data
    sources = ["kernel.default_policy"]
    findings: list[HealthFinding] = []
    target_policy.apply_policy_plugins(
        effective,
        sources,
        findings,
        registry,
        collect_schema_findings=lambda *_args, **_kwargs: (),
    )

    assert calls == ["alpha", "zeta"]
    assert findings == []
    assert effective["node_source"]["max_lines"] == 498
    assert sources == [
        "kernel.default_policy",
        "plugin.policy:alpha",
        "plugin.policy:zeta",
    ]

    class RelaxingPlugin:
        name = "relaxing"

        def extend_policy(self, policy):
            return {"node_source": {"max_lines": policy["node_source"]["max_lines"] + 1}}

    relaxing = target_plugins.PluginRegistry()
    relaxing.register(RelaxingPlugin())
    effective = target_policy.default_effective_policy().data
    findings = []
    target_policy.apply_policy_plugins(
        effective,
        ["kernel.default_policy"],
        findings,
        relaxing,
        collect_schema_findings=lambda *_args, **_kwargs: (),
    )

    assert [item.rule_id for item in findings] == [
        "PLUGIN.POLICY.RELAXATION_REQUIRED"
    ]
    assert findings[0].message == (
        "plugin policy relaxation must include relaxations list with rule_id, "
        "scope, reason, and source"
    )
    assert effective["node_source"]["max_lines"] == 500
