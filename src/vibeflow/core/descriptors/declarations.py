"""A loaded declaration with an optional opaque, Target-owned implementation handle."""

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ResourceDefinition:
    descriptor: Any
    implementation: Any = None
    path: str = ""
    line: int | None = None
    symbol: str = ""


@dataclass(frozen=True)
class ResourceDiscovery:
    """Target declaration results and observed source loading, without IO."""
    resources: tuple[ResourceDefinition, ...] = ()
    load_states: Mapping[str, str] = field(default_factory=dict)
