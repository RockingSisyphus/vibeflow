"""Fixed standard-plugin declarations and their native implementation bindings."""
from dataclasses import dataclass, replace
import inspect
from types import MappingProxyType

from vibeflow.core.descriptors.contributions import ContributionBuilder, ResourceOrigin
from vibeflow.core.descriptors.models import RuleImplementationDescriptor, SourceLocator


_BUILTIN_PLUGIN_ID = "vibeflow.core"


def configured_rule_defaults(rule, configured, origin, *, factory):
    """Fill a native declaration's schema without replacing external defaults."""
    automatic = (origin is not None and origin.plugin_id == _BUILTIN_PLUGIN_ID
        and origin.path == str(inspect.getsourcefile(factory))
        and origin.symbol == factory.__qualname__
        and origin.line == inspect.getsourcelines(factory)[1])
    return {name: value for name, value in configured.items()
            if name in rule.params_schema
            and (automatic or name not in rule.params_defaults)}


@dataclass(frozen=True)
class BuiltinPlugin:
    id: str
    _contributions: object
    _bindings: object
    source: str
    session: object = None

    def contributions(self, config=None):
        return self._contributions._with_config(config)

    def bindings(self):
        return self._bindings

    def close(self):
        pass


def make_builtin_plugin(rules, rulesets, handlers, *, declaration_origins):
    """Pair fixed portable declarations with Target-owned native bindings."""
    source = str(inspect.getsourcefile(make_builtin_plugin))
    builder = ContributionBuilder(_BUILTIN_PLUGIN_ID, source=source)
    bindings = {}
    for descriptor in rules:
        check = handlers[descriptor.id]
        path = str(inspect.getsourcefile(check))
        symbol = check.__qualname__
        descriptor = replace(descriptor, handler="", implementations=(
            RuleImplementationDescriptor("python", SourceLocator("file", path, symbol)),))
        builder.add(descriptor, origin=declaration_origins[("rule", descriptor.id)])
        bindings[("rule", descriptor.id)] = check
    for descriptor in rulesets:
        builder.add(descriptor, origin=declaration_origins[("ruleset", descriptor.id)])
    return BuiltinPlugin(builder.id, builder.finish(), MappingProxyType(bindings), source)


def project_plugin():
    from vibeflow.builtin.project_quality import project_quality_handlers, project_quality_resources
    rules, ruleset = project_quality_resources()
    from vibeflow.builtin import builtin_declaration_origins
    return make_builtin_plugin(rules, (ruleset,), project_quality_handlers(), declaration_origins=builtin_declaration_origins())
