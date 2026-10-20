"""Author canonical AOT plans and target bindings for focused runtime cases.

These in-memory descriptions are test data, not a workflow decoder. Production
builders receive only the canonical dataclasses returned here; no legacy public
model, resource discovery, or validation implementation is used by this helper.
"""
from pathlib import Path

from vibeflow.block_compiler.model import (
    WORKFLOW_ABI_VERSION, BlockPlan, ConditionPlan, DataProviderPlan,
    DataRequirementPlan, ExecutionLockPlan, LoopCarryPlan, LoopCollectPlan,
    LoopOutputPlan, LoopPlan, NodeCallPlan, PipelineInputSpec, PipelineOutputSpec,
    SourceRef, WorkflowPlan, freeze_json_object,
)
from vibeflow.targets.javascript.build import BuildRequest
from vibeflow.targets.javascript.frontend.bindings import build_javascript_binding_plan
from vibeflow.targets.javascript.frontend.emission_view import bound_workflow_view
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module


def plan_fixture(description, *, project_root=None, import_policy=None, host_extensions=()):
    """Construct native plan dataclasses and a JS sidecar from authored cases."""
    blocks = []
    metadata, required_capabilities = {}, {}
    schemas = dict(description.get("schemas", {}))

    def source(value, *, fallback):
        item = value or {"kind": "native", "ref": fallback, "export": ""}
        ref = str(item["ref"])
        if project_root is not None and item.get("kind", "file") == "file":
            ref = str((Path(project_root) / ref).resolve())
        return SourceRef(item.get("kind", "file"), ref, item.get("export", "run"))

    def inputs(items):
        result = []
        for item in items:
            if "schema" in item:
                schemas[item["type"]] = item["schema"]
            result.append(PipelineInputSpec(item["key"], item["type"], item["required"]))
        return tuple(result)

    def outputs(items):
        result = []
        for item in items:
            if "schema" in item:
                schemas[item["type"]] = item["schema"]
            result.append(PipelineOutputSpec(item["type"], item["cardinality"], item["as"]))
        return tuple(result)

    def condition(item):
        return ConditionPlan(item["key"], item["operator"], item["literal"]) if item else None

    def loop(item):
        if not item:
            return None
        return LoopPlan(
            body_type_key=item.get("body", "fixture.body"), max_iterations=item.get("max_iterations", 1000),
            stop_after=item.get("stop_after") or None, stop_when=condition(item.get("stop_when")),
            carry=tuple(LoopCarryPlan(value["from"], value["as"], value["update"]) for value in item.get("carry", ())),
            collect=tuple(LoopCollectPlan(value["from"], value["as"], value.get("mode", "all")) for value in item.get("collect", ())),
            outputs=tuple(LoopOutputPlan(value["from"], value["as"]) for value in item.get("outputs", ())),
        )

    def block(item, block_id, path, kind, loop_description=None):
        nodes = []
        for raw in item.get("nodes", ()):
            child_id = raw.get("child_block", "")
            if "subplan" in raw:
                child_id = "block:/" + "/".join((*path, raw["id"]))
                block(raw["subplan"], child_id, (*path, raw["id"]),
                      "loop" if raw.get("is_loop") else "nodeset", raw.get("loop"))
            implementation = raw.get("implementation")
            completion = raw.get("completion", (implementation or {}).get("completion", "immediate"))
            schedule = raw.get("schedule", "inline")
            executor = raw.get("executor", "event_loop" if completion == "suspend" or schedule != "inline" else "current")
            metadata[raw["type_used"]] = {"completion": completion,
                "language": (implementation or {}).get("language", "javascript"),
                "params_schema": raw.get("params_schema", {})}
            required_capabilities[raw["type_used"]] = raw.get("capabilities", ())
            nodes.append(NodeCallPlan(
                id=raw["id"], type_used=raw["type_used"], implementation=source(implementation, fallback=raw["type_used"]),
                requires=tuple(DataRequirementPlan(value["type"], value.get("cardinality", "exactly_one")) for value in raw.get("requires", ())),
                provides=tuple(DataProviderPlan(value["key"], value["type"]) for value in raw.get("provides", ())),
                params=freeze_json_object(raw.get("params", {})), config_overrides=freeze_json_object({}),
                flow_kind=raw.get("flow_kind", ""), join_policy=raw.get("join_policy", "safe_any"),
                max_concurrency=raw.get("max_concurrency", 8),
                status=raw.get("status", "implemented"), planned_behavior=raw.get("planned_behavior", ""),
                is_terminal=raw.get("is_terminal", False), is_nodeset=raw.get("is_nodeset", False),
                is_loop=raw.get("is_loop", False), nodeset_type_key="", child_block=child_id, exports=(),
                completion=completion, schedule=schedule, executor=executor,
                effect_scope=raw.get("effect_scope", "none"),
            ))
        from vibeflow.block_compiler.model import RoutePlan
        routes = tuple(RoutePlan(value["source"], value["target"], condition(value.get("condition")),
                                 value.get("schedule", True), value.get("transfer", True)) for value in item.get("routes", ()))
        incoming = {value.target for value in routes if value.schedule}
        entries = tuple(item.get("entries", tuple(node.id for node in nodes if node.is_terminal and node.id not in incoming)))
        blocks.append(BlockPlan(
            id=block_id, kind=kind, path=path, source=SourceRef("fixture", block_id),
            inputs=inputs(item.get("inputs", ())), outputs=outputs(item.get("outputs", ())),
            nodes=tuple(nodes), routes=routes, order=tuple(item.get("order", tuple(node.id for node in nodes))),
            entries=entries, exits=(), max_steps=item.get("max_steps", 1000), loop=loop(loop_description or item.get("loop")),
        ))

    if "blocks" in description:
        for item in description["blocks"]:
            path = tuple(item.get("path", tuple(part for part in item["id"].removeprefix("block:/").split("/") if part)))
            block(item, item["id"], path, item["kind"])
    else:
        block(description, "block:/", (), "workflow")
    plan = WorkflowPlan(
        abi_version=description.get("abi_version", WORKFLOW_ABI_VERSION), workflow_id=description.get("workflow_id", "fixture.workflow"),
        source=SourceRef("fixture", "workflow"), entry_block=description.get("entry_block", "block:/"),
        inputs=inputs(description.get("inputs", ())), outputs=outputs(description.get("outputs", ())),
        blocks=tuple(blocks), max_steps=description.get("max_steps", 1000), entry_mode=description.get("entry_mode", "sync"),
        execution_lock=ExecutionLockPlan(description["execution_lock"]["key"], "root") if description.get("execution_lock") else None,
        contains_global_state=description.get("contains_global_state", False),
    )
    capability_values = description.get("capabilities", ())
    capabilities = capability_values if isinstance(capability_values, dict) else {value["id"]: {"operations": value["operations"]} for value in capability_values}
    hosts = tuple(dict(item, module=str((Path(project_root) / item["module"]).resolve())) if project_root else item for item in host_extensions)
    bindings = build_javascript_binding_plan(plan, implementations=metadata, capabilities_by_type=required_capabilities,
        schemas=schemas, capabilities=capabilities, import_policy=import_policy or {}, host_extensions=hosts)
    return plan, bindings


def emit_fixture(description, *, host_extensions=()):
    plan, bindings = plan_fixture(description, host_extensions=host_extensions)
    return emit_workflow_module(plan, javascript_bindings=bindings)


def view_fixture(description):
    plan, bindings = plan_fixture(description)
    return bound_workflow_view(plan, bindings)


def fixture_build_request(*, plan, import_policy=None, host_extensions=(), **kwargs):
    canonical, bindings = plan_fixture(plan, project_root=kwargs["project_root"],
        import_policy=import_policy, host_extensions=host_extensions)
    return BuildRequest(plan=canonical, javascript_bindings=bindings, **kwargs)
