from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Mapping


@dataclass(frozen=True)
class RuntimeOptions:
    trace: str = "full"
    run_hooks: bool = True
    node_hooks: bool = True
    nodeset_hooks: bool = True
    block_hooks: bool = True
    execution: str = "plan"
    async_max_workers: int = 4
    nodeset_max_depth: int = 4
    allow_planned_stub: bool = False
    status_interval: float = 60.0
    status_file: str | None = None

    def __post_init__(self) -> None:
        if (isinstance(self.status_interval, bool) or not isinstance(self.status_interval, (int, float))
                or not math.isfinite(self.status_interval) or self.status_interval <= 0):
            raise ValueError("runtime status_interval must be positive finite seconds")
        if self.status_file is not None and (not isinstance(self.status_file, str) or not self.status_file):
            raise ValueError("runtime status_file must be a nonempty path string")
        if self.trace not in {"full", "boundary", "off"}:
            raise ValueError("runtime trace must be one of: full, boundary, off")
        if self.execution not in {"plan", "block", "compiled"}:
            raise ValueError("runtime execution must be one of: plan, block, compiled")
        if not isinstance(self.async_max_workers, int) or isinstance(self.async_max_workers, bool) or self.async_max_workers <= 0:
            raise ValueError("runtime async_max_workers must be a positive integer")
        if not isinstance(self.nodeset_max_depth, int) or isinstance(self.nodeset_max_depth, bool) or self.nodeset_max_depth <= 0:
            raise ValueError("runtime nodeset_max_depth must be a positive integer")


RuntimeHook = tuple[str, Callable[..., object]]


def runtime_options(value: RuntimeOptions | Mapping[str, object] | None) -> RuntimeOptions:
    if value is None:
        return RuntimeOptions()
    if isinstance(value, RuntimeOptions):
        return value
    return RuntimeOptions(**dict(value))


def merge_runtime_options(defaults: Mapping[str, object], overrides=None) -> RuntimeOptions:
    """Mappings overlay defaults; a complete RuntimeOptions instance replaces them."""
    if isinstance(overrides, Mapping):
        return runtime_options({**defaults, **overrides})
    return runtime_options(defaults if overrides is None else overrides)


@dataclass(frozen=True)
class HookPlan:
    before_run: tuple[RuntimeHook, ...] = ()
    after_run: tuple[RuntimeHook, ...] = ()
    run_failed: tuple[RuntimeHook, ...] = ()
    before_node: tuple[RuntimeHook, ...] = ()
    after_node: tuple[RuntimeHook, ...] = ()
    node_failed: tuple[RuntimeHook, ...] = ()
    before_nodeset: tuple[RuntimeHook, ...] = ()
    after_nodeset: tuple[RuntimeHook, ...] = ()
    nodeset_failed: tuple[RuntimeHook, ...] = ()
    before_block: tuple[RuntimeHook, ...] = ()
    after_block: tuple[RuntimeHook, ...] = ()
    block_failed: tuple[RuntimeHook, ...] = ()

    def for_hook(self, hook: str) -> tuple[RuntimeHook, ...]:
        return getattr(self, hook, ())


def runtime_hook_plan(plugins: tuple[object, ...], options: RuntimeOptions) -> HookPlan:
    hooks = {
        "before_run": options.run_hooks,
        "after_run": options.run_hooks,
        "run_failed": options.run_hooks,
        "before_node": options.node_hooks,
        "after_node": options.node_hooks,
        "node_failed": options.node_hooks,
        "before_nodeset": options.nodeset_hooks,
        "after_nodeset": options.nodeset_hooks,
        "nodeset_failed": options.nodeset_hooks,
        "before_block": options.block_hooks,
        "after_block": options.block_hooks,
        "block_failed": options.block_hooks,
    }
    table: dict[str, list[RuntimeHook]] = {hook: [] for hook in hooks}
    for plugin in plugins:
        plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
        for hook, enabled in hooks.items():
            if not enabled:
                continue
            method = getattr(plugin, hook, None)
            if callable(method):
                table[hook].append((plugin_name, method))
    return HookPlan(**{hook: tuple(methods) for hook, methods in table.items()})


def runtime_hook_table(plugins: tuple[object, ...], options: RuntimeOptions) -> dict[str, tuple[RuntimeHook, ...]]:
    plan = runtime_hook_plan(plugins, options)
    return {name: plan.for_hook(name) for name in HookPlan.__dataclass_fields__}


__all__ = [
    "HookPlan",
    "RuntimeHook",
    "RuntimeOptions",
    "runtime_hook_plan",
    "runtime_hook_table",
    "runtime_options",
    "merge_runtime_options",
]
