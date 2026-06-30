from __future__ import annotations

from .health_types import HealthFinding
from .plugin import PluginRegistry, plugin_error


def append_plugin_findings(
    plugin_registry: PluginRegistry | None,
    hook: str,
    errors: list[HealthFinding],
    warnings: list[HealthFinding],
    *args,
    plugin_types: tuple[str, ...] = ("policy",),
) -> None:
    if plugin_registry is None:
        return
    for plugin in _plugins_for_types(plugin_registry, plugin_types):
        _append_plugin_hook_findings(plugin, hook, errors, warnings, *args)


def _plugins_for_types(plugin_registry: PluginRegistry, plugin_types: tuple[str, ...]) -> tuple[object, ...]:
    plugins: list[object] = []
    if "policy" in plugin_types:
        plugins.extend(plugin_registry.policy_plugins())
    if "compiler" in plugin_types:
        plugins.extend(plugin_registry.compiler_plugins())
    if "runtime" in plugin_types:
        plugins.extend(plugin_registry.runtime_plugins())
    return tuple(plugins)


def _append_plugin_hook_findings(
    plugin: object,
    hook: str,
    errors: list[HealthFinding],
    warnings: list[HealthFinding],
    *args,
) -> None:
    method = getattr(plugin, hook, None)
    if not callable(method):
        return
    plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
    findings = _call_plugin_hook(method, hook, plugin_name, errors, *args)
    if findings is not None:
        _append_plugin_hook_result(findings, hook, plugin_name, errors, warnings)


def _call_plugin_hook(method, hook: str, plugin_name: str, errors: list[HealthFinding], *args):
    try:
        return method(*args)
    except Exception as exc:
        errors.append(plugin_error("PLUGIN.EXECUTION", f"PolicyPlugin.{hook} failed: {exc}", plugin_name))
        return None


def _append_plugin_hook_result(
    findings,
    hook: str,
    plugin_name: str,
    errors: list[HealthFinding],
    warnings: list[HealthFinding],
) -> None:
    if not isinstance(findings, (list, tuple)):
        errors.append(plugin_error("PLUGIN.FINDINGS.SHAPE", f"PolicyPlugin.{hook} must return a list/tuple of findings", plugin_name))
        return
    for finding in findings:
        _append_plugin_finding(finding, hook, plugin_name, errors, warnings)


def _append_plugin_finding(
    finding,
    hook: str,
    plugin_name: str,
    errors: list[HealthFinding],
    warnings: list[HealthFinding],
) -> None:
    if not isinstance(finding, HealthFinding):
        errors.append(plugin_error("PLUGIN.FINDINGS.SHAPE", f"PolicyPlugin.{hook} returned non-HealthFinding", plugin_name))
        return
    append_finding_by_severity(finding, errors, warnings)


def append_finding_by_severity(
    finding: HealthFinding,
    errors: list[HealthFinding],
    warnings: list[HealthFinding],
) -> None:
    if finding.severity == "warning":
        warnings.append(finding)
    else:
        errors.append(finding)
