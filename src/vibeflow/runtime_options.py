from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class RuntimeOptions:
    trace: str = "full"
    run_hooks: bool = True
    node_hooks: bool = True
    nodeset_hooks: bool = True
    block_hooks: bool = True
    execution: str = "plan"
    async_flush_timeout: float | None = None

    def __post_init__(self) -> None:
        if self.trace not in {"full", "boundary", "off"}:
            raise ValueError("runtime trace must be one of: full, boundary, off")
        if self.execution not in {"plan", "block", "compiled"}:
            raise ValueError("runtime execution must be one of: plan, block, compiled")
        if self.async_flush_timeout is not None and self.async_flush_timeout < 0:
            raise ValueError("runtime async_flush_timeout must be >= 0")


RuntimeHook = tuple[str, Callable[..., object]]


def runtime_options(value: RuntimeOptions | Mapping[str, object] | None) -> RuntimeOptions:
    if value is None:
        return RuntimeOptions()
    if isinstance(value, RuntimeOptions):
        return value
    return RuntimeOptions(**dict(value))


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
