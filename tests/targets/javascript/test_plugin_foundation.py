"""JavaScript Target plugin descriptor, binding, and ABI foundations."""

from __future__ import annotations

import json
from pathlib import Path
import pickle

import pytest

from vibeflow.core.descriptors import PluginCatalog
from vibeflow.targets.javascript.frontend.bindings import (
    JavascriptBindingPlan,
)
from vibeflow.targets.javascript.frontend.plugin_descriptors import (
    JavascriptPluginError,
    parse_javascript_plugin_descriptor,
    parse_javascript_plugin_selection,
    resolve_javascript_plugins,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _descriptor(
    plugin_id: str = "demo.runtime",
    *,
    plugin_type: str = "runtime",
    completion: str = "immediate",
    targets: tuple[str, ...] = ("browser",),
    source: str = "plugins/runtime.ts",
) -> dict[str, object]:
    return {
        "kind": "plugin",
        "id": plugin_id,
        "type": plugin_type,
        "targets": list(targets),
        "priority": 20,
        "implementations": [
            {
                "language": "typescript",
                "targets": list(targets),
                "source": {"kind": "file", "ref": source},
                "completion": completion,
            }
        ],
        "config": {
            "schema": {
                "type": "object",
                "properties": {"mode": {"type": "string"}},
            },
            "defaults": {"mode": "default"},
        },
    }


def test_plugin_descriptor_parser_uses_single_factory_abi() -> None:
    descriptor = parse_javascript_plugin_descriptor(_descriptor())

    assert descriptor.id == "demo.runtime"
    assert descriptor.plugin_type == "runtime"
    assert descriptor.implementations[0].source.export == "createPlugin"
    assert descriptor.config_defaults["mode"] == "default"


def test_plugin_descriptor_parser_reports_stable_codes() -> None:
    wrong_kind = _descriptor()
    wrong_kind["kind"] = "node"
    with pytest.raises(JavascriptPluginError) as kind:
        parse_javascript_plugin_descriptor(wrong_kind)
    assert kind.value.code == "VF_AOT_PLUGIN_KIND"

    suspending_policy = _descriptor(
        plugin_type="policy",
        completion="suspend",
    )
    with pytest.raises(JavascriptPluginError) as factory:
        parse_javascript_plugin_descriptor(suspending_policy)
    assert factory.value.code == "VF_AOT_PLUGIN_FACTORY"

    invalid_config = _descriptor()
    invalid_config["config"] = []
    with pytest.raises(JavascriptPluginError) as config:
        parse_javascript_plugin_descriptor(invalid_config)
    assert config.value.code == "VF_AOT_PLUGIN_CONFIG"


def test_runtime_plugin_binding_is_absolute_frozen_and_deterministic(
    tmp_path: Path,
) -> None:
    descriptor = parse_javascript_plugin_descriptor(_descriptor())
    binding_plan = resolve_javascript_plugins(
        (
            parse_javascript_plugin_selection(
                {"id": descriptor.id, "config": {"mode": "selected"}}
            ),
        ),
        catalog=PluginCatalog((descriptor,)),
        target="browser",
        entry_mode="sync",
        project_root=tmp_path,
        source_hashes={descriptor.id: "a" * 64},
    )
    binding = binding_plan.runtime_plugins[0]

    assert binding.module == str((tmp_path / "plugins/runtime.ts").resolve())
    assert binding.export == "createPlugin"
    assert binding.config.to_value() == {"mode": "selected"}
    assert binding.source_hash == "a" * 64
    assert len(binding.config_hash) == 64
    assert json.loads(json.dumps(binding_plan.to_dict())) == binding_plan.to_dict()
    assert pickle.loads(pickle.dumps(binding)) == binding

    workflow_bindings = JavascriptBindingPlan(
        workflow_id="demo.workflow",
        runtime_plugins=binding_plan.runtime_plugins,
    )
    assert workflow_bindings.to_dict()["runtime_plugins"][0]["module"] == (
        binding.module
    )


def test_planned_plugin_never_resolves_source(tmp_path: Path) -> None:
    outside = tmp_path.parent / "must-not-resolve.ts"
    descriptor = _descriptor(source=str(outside))
    parsed = parse_javascript_plugin_descriptor(descriptor)
    binding_plan = resolve_javascript_plugins(
        (
            parse_javascript_plugin_selection(
                {
                    "id": parsed.id,
                    "status": "planned",
                    "type": "runtime",
                }
            ),
        ),
        catalog=PluginCatalog((parsed,)),
        target="browser",
        entry_mode="sync",
        project_root=tmp_path,
    )

    assert binding_plan.runtime_plugins == ()
    planned = binding_plan.planned_plugins[0]
    assert planned.implementation is None
    assert "module" not in planned.to_dict()
    assert "source_hash" not in planned.to_dict()


def test_sync_entry_rejects_suspending_runtime_plugin() -> None:
    descriptor = parse_javascript_plugin_descriptor(
        _descriptor(completion="suspend")
    )
    selection = parse_javascript_plugin_selection(descriptor.id)

    with pytest.raises(JavascriptPluginError) as failure:
        resolve_javascript_plugins(
            (selection,),
            catalog=PluginCatalog((descriptor,)),
            target="browser",
            entry_mode="sync",
            project_root=PROJECT_ROOT,
        )
    assert failure.value.code == "VF_ENTRY_MODE_PLUGIN_SUSPEND_IN_SYNC"

    async_plan = resolve_javascript_plugins(
        (selection,),
        catalog=PluginCatalog((descriptor,)),
        target="browser",
        entry_mode="async",
        project_root=PROJECT_ROOT,
    )
    assert async_plan.runtime_plugins[0].completion == "suspend"


def test_active_plugin_source_cannot_escape_project_root(tmp_path: Path) -> None:
    descriptor = parse_javascript_plugin_descriptor(
        _descriptor(source="../outside.ts")
    )
    with pytest.raises(JavascriptPluginError) as failure:
        resolve_javascript_plugins(
            (parse_javascript_plugin_selection(descriptor.id),),
            catalog=PluginCatalog((descriptor,)),
            target="browser",
            entry_mode="sync",
            project_root=tmp_path,
        )
    assert failure.value.code == "VF_AOT_PLUGIN_SOURCE"


def test_plugin_abi_declaration_is_packaged_with_the_target() -> None:
    declaration = (
        PROJECT_ROOT
        / "src/vibeflow/targets/javascript/resources/plugin_abi.d.ts"
    )
    source = declaration.read_text(encoding="utf-8")

    assert '"vibeflow.plugin.v1"' in source
    assert "interface RuntimePlugin" in source
    assert "type CreateRuntimePlugin" in source
