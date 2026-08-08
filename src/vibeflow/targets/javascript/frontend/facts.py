"""Build language-neutral implementation facts from JS/TS descriptors."""

from __future__ import annotations

from vibeflow.core.constants import (
    EFFECT_SCOPE_GLOBAL_STATE,
    EFFECT_SCOPE_NONE,
    FLOW_KIND_GLOBAL_STATE,
)
from vibeflow.core.descriptors import DescriptorCatalogs, NodeCatalog
from vibeflow.core.models import ImplementationFact, ImplementationFacts


class JavascriptImplementationFactsError(ValueError):
    """A target-neutral JavaScript implementation contract is ambiguous."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        self.message = str(message)
        super().__init__(self.message)


def validate_javascript_descriptor_catalogs(
    catalogs: DescriptorCatalogs,
) -> None:
    """Reject implementation languages that do not belong to a JS root.

    A JavaScript project root is a language-backend boundary, not a catalog of
    cross-language alternatives.  Validate every registered implementation,
    including currently unused resources, so target-neutral review and a
    platform-selected build apply the same root contract.
    """

    groups = (
        ("node", ((item.type_key, item) for item in catalogs.nodes)),
        ("base_lib", ((item.id, item) for item in catalogs.base_libs)),
        ("plugin", ((item.id, item) for item in catalogs.plugins)),
        (
            "host_extension",
            ((item.id, item) for item in catalogs.host_extensions),
        ),
    )
    for kind, resources in groups:
        for resource_id, descriptor in resources:
            invalid = sorted(
                {
                    implementation.language
                    for implementation in descriptor.implementations
                    if implementation.language
                    not in {"javascript", "typescript"}
                }
            )
            if invalid:
                raise JavascriptImplementationFactsError(
                    "VF_AOT_CONTRACT_INVALID",
                    (
                        f"JavaScript project {kind} '{resource_id}' declares "
                        f"foreign implementation languages: {invalid}"
                    ),
                )


def implementation_facts_from_catalog(
    catalog: NodeCatalog,
    *,
    target: str,
) -> ImplementationFacts:
    """Project static Node descriptors into the facts consumed by Core.

    Availability is validated later for each used Node, so every descriptor
    contributes its target-neutral flow kind. When exactly one JS/TS
    implementation matches the target, its execution facts are included too.
    """

    facts: list[ImplementationFact] = []
    for descriptor in catalog.descriptors():
        candidates = tuple(
            implementation
            for implementation in descriptor.implementations
            if implementation.language in {"javascript", "typescript"}
            and target in implementation.targets
        )
        selected = candidates[0] if len(candidates) == 1 else None
        completion = selected.completion if selected is not None else "immediate"
        source = selected.source if selected is not None else None
        facts.append(
            ImplementationFact(
                type_key=descriptor.type_key,
                flow_kind=descriptor.flow_kind,
                effect_scope=_effect_scope(descriptor.flow_kind),
                runtime_dispatch=None,
                requires=descriptor.contract.requires,
                provides=descriptor.contract.provides,
                completion=completion,
                schedule="inline",
                executor=(
                    "event_loop" if completion == "suspend" else "current"
                ),
                source_kind=source.kind if source is not None else "",
                source_ref=source.ref if source is not None else "",
                source_export=(source.export or "") if source is not None else "",
            )
        )
    return ImplementationFacts(tuple(facts), strict=True)


def target_neutral_implementation_facts_from_catalog(
    catalog: NodeCatalog,
) -> ImplementationFacts:
    """Project JS/TS descriptors into Core facts without choosing a platform.

    Browser and Node implementations may use different source files, but they
    must agree on execution completion.  Completion changes workflow scheduling
    semantics, so treating it as a platform-specific detail would make a
    target-neutral architecture review ambiguous.
    """

    facts: list[ImplementationFact] = []
    for descriptor in catalog.descriptors():
        candidates = tuple(
            implementation
            for implementation in descriptor.implementations
            if implementation.language in {"javascript", "typescript"}
        )
        if not candidates:
            continue
        completions = {item.completion for item in candidates}
        if len(completions) != 1:
            raise JavascriptImplementationFactsError(
                "VF_AOT_CONTRACT_INVALID",
                (
                    f"node '{descriptor.type_key}' has platform implementations "
                    f"with different completion contracts: {sorted(completions)}"
                ),
            )
        completion = next(iter(completions))
        facts.append(
            ImplementationFact(
                type_key=descriptor.type_key,
                flow_kind=descriptor.flow_kind,
                effect_scope=_effect_scope(descriptor.flow_kind),
                runtime_dispatch=None,
                requires=descriptor.contract.requires,
                provides=descriptor.contract.provides,
                completion=completion,
                schedule="inline",
                executor=(
                    "event_loop" if completion == "suspend" else "current"
                ),
            )
        )
    return ImplementationFacts(tuple(facts), strict=True)


def _effect_scope(flow_kind: str) -> str:
    return (
        EFFECT_SCOPE_GLOBAL_STATE
        if flow_kind == FLOW_KIND_GLOBAL_STATE
        else EFFECT_SCOPE_NONE
    )


__all__ = [
    "JavascriptImplementationFactsError",
    "implementation_facts_from_catalog",
    "target_neutral_implementation_facts_from_catalog",
    "validate_javascript_descriptor_catalogs",
]
