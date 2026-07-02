from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class RuntimeOptions:
    trace: str = "full"
    node_hooks: bool = True
    execution: str = "plan"
    async_flush_timeout: float | None = None

    def __post_init__(self) -> None:
        if self.trace not in {"full", "boundary", "off"}:
            raise ValueError("runtime trace must be one of: full, boundary, off")
        if self.execution not in {"plan", "block"}:
            raise ValueError("runtime execution must be one of: plan, block")
        if self.async_flush_timeout is not None and self.async_flush_timeout < 0:
            raise ValueError("runtime async_flush_timeout must be >= 0")


RuntimeHookTable = dict[str, tuple[tuple[str, Callable[..., object]], ...]]


def runtime_options(value: RuntimeOptions | Mapping[str, object] | None) -> RuntimeOptions:
    if value is None:
        return RuntimeOptions()
    if isinstance(value, RuntimeOptions):
        return value
    return RuntimeOptions(**dict(value))


def runtime_hook_table(plugins: tuple[object, ...], options: RuntimeOptions) -> RuntimeHookTable:
    hooks = ("before_run", "after_run", "before_node", "after_node", "before_nodeset", "after_nodeset")
    table: dict[str, list[tuple[str, Callable[..., object]]]] = {hook: [] for hook in hooks}
    for plugin in plugins:
        plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
        for hook in hooks:
            if not options.node_hooks and hook in {"before_node", "after_node"}:
                continue
            method = getattr(plugin, hook, None)
            if callable(method):
                table[hook].append((plugin_name, method))
    return {hook: tuple(methods) for hook, methods in table.items()}
