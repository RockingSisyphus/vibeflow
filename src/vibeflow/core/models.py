"""Language-neutral request, validation, and implementation fact models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.core.flow import GraphConfig

if TYPE_CHECKING:
    from vibeflow.core.compiler import CompiledGraph
    from vibeflow.core.mainline import MainlineFinding


COMPLETIONS = frozenset({"immediate", "suspend"})
SCHEDULES = frozenset({"inline", "deferred", "detached"})
EXECUTORS = frozenset({"current", "event_loop", "thread"})


@dataclass(frozen=True)
class ImplementationFact:
    """Static, target-supplied facts about one node implementation."""

    type_key: str
    flow_kind: str = ""
    effect_scope: str = ""
    runtime_dispatch: bool | None = None
    requires: tuple[DataRequirement, ...] = ()
    provides: tuple[DataProvider, ...] = ()
    completion: str = "immediate"
    schedule: str = "inline"
    executor: str = "current"
    source_kind: str = ""
    source_ref: str = ""
    source_export: str = ""

    def __post_init__(self) -> None:
        text_fields = (
            self.type_key,
            self.flow_kind,
            self.effect_scope,
            self.completion,
            self.schedule,
            self.executor,
            self.source_kind,
            self.source_ref,
            self.source_export,
        )
        if not all(isinstance(value, str) for value in text_fields):
            raise ValueError("implementation facts must contain only strings")
        if self.runtime_dispatch is not None and not isinstance(
            self.runtime_dispatch, bool
        ):
            raise ValueError(
                "implementation runtime_dispatch must be true, false, or null"
            )
        requires = tuple(self.requires)
        provides = tuple(self.provides)
        if not all(isinstance(item, DataRequirement) for item in requires):
            raise ValueError(
                "implementation requires must contain DataRequirement values"
            )
        if not all(isinstance(item, DataProvider) for item in provides):
            raise ValueError(
                "implementation provides must contain DataProvider values"
            )
        object.__setattr__(self, "requires", requires)
        object.__setattr__(self, "provides", provides)
        if not self.type_key.strip():
            raise ValueError("implementation type_key must be non-empty")
        if self.completion not in COMPLETIONS:
            raise ValueError(
                f"implementation completion must be one of {sorted(COMPLETIONS)}"
            )
        if self.schedule not in SCHEDULES:
            raise ValueError(
                f"implementation schedule must be one of {sorted(SCHEDULES)}"
            )
        if self.executor not in EXECUTORS:
            raise ValueError(
                f"implementation executor must be one of {sorted(EXECUTORS)}"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "type_key": self.type_key,
            "flow_kind": self.flow_kind,
            "effect_scope": self.effect_scope,
            "runtime_dispatch": self.runtime_dispatch,
            "requires": [item.to_dict() for item in self.requires],
            "provides": [item.to_dict() for item in self.provides],
            "completion": self.completion,
            "schedule": self.schedule,
            "executor": self.executor,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "source_export": self.source_export,
        }


@dataclass(frozen=True)
class ImplementationFacts:
    """Deterministic implementation table supplied by a Target frontend."""

    nodes: tuple[ImplementationFact, ...] = ()
    strict: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.strict, bool):
            raise ValueError("implementation facts strict must be a boolean")
        if not all(isinstance(item, ImplementationFact) for item in self.nodes):
            raise ValueError(
                "implementation facts nodes must contain ImplementationFact values"
            )
        ordered = tuple(sorted(self.nodes, key=lambda item: item.type_key))
        keys = tuple(item.type_key for item in ordered)
        if len(keys) != len(set(keys)):
            raise ValueError("implementation facts contain duplicate type_key")
        object.__setattr__(self, "nodes", ordered)

    def get(self, type_key: str) -> ImplementationFact | None:
        return next(
            (item for item in self.nodes if item.type_key == type_key),
            None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "strict": self.strict,
            "nodes": [item.to_dict() for item in self.nodes],
        }


@dataclass(frozen=True)
class TargetFeatureSet:
    """Portable feature declaration used for validation and audit output."""

    target: str = "generic"
    features: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("target feature set target must be non-empty")
        features = frozenset(self.features)
        if not all(isinstance(item, str) and item for item in features):
            raise ValueError("target features must be non-empty strings")
        object.__setattr__(self, "features", features)

    def supports(self, feature: str) -> bool:
        return feature in self.features

    def to_dict(self) -> dict[str, object]:
        return {"target": self.target, "features": sorted(self.features)}


@dataclass(frozen=True)
class ValidatedWorkflow:
    graph: GraphConfig
    implementation_facts: ImplementationFacts = field(
        default_factory=ImplementationFacts
    )
    target_features: TargetFeatureSet = field(default_factory=TargetFeatureSet)

    def __post_init__(self) -> None:
        if not isinstance(self.graph, GraphConfig):
            raise ValueError("validated workflow graph must be a GraphConfig")
        if not isinstance(self.implementation_facts, ImplementationFacts):
            raise ValueError(
                "validated workflow implementation_facts must be ImplementationFacts"
            )
        if not isinstance(self.target_features, TargetFeatureSet):
            raise ValueError(
                "validated workflow target_features must be TargetFeatureSet"
            )


@dataclass(frozen=True)
class CoreCompileRequest:
    graph: GraphConfig
    implementation_facts: ImplementationFacts = field(
        default_factory=ImplementationFacts
    )
    target_features: TargetFeatureSet = field(default_factory=TargetFeatureSet)
    known_nodesets: frozenset[str] = field(default_factory=frozenset)
    owner: str = "pipeline"

    def __post_init__(self) -> None:
        if not isinstance(self.graph, GraphConfig):
            raise ValueError("core compile graph must be a GraphConfig")
        if not isinstance(self.implementation_facts, ImplementationFacts):
            raise ValueError(
                "core compile implementation_facts must be ImplementationFacts"
            )
        if not isinstance(self.target_features, TargetFeatureSet):
            raise ValueError(
                "core compile target_features must be TargetFeatureSet"
            )
        if not isinstance(self.owner, str) or not self.owner.strip():
            raise ValueError("core compile owner must be non-empty")
        object.__setattr__(self, "known_nodesets", frozenset(self.known_nodesets))


@dataclass(frozen=True)
class CoreCompilation:
    workflow: ValidatedWorkflow
    compiled_graph: "CompiledGraph"
    findings: tuple["MainlineFinding", ...] = ()

    @property
    def graph(self) -> "CompiledGraph":
        return self.compiled_graph


__all__ = [
    "COMPLETIONS",
    "EXECUTORS",
    "SCHEDULES",
    "CoreCompilation",
    "CoreCompileRequest",
    "ImplementationFact",
    "ImplementationFacts",
    "TargetFeatureSet",
    "ValidatedWorkflow",
]
