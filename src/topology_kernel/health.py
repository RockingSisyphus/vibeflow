from __future__ import annotations

from dataclasses import dataclass, field

from .compiler import GraphCompiler, GraphCompileError
from .graph_config import GraphConfig
from .purity import PurityPolicy, validate_node_class
from .registry import NodeRegistry, NodeRegistryError


@dataclass(frozen=True)
class HealthFinding:
    severity: str
    code: str
    message: str
    subject: str = ""


@dataclass(frozen=True)
class HealthReport:
    status: str
    errors: tuple[HealthFinding, ...] = ()
    warnings: tuple[HealthFinding, ...] = ()
    info: dict[str, object] = field(default_factory=dict)


def validate_graph_health(
    graph: GraphConfig,
    *,
    registry: NodeRegistry,
    purity_policy: PurityPolicy | None = None,
) -> HealthReport:
    errors: list[HealthFinding] = []
    warnings: list[HealthFinding] = []
    try:
        compiled = GraphCompiler().compile(graph)
    except GraphCompileError as exc:
        return HealthReport(
            status="failed",
            errors=(HealthFinding("error", "graph_compile_error", str(exc)),),
        )

    for spec in graph.nodes:
        if spec.node_type.startswith("nodeset."):
            continue
        try:
            node_cls = registry.get(spec.node_type)
        except NodeRegistryError as exc:
            errors.append(HealthFinding("error", "unknown_node_type", str(exc), spec.name))
            continue
        for violation in validate_node_class(node_cls, policy=purity_policy):
            errors.append(HealthFinding("error", violation.code, violation.message, spec.name))

    consumed = {key for node in graph.nodes for key in node.requires}
    provided = {key for node in graph.nodes for key in node.provides}
    for key in sorted(provided - consumed):
        warnings.append(HealthFinding("warning", "unconsumed_output", f"output key is not consumed: {key}", key))

    status = "failed" if errors else "ok"
    return HealthReport(
        status=status,
        errors=tuple(errors),
        warnings=tuple(warnings),
        info={
            "explicit_edges": [edge.pair for edge in compiled.explicit_edges],
            "data_edges": [edge.pair for edge in compiled.data_edges],
            "effective_edges": [edge.pair for edge in compiled.effective_edges],
            "loops": [loop.name for loop in compiled.loops],
        },
    )
