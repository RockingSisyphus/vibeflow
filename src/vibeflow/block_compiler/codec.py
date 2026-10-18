"""Read the current portable plan format without importing a Target."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Mapping

from vibeflow.block_compiler import model as m


def _record(value, constructor, **updates):
    if not isinstance(value, Mapping):
        raise m.PortablePlanError(f"{constructor.__name__} must be an object")
    return constructor(**{**value, **updates})


def _lock(value):
    return None if value is None else _record(value, m.ExecutionLockPlan)


def _condition(value):
    return None if value is None else _record(value, m.ConditionPlan)


def _output(value):
    data = dict(value)
    data["as_key"] = data.pop("as")
    return m.PipelineOutputSpec(**data)


def _loop(value):
    if value is None:
        return None
    return m.LoopPlan(
        body_type_key=value["body"], max_iterations=value["max_iterations"],
        stop_after=value.get("stop_after"), stop_when=_condition(value.get("stop_when")),
        carry=tuple(m.LoopCarryPlan(v["from"], v["as"], v["update"]) for v in value["carry"]),
        collect=tuple(m.LoopCollectPlan(v["from"], v["as"], v["mode"]) for v in value["collect"]),
        outputs=tuple(m.LoopOutputPlan(v["from"], v["as"]) for v in value["outputs"]),
    )


def _node(value):
    return _record(value, m.NodeCallPlan,
        implementation=_record(value["implementation"], m.SourceRef),
        requires=tuple(_record(v, m.DataRequirementPlan) for v in value["requires"]),
        provides=tuple(_record(v, m.DataProviderPlan) for v in value["provides"]),
        exports=tuple(_record(v, m.DataProviderPlan) for v in value["exports"]),
        params=m.freeze_json_object(value["params"]),
        config_overrides=m.freeze_json_object(value["config_overrides"]),
        execution_lock=_lock(value["execution_lock"]),
    )


def _block(value):
    return _record(value, m.BlockPlan,
        path=tuple(value["path"]), source=_record(value["source"], m.SourceRef),
        inputs=tuple(_record(v, m.PipelineInputSpec) for v in value["inputs"]),
        outputs=tuple(_output(v) for v in value["outputs"]),
        nodes=tuple(_node(v) for v in value["nodes"]),
        routes=tuple(_record(v, m.RoutePlan, condition=_condition(v["condition"])) for v in value["routes"]),
        order=tuple(value["order"]), entries=tuple(value["entries"]), exits=tuple(value["exits"]),
        loop=_loop(value["loop"]), execution_lock=_lock(value["execution_lock"]))


def workflow_plan_from_dict(value: Mapping[str, object]) -> m.WorkflowPlan:
    """Restore exactly the current ABI; older plans must be rebuilt."""
    try:
        if value.get("abi_version") != m.WORKFLOW_ABI_VERSION:
            raise m.PortablePlanError(f"workflow ABI must be '{m.WORKFLOW_ABI_VERSION}'")
        plan = _record(value, m.WorkflowPlan,
            source=_record(value["source"], m.SourceRef),
            inputs=tuple(_record(v, m.PipelineInputSpec) for v in value["inputs"]),
            outputs=tuple(_output(v) for v in value["outputs"]),
            blocks=tuple(_block(v) for v in value["blocks"]),
            execution_lock=_lock(value["execution_lock"]))
        blocks = {block.id: block for block in plan.blocks}
        if len(blocks) != len(plan.blocks) or plan.entry_block not in blocks:
            raise m.PortablePlanError("workflow must name distinct blocks and an existing entry block")
        for block in plan.blocks:
            ids = {node.id for node in block.nodes}
            if len(ids) != len(block.nodes) or len(block.order) != len(ids) or set(block.order) != ids:
                raise m.PortablePlanError(f"block '{block.id}' order must name every node once")
            if any(route.source not in ids or route.target not in ids for route in block.routes):
                raise m.PortablePlanError(f"block '{block.id}' route names an unknown node")
            if any(node.child_block and node.child_block not in blocks for node in block.nodes):
                raise m.PortablePlanError(f"block '{block.id}' names an unknown child block")
        return plan
    except (KeyError, TypeError, AttributeError) as exc:
        raise m.PortablePlanError(f"invalid workflow plan: {exc}") from exc


def workflow_plan_from_json(value: str) -> m.WorkflowPlan:
    """Read a JSON plan using the same pure-data decoder."""
    try:
        return workflow_plan_from_dict(json.loads(value))
    except json.JSONDecodeError as exc:
        raise m.PortablePlanError(f"invalid workflow JSON: {exc}") from exc


def workflow_subplan(plan: m.WorkflowPlan, entry_block: str) -> m.WorkflowPlan:
    """Expose an existing subtree as a workflow; no structural inference runs."""
    if entry_block == plan.entry_block:
        return plan
    from vibeflow.block_compiler.compiler import _block_id
    root = plan.block(entry_block)
    prefix = root.path
    included = set()
    def collect(key):
        if key in included:
            return
        included.add(key)
        for call in plan.block(key).nodes:
            if call.child_block:
                collect(call.child_block)
    collect(entry_block)
    ids = {block.id:_block_id(block.path[len(prefix):]) for block in plan.blocks if block.id in included}
    blocks = []
    for block in plan.blocks:
        if block.id not in included:
            continue
        calls = tuple(replace(call, child_block=ids[call.child_block] if call.child_block else '') for call in block.nodes)
        lock = replace(block.execution_lock,scope='root') if block.id == entry_block and block.execution_lock else block.execution_lock
        blocks.append(replace(block,id=ids[block.id],path=block.path[len(prefix):],nodes=calls,
            kind='workflow' if block.id == entry_block else block.kind,
            loop=None if block.id == entry_block else block.loop,execution_lock=lock))
    entry = next(block for block in blocks if block.id == ids[entry_block])
    return replace(plan,entry_block=entry.id,blocks=tuple(blocks),source=entry.source,
        inputs=entry.inputs,outputs=entry.outputs,max_steps=entry.max_steps,
        execution_lock=entry.execution_lock,contains_global_state=entry.contains_global_state)


def map_plan_sources(plan: m.WorkflowPlan, transform) -> m.WorkflowPlan:
    """Map locator records without touching business parameters or topology."""
    return replace(plan, source=transform(plan.source), blocks=tuple(
        replace(block,source=transform(block.source),nodes=tuple(
            replace(call,implementation=transform(call.implementation)) for call in block.nodes))
        for block in plan.blocks))
