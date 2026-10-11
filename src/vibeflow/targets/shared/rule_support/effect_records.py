"""Effect-policy Records consumed by Target bindings."""
from typing import Any, Mapping

EFFECT_POLICY_TYPE = "vibeflow.effect_policy.v1"


def effect_policies(result: Any) -> tuple[Mapping[str, Any], ...]:
    """Read explicit policy outputs; never infer grants from flow_kind."""
    values = result.results.values() if hasattr(result, "results") else (result,)
    unique = {id(item): item for item in values}
    return tuple(record.value for item in unique.values() if item.state == "completed"
                 for record in item.records.values() if record.type_id == EFFECT_POLICY_TYPE and isinstance(record.value, Mapping))
