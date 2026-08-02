"""Stable Python execution-runtime API, loaded on demand."""

from __future__ import annotations

from importlib import import_module


_EXPORTS: dict[str, tuple[str, str]] = {}


def _export(module: str, *names: str) -> None:
    _EXPORTS.update({name: (module, name) for name in names})


_export(
    "vibeflow.targets.python.runtime.block_compiler",
    "CompiledBlock",
    "CompiledBlockResult",
    "PythonCompiledBlock",
    "compile_blocks",
    "explain_block_compilation",
)
_export("vibeflow.targets.python.runtime.compiled", "run_compiled_steps")
_export("vibeflow.targets.python.runtime.engine", "PipelineRuntime")
_export(
    "vibeflow.targets.python.runtime.errors",
    "BoundaryRuntimeError",
    "DelegateCliExit",
    "PipelineRuntimeError",
    "normalize_delegate_cli_system_exit",
)
_export(
    "vibeflow.targets.python.runtime.options",
    "HookPlan",
    "RuntimeHook",
    "RuntimeOptions",
    "runtime_hook_plan",
    "runtime_hook_table",
    "runtime_options",
)
_export(
    "vibeflow.targets.python.runtime.planning",
    "ExecutionPlan",
    "NodeFrame",
    "build_execution_plan",
)
_export(
    "vibeflow.targets.python.runtime.trace",
    "RuntimeTrace",
    "RuntimeTraceSink",
    "qualified_name",
)

del _export

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
