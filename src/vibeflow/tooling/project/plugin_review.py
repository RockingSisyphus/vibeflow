"""Target-neutral Plugin selection facts for architecture review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vibeflow.core.descriptors import (
    PluginCatalog,
    PluginReviewRecord,
    PluginSelection,
    PluginSelectionError,
    review_plugin_selections,
)


@dataclass(frozen=True)
class PluginReviewResource:
    """A Core review record with project source ownership attached."""

    record: PluginReviewRecord
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""

    @property
    def status(self) -> str:
        return self.record.status

    def to_dict(self) -> dict[str, object]:
        payload = self.record.to_dict()
        if self.root_id:
            payload["root_id"] = self.root_id
        if self.root_path:
            payload["root_path"] = self.root_path
        if self.source_path:
            payload["source_path"] = self.source_path
        return payload


def load_plugin_review_resources(
    config: Mapping[str, Any],
    *,
    catalog: PluginCatalog,
) -> tuple[PluginReviewResource, ...]:
    """Parse workflow selections and resolve pure descriptor metadata."""

    raw = config.get("plugins", ())
    if raw in (None, ()):
        return ()
    if not isinstance(raw, list):
        raise PluginSelectionError(
            "PLUGIN.SELECTION.SCHEMA",
            "plugins must be a list",
        )
    selections: list[PluginSelection] = []
    for index, item in enumerate(raw):
        selection = _plugin_selection(item, index=index)
        if selection is not None:
            selections.append(selection)
    return tuple(
        PluginReviewResource(record)
        for record in review_plugin_selections(
            tuple(selections),
            catalog=catalog,
        )
    )


def _plugin_selection(
    value: object,
    *,
    index: int,
) -> PluginSelection | None:
    if isinstance(value, str):
        return PluginSelection(id=value)
    if not isinstance(value, Mapping):
        raise PluginSelectionError(
            "PLUGIN.SELECTION.SCHEMA",
            f"plugins[{index}] must be a string id or object",
        )
    if value.get("enabled", True) is False:
        return None
    raw_config = value.get("config", value.get("settings", {}))
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise PluginSelectionError(
            "PLUGIN.SELECTION.SCHEMA",
            f"plugins[{index}].config must be an object",
            str(value.get("id", "") or ""),
        )
    return PluginSelection(
        id=str(value.get("id", "") or ""),
        status=str(value.get("status", "implemented") or "implemented"),
        plugin_type=str(value.get("type", "") or ""),
        targets=_string_tuple(value.get("targets", ())),
        dependencies=_string_tuple(value.get("dependencies", ())),
        config={str(key): item for key, item in raw_config.items()},
        priority=value.get("priority"),
        display_name=str(value.get("display_name", "") or ""),
        description=str(value.get("description", "") or ""),
        version=str(value.get("version", "") or ""),
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, (list, tuple)):
        raise PluginSelectionError(
            "PLUGIN.SELECTION.SCHEMA",
            "plugin targets and dependencies must be lists",
        )
    return tuple(str(item).strip() for item in value)


__all__ = ["PluginReviewResource", "load_plugin_review_resources"]
