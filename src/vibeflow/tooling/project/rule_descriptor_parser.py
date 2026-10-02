"""Decode declarative Rule/Ruleset resources; handlers remain ordinary code."""

from __future__ import annotations

from typing import Any, Mapping

from vibeflow.core.descriptors.models import DescriptorModelError
from vibeflow.core.rules.models import RuleCall, RuleDescriptor, RuleRelation, RulesetDescriptor
from vibeflow.tooling.project.descriptor_values import (
    check_fields, mapping_or_empty, object_list, optional_string, required_string, string_list,
)


def parse_rule(data: Mapping[str, Any]) -> RuleDescriptor:
    from vibeflow.tooling.project.descriptor_parser import _parse_implementations
    check_fields(data, allowed={"kind", "id", "display_name", "description", "implementations", "inputs", "outputs", "params_schema", "params_defaults", "handler", "scope"}, field="rule")
    return _construct(RuleDescriptor,
        id=required_string(data.get("id"), field="rule.id"),
        display_name=optional_string(data.get("display_name")),
        description=optional_string(data.get("description")),
        implementations=_parse_implementations(data.get("implementations", ()), field="rule.implementations", default_export="check"),
        inputs=mapping_or_empty(data.get("inputs"), field="rule.inputs"),
        outputs=mapping_or_empty(data.get("outputs"), field="rule.outputs"),
        params_schema=mapping_or_empty(data.get("params_schema"), field="rule.params_schema"),
        params_defaults=mapping_or_empty(data.get("params_defaults"), field="rule.params_defaults"),
        handler=optional_string(data.get("handler")),
        scope=optional_string(data.get("scope")) or "call",
    )


def parse_ruleset(data: Mapping[str, Any]) -> RulesetDescriptor:
    check_fields(data, allowed={"kind", "id", "display_name", "description", "calls", "relations", "entrypoints"}, field="ruleset")
    calls = []
    for value in object_list(data.get("calls", ()), field="ruleset.calls"):
        check_fields(value, allowed={"id", "rule_id", "ruleset_id", "params"}, field="ruleset.call")
        calls.append(_construct(RuleCall,
            id=required_string(value.get("id"), field="call.id"),
            rule_id=optional_string(value.get("rule_id")), ruleset_id=optional_string(value.get("ruleset_id")),
            params=mapping_or_empty(value.get("params"), field="call.params")))
    relations = []
    for value in object_list(data.get("relations", ()), field="ruleset.relations"):
        check_fields(value, allowed={"source", "target", "kind", "bindings", "params", "replace_rule"}, field="ruleset.relation")
        relations.append(_construct(RuleRelation,
            source=required_string(value.get("source"), field="relation.source"),
            target=required_string(value.get("target"), field="relation.target"),
            kind=required_string(value.get("kind"), field="relation.kind"),
            bindings=mapping_or_empty(value.get("bindings"), field="relation.bindings"),
            params=mapping_or_empty(value.get("params"), field="relation.params"),
            replace_rule=optional_string(value.get("replace_rule"))))
    entries = mapping_or_empty(data.get("entrypoints"), field="ruleset.entrypoints")
    return _construct(RulesetDescriptor,
        id=required_string(data.get("id"), field="ruleset.id"), calls=tuple(calls), relations=tuple(relations),
        entrypoints={key: string_list(value, field=f"ruleset.entrypoints.{key}") for key, value in entries.items()},
        display_name=optional_string(data.get("display_name")), description=optional_string(data.get("description")))


def _construct(model, **values):
    try:
        return model(**values)
    except ValueError as exc:
        raise DescriptorModelError(str(exc)) from exc
