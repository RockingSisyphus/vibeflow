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
        for task in block.tasks:
            _supported(task, task.id)
        for node in block.nodes:
            if node.flow_kind == "task_manager" and plan.entry_mode == "sync":
                raise AotPlanError("JavaScript task management requires an async workflow", code="VF_ENTRY_MODE_TASK_IN_SYNC")
            if node.status != "planned":
                _supported(node, ".".join((*block.path, node.id)))
            if node.status == "planned" or node.planned_behavior not in ("", "blocking"):
                raise AotPlanError(f"node '{node.id}' uses planned/Python-only behavior and cannot target JS")
            _unique((item.type for item in node.requires), f"node '{node.id}' requirement type")
            _unique((item.key for item in node.provides), f"node '{node.id}' provider key")
            if (node.is_nodeset or node.is_loop) and not node.child_block:
                raise AotPlanError(f"composite node '{node.id}' has no child block")
            if node.type_used == "vibeflow.io":
                _validate_io(node)


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
               or (block.kind != "task" and not block.node(entry).is_terminal)]
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


def _validate_io(node: object) -> None:
    if node.io_operation not in {"receive", "send"}:
        raise AotPlanError(f"vibeflow.io node '{node.id}' must declare receive or send", code="VF_IO_OPERATION")
    if not node.io_port:
        raise AotPlanError(f"vibeflow.io node '{node.id}' must declare a port", code="VF_IO_PORT")
    if node.io_operation == "receive" and (node.requires or len(node.provides) != 1 or node.completion != "suspend"):
        raise AotPlanError(f"vibeflow.io receive node '{node.id}' requires zero inputs, one output, and suspend completion",
                           code="VF_IO_CONTRACT")
    if node.io_operation == "send" and (len(node.requires) != 1 or node.requires[0].cardinality != "exactly_one"
                                       or node.provides or node.completion != "immediate"):
        raise AotPlanError(f"vibeflow.io send node '{node.id}' requires one exactly_one input, zero outputs, and immediate completion",
                           code="VF_IO_CONTRACT")
