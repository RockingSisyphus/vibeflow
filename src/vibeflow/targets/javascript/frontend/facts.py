"""Build language-neutral implementation facts from JS/TS descriptors."""

from __future__ import annotations

from vibeflow.core.descriptors import NodeCatalog
from vibeflow.core.models import ImplementationFact, ImplementationFacts


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


__all__ = ["implementation_facts_from_catalog"]
