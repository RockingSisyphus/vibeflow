"""Language-neutral plugin descriptors and Planned selection semantics."""

from __future__ import annotations

import json

import pytest

from vibeflow.core.descriptors import (
    DescriptorCatalogError,
    DescriptorModelError,
    ImplementationDescriptor,
    PluginCatalog,
    PluginDescriptor,
    PluginSelection,
    PluginSelectionError,
    SourceLocator,
    resolve_plugin_selections,
)


def _implementation(
    ref: str,
    *,
    target: str = "browser",
    completion: str = "immediate",
) -> ImplementationDescriptor:
    return ImplementationDescriptor(
        language="typescript",
        targets=(target,),
        source=SourceLocator(
            kind="file",
            ref=ref,
            export="createRuntimePlugin",
        ),
        completion=completion,
    )


def _descriptor(
    plugin_id: str,
    *,
    plugin_type: str = "runtime",
    dependencies: tuple[str, ...] = (),
    priority: int = 100,
) -> PluginDescriptor:
    return PluginDescriptor(
        id=plugin_id,
        plugin_type=plugin_type,
        targets=("browser",),
        implementations=(_implementation(f"plugins/{plugin_id}.ts"),),
        dependencies=dependencies,
        config_schema={"type": "object"},
        config_defaults={"mode": "default"},
        priority=priority,
    )


def test_plugin_descriptor_is_frozen_json_data() -> None:
    descriptor = _descriptor("demo.runtime")

    assert json.loads(json.dumps(descriptor.to_dict()))["kind"] == "plugin"
    assert descriptor.to_dict()["config"] == {
        "schema": {"type": "object"},
        "defaults": {"mode": "default"},
    }
    with pytest.raises(TypeError):
        descriptor.config_defaults["mode"] = "changed"  # type: ignore[index]
    with pytest.raises(DescriptorModelError, match="must contain JSON values"):
        PluginDescriptor(
            id="demo.invalid",
            plugin_type="runtime",
            targets=("browser",),
            implementations=(_implementation("plugins/invalid.ts"),),
            config_defaults={"factory": lambda: None},
        )


def test_plugin_catalog_uses_stable_duplicate_and_conflict_codes() -> None:
    descriptor = _descriptor("demo.runtime")
    catalog = PluginCatalog((descriptor,))

    with pytest.raises(DescriptorCatalogError) as duplicate:
        catalog.register(descriptor)
    assert duplicate.value.code == "DESCRIPTOR.DUPLICATE"

    with pytest.raises(DescriptorCatalogError) as conflict:
        catalog.register(_descriptor("demo.runtime", priority=1))
    assert conflict.value.code == "DESCRIPTOR.CONFLICT"


def test_implemented_plugin_closure_is_dependency_first_and_uses_defaults() -> None:
    dependency = _descriptor("demo.dependency", priority=200)
    root = _descriptor(
        "demo.root",
        dependencies=("demo.dependency",),
        priority=10,
    )
    resolution = resolve_plugin_selections(
        (PluginSelection(id="demo.root", config={"mode": "selected"}),),
        catalog=PluginCatalog((root, dependency)),
        target="browser",
    )

    assert tuple(item.id for item in resolution.active) == (
        "demo.dependency",
        "demo.root",
    )
    assert resolution.active[0].config["mode"] == "default"
    assert resolution.active[1].config["mode"] == "selected"
    assert resolution.active[1].implementation is not None
    assert tuple(item.id for item in resolution.declared) == ("demo.root",)


def test_unknown_planned_plugin_is_architecture_only() -> None:
    resolution = resolve_plugin_selections(
        (
            PluginSelection(
                id="future.policy",
                status="planned",
                plugin_type="policy",
                targets=("browser",),
                config={"mode": "review"},
            ),
        ),
        catalog=PluginCatalog(),
        target="browser",
    )

    assert resolution.active == ()
    assert resolution.planned[0].implementation is None
    assert "implementation" not in resolution.planned[0].to_dict()
    assert resolution.planned[0].descriptor is None


def test_implemented_plugin_cannot_depend_on_planned_plugin() -> None:
    root = _descriptor("demo.root", dependencies=("demo.future",))
    future = _descriptor("demo.future")

    with pytest.raises(PluginSelectionError) as failure:
        resolve_plugin_selections(
            (
                PluginSelection(id="demo.root"),
                PluginSelection(id="demo.future", status="planned"),
            ),
            catalog=PluginCatalog((root, future)),
            target="browser",
        )
    assert failure.value.code == "PLUGIN.SELECTION.PLANNED_DEPENDENCY"


def test_plugin_dependency_cycle_and_target_fail_with_stable_codes() -> None:
    first = _descriptor("demo.first", dependencies=("demo.second",))
    second = _descriptor("demo.second", dependencies=("demo.first",))

    with pytest.raises(PluginSelectionError) as cycle:
        resolve_plugin_selections(
            (PluginSelection(id="demo.first"),),
            catalog=PluginCatalog((first, second)),
            target="browser",
        )
    assert cycle.value.code == "PLUGIN.SELECTION.CYCLE"

    with pytest.raises(PluginSelectionError) as target:
        resolve_plugin_selections(
            (PluginSelection(id="demo.first"),),
            catalog=PluginCatalog((first, second)),
            target="node",
        )
    assert target.value.code == "PLUGIN.SELECTION.TARGET"
