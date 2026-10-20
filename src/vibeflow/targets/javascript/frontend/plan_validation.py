"""Native target feasibility and graph contracts for canonical JS plans."""
from vibeflow.block_compiler.model import BlockPlan, WorkflowPlan
from vibeflow.targets.javascript.frontend.errors import AotPlanError


def validate_javascript_plan(plan: WorkflowPlan) -> None:
    """Validate executable structure independently of optional review Rules."""
    _supported(plan, "workflow")
    _unique((item.key for item in plan.inputs), "pipeline input key")
    _unique((item.as_key for item in plan.outputs), "pipeline output alias")
    for block in plan.blocks:
        _supported(block, block.id)
        _validate_block(block)
        for node in block.nodes:
            if node.status != "planned":
                _supported(node, ".".join((*block.path, node.id)))
            if node.status == "planned" or node.planned_behavior not in ("", "blocking"):
                raise AotPlanError(f"node '{node.id}' uses planned/Python-only behavior and cannot target JS")
            _unique((item.type for item in node.requires), f"node '{node.id}' requirement type")
            _unique((item.key for item in node.provides), f"node '{node.id}' provider key")
            if (node.is_nodeset or node.is_loop) and not node.child_block:
                raise AotPlanError(f"composite node '{node.id}' has no child block")


def _supported(value: object, location: str) -> None:
    feature = ""
    if getattr(value, "executor", "") == "thread":
        feature = "thread_executor"
    elif getattr(value, "execution_lock", None) is not None:
        feature = "execution_locks"
    elif (getattr(value, "contains_global_state", False)
          or getattr(value, "flow_kind", "") == "global_state"
          or getattr(value, "effect_scope", "") == "global_state"):
        feature = "global_state"
    if feature:
        raise AotPlanError(
            f"JavaScript target does not support feature '{feature}' at {location}",
            code="TARGET.FEATURE.UNSUPPORTED",
        )


def _unique(values, subject: str) -> None:
    items = tuple(values)
    if len(items) != len(set(items)):
        raise AotPlanError(f"{subject} must contain unique values")


def _validate_block(block: BlockPlan) -> None:
    ids = {node.id for node in block.nodes}
    if len(ids) != len(block.nodes):
        raise AotPlanError(f"block '{block.id}' contains duplicate node ids")
    if set(block.order) != ids or len(block.order) != len(ids):
        raise AotPlanError("workflow order must contain every node exactly once")
    _unique(block.entries, "workflow entry")
    incoming = {route.target for route in block.routes if route.schedule}
    invalid = [entry for entry in block.entries if entry not in ids or entry in incoming
               or not block.node(entry).is_terminal]
    if invalid:
        raise AotPlanError(f"workflow entries must be terminal nodes without incoming routes: {invalid}",
                           code="VF_WORKFLOW_ENTRY")
    if block.nodes and not block.entries:
        raise AotPlanError("workflow block has nodes but no executable terminal entry", code="VF_WORKFLOW_ENTRY")
    for route in block.routes:
        if route.source not in ids or route.target not in ids:
            raise AotPlanError(f"route '{route.source} -> {route.target}' is not a workflow route")
        if not route.schedule and not route.transfer:
            raise AotPlanError(f"route '{route.source} -> {route.target}' must schedule, transfer, or both")
