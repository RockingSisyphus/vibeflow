"""Read-only JavaScript emission views over the canonical workflow IR."""

from __future__ import annotations

from typing import Any, Mapping

from vibeflow.block_compiler.model import BlockPlan, NodeCallPlan, WorkflowPlan
from vibeflow.targets.javascript.frontend.bindings import JavascriptBindingPlan, JavascriptCallBinding
from vibeflow.targets.javascript.frontend.emission_protocol import (
    BoundCapabilityOperationView,
    BoundCapabilityView,
    BoundImplementationView,
    BoundInputView,
    BoundLoopView,
    BoundOutputView,
    BoundProviderView,
    BoundRequirementView,
    BoundRouteView,
    EmissionNode,
    EmissionWorkflow,
    copy_json,
    implementation_override,
    module_specifier,
    restore_properties_order,
    schema_order_path_key,
)
from vibeflow.targets.javascript.frontend.model_types import AotPlanError


class _BoundContext:
    def __init__(
        self,
        plan: WorkflowPlan,
        bindings: JavascriptBindingPlan,
    ) -> None:
        self.plan = plan
        self.bindings = bindings
        self.blocks = {block.id: block for block in plan.blocks}
        self.calls = {item.path: item for item in bindings.calls}
        self.orders = {
            (item.source, item.path): item
            for item in bindings.schema_member_orders
        }
        self.schemas = {
            str(key): self.ordered_schema(("schemas", str(key)), value)
            for key, value in bindings.schemas.to_value().items()
        }
        self.capabilities = _capability_views(
            bindings.capabilities.to_value()
        )
        self._validate()

    def _validate(self) -> None:
        if self.plan.workflow_id != self.bindings.workflow_id:
            raise AotPlanError(
                "JavaScript binding workflow_id does not match WorkflowPlan"
            )
        if len(self.blocks) != len(self.plan.blocks):
            raise AotPlanError("WorkflowPlan contains duplicate block ids")
        if self.plan.entry_block not in self.blocks:
            raise AotPlanError("WorkflowPlan entry block does not exist")
        expected: dict[tuple[str, ...], NodeCallPlan] = {}
        for block in self.plan.blocks:
            for node in block.nodes:
                path = (*block.path, node.id)
                if path in expected:
                    raise AotPlanError(
                        f"WorkflowPlan contains duplicate call path "
                        f"'{'.'.join(path)}'"
                    )
                expected[path] = node
                binding = self.calls.get(path)
                if binding is None:
                    raise AotPlanError(
                        f"JavaScript binding is missing call '{'.'.join(path)}'"
                    )
                self._validate_call(path, node, binding)
                if node.child_block and node.child_block not in self.blocks:
                    raise AotPlanError(
                        f"child block '{node.child_block}' does not exist"
                    )
        extra = sorted(set(self.calls) - set(expected))
        if extra:
            raise AotPlanError(
                "JavaScript bindings contain unknown calls: "
                f"{['.'.join(path) for path in extra]}"
            )

    def _validate_call(
        self,
        path: tuple[str, ...],
        node: NodeCallPlan,
        binding: JavascriptCallBinding,
    ) -> None:
        location = ".".join(path)
        if binding.type_key != node.type_used:
            raise AotPlanError(
                f"JavaScript binding type mismatch at '{location}'"
            )
        if binding.implementation != node.implementation:
            raise AotPlanError(
                f"JavaScript binding source mismatch at '{location}'"
            )
        if binding.params.to_value() != node.params.to_value():
            raise AotPlanError(
                f"JavaScript binding params mismatch at '{location}'"
            )
        if binding.schedule != node.schedule:
            raise AotPlanError(
                f"JavaScript binding schedule mismatch at '{location}'"
            )
        if self.plan.entry_mode != "sync":
            return
        if binding.completion == "suspend":
            raise AotPlanError(
                f"sync workflow contains asynchronous call '{location}'",
                code="VF_ENTRY_MODE_SUSPEND_IN_SYNC",
            )
        if binding.schedule != "inline":
            raise AotPlanError(
                f"sync workflow contains asynchronous call '{location}'",
                code="VF_ENTRY_MODE_TASK_IN_SYNC",
            )

    def ordered_schema(
        self,
        source: tuple[str, ...],
        value: object,
    ) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise AotPlanError(
                f"JavaScript schema '{'.'.join(source)}' must be an object"
            )
        copied = copy_json(value)
        assert isinstance(copied, dict)
        records = [
            record
            for (record_source, _path), record in self.orders.items()
            if record_source == source
        ]
        for record in sorted(records, key=schema_order_path_key):
            restore_properties_order(copied, record)
        return copied


class BoundNodeView:
    def __init__(
        self,
        context: _BoundContext,
        block: BlockPlan,
        source: NodeCallPlan,
        binding: JavascriptCallBinding,
        subplan: "BoundWorkflowView | None",
    ) -> None:
        self._block = block
        self._source = source
        self._binding = binding
        self.subplan = subplan
        self.loop = BoundLoopView.from_plan(
            context.blocks[source.child_block].loop
            if source.is_loop and source.child_block
            else None
        )
        self.requires = tuple(
            BoundRequirementView(item) for item in source.requires
        )
        self.provides = tuple(
            BoundProviderView(item) for item in source.provides
        )
        self.capabilities = tuple(binding.capabilities)
        self.params = binding.params.to_value()
        self.params_schema = _ordered_contract_schemas(
            context, binding, "params_schema"
        )
        self.implementation = (
            None
            if source.is_nodeset or source.is_loop or source.io_operation
            else BoundImplementationView(binding)
        )

    @property
    def path(self) -> tuple[str, ...]:
        return (*self._block.path, self._source.id)
    @property
    def id(self) -> str:
        return self._source.id
    @property
    def type_used(self) -> str:
        return self._source.type_used
    @property
    def flow_kind(self) -> str:
        return self._source.flow_kind
    @property
    def join_policy(self) -> str:
        return self._source.join_policy
    @property
    def async_mode(self) -> str:
        return self._source.async_mode
    @property
    def result_key(self) -> str:
        return self._source.result_key
    @property
    def is_terminal(self) -> bool:
        return self._source.is_terminal
    @property
    def is_nodeset(self) -> bool:
        return self._source.is_nodeset
    @property
    def is_loop(self) -> bool:
        return self._source.is_loop
    @property
    def completion(self) -> str:
        return self._binding.completion
    @property
    def schedule(self) -> str:
        return self._binding.schedule
    @property
    def executor(self) -> str:
        return self._binding.executor
    @property
    def io_operation(self) -> str:
        return self._source.io_operation
    @property
    def io_port(self) -> str:
        return self._source.io_port

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = dict(
            id=self.id,
            type_used=self.type_used,
            requires=[item.to_dict() for item in self.requires],
            provides=[item.to_dict() for item in self.provides],
            params=dict(self.params),
            flow_kind=self.flow_kind,
            join_policy=self.join_policy,
            async_mode=self.async_mode,
            result_key=self.result_key,
            is_terminal=self.is_terminal,
            is_nodeset=self.is_nodeset,
            is_loop=self.is_loop,
            capabilities=[item.to_dict() for item in self.capabilities],
            loop=self.loop.to_dict(),
            completion=self.completion,
            schedule=self.schedule,
            executor=self.executor,
            io_operation=self.io_operation,
            io_port=self.io_port,
        )
        if self.implementation is not None:
            payload["implementation"] = self.implementation.to_dict()
        if self.subplan is not None:
            payload["subplan"] = self.subplan.to_dict()
        return payload


class BoundWorkflowView:
    """WorkflowSpec-shaped projection whose authority remains canonical IR."""

    def __init__(
        self,
        context: _BoundContext,
        block: BlockPlan,
        workflow_id: str,
        *,
        active: tuple[str, ...],
    ) -> None:
        if block.id in active:
            raise AotPlanError(
                f"recursive block reference cannot target JS: {block.id}"
            )
        self.abi_version = context.plan.abi_version
        self.workflow_id = workflow_id
        self.entry_mode = context.plan.entry_mode
        self.max_steps = block.max_steps
        self.schemas = context.schemas
        self.capabilities = context.capabilities
        input_specs = (
            context.plan.inputs
            if block.id == context.plan.entry_block
            else block.inputs
        )
        output_specs = (
            context.plan.outputs
            if block.id == context.plan.entry_block
            else block.outputs
        )
        self.inputs = tuple(
            BoundInputView(item, self.schemas.get(item.type))
            for item in input_specs
        )
        self.outputs = tuple(
            BoundOutputView(item, self.schemas.get(item.type))
            for item in output_specs
        )
        self.routes = tuple(BoundRouteView(item) for item in block.routes)
        self.order = tuple(block.order)
        self.entries = tuple(block.entries)
        child_active = (*active, block.id)
        nodes: list[BoundNodeView] = []
        for node in block.nodes:
            path = (*block.path, node.id)
            subplan = (
                BoundWorkflowView(
                    context,
                    context.blocks[node.child_block],
                    f"{workflow_id}.{node.id}",
                    active=child_active,
                )
                if node.child_block
                else None
            )
            nodes.append(
                BoundNodeView(
                    context,
                    block,
                    node,
                    context.calls[path],
                    subplan,
                )
            )
        self.nodes = tuple(nodes)

    @classmethod
    def from_plan(
        cls,
        plan: WorkflowPlan,
        bindings: JavascriptBindingPlan,
    ) -> "BoundWorkflowView":
        if not isinstance(plan, WorkflowPlan):
            raise TypeError("plan must be a WorkflowPlan")
        if not isinstance(bindings, JavascriptBindingPlan):
            raise TypeError("bindings must be a JavascriptBindingPlan")
        context = _BoundContext(plan, bindings)
        return cls(
            context,
            context.blocks[plan.entry_block],
            plan.workflow_id,
            active=(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "abi_version": self.abi_version,
            "workflow_id": self.workflow_id,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "nodes": [item.to_dict() for item in self.nodes],
            "routes": [item.to_dict() for item in self.routes],
            "order": list(self.order),
            "entries": list(self.entries),
            "max_steps": self.max_steps,
            "schemas": {
                key: dict(value)
                for key, value in sorted(self.schemas.items())
            },
            "capabilities": [item.to_dict() for item in self.capabilities],
            "entry_mode": self.entry_mode,
            "tasks": [
                {
                    "id": f"task:{node.id}",
                    "node_id": node.id,
                    "schedule": node.schedule,
                    "executor": node.executor,
                    **(
                        {"result_key": node.result_key}
                        if node.result_key
                        else {}
                    ),
                }
                for node in self.nodes
                if node.schedule != "inline"
            ],
        }


def bound_workflow_view(
    plan: WorkflowPlan,
    bindings: JavascriptBindingPlan,
) -> BoundWorkflowView:
    return BoundWorkflowView.from_plan(plan, bindings)


def legacy_emission_payload(workflow: EmissionWorkflow) -> dict[str, Any]:
    """Return the ABI-v2 hash projection without creating WorkflowSpec."""

    return workflow.to_dict()


def _capability_views(
    values: Mapping[str, object],
) -> tuple[BoundCapabilityView, ...]:
    result: list[BoundCapabilityView] = []
    for capability_id in sorted(values):
        raw = values[capability_id]
        if not isinstance(raw, Mapping):
            raise AotPlanError(
                f"capability '{capability_id}' must be an object"
            )
        operations_raw = raw.get("operations", {})
        if not isinstance(operations_raw, Mapping):
            raise AotPlanError(
                f"capability '{capability_id}'.operations must be an object"
            )
        operations: dict[str, BoundCapabilityOperationView] = {}
        for name in sorted(operations_raw):
            operation = operations_raw[name]
            if not isinstance(operation, Mapping):
                raise AotPlanError(
                    f"capability '{capability_id}.{name}' must be an object"
                )
            operations[str(name)] = BoundCapabilityOperationView(
                input_type=str(operation.get("input_type", "") or ""),
                output_type=str(operation.get("output_type", "") or ""),
                completion=str(
                    operation.get("completion", "immediate") or "immediate"
                ),
            )
        result.append(BoundCapabilityView(str(capability_id), operations))
    return tuple(result)


def _ordered_contract_schemas(
    context: _BoundContext,
    binding: JavascriptCallBinding,
    contract_name: str,
) -> Mapping[str, Mapping[str, Any]]:
    raw = getattr(binding, contract_name).to_value()
    return {
        str(key): context.ordered_schema(
            ("calls", *binding.path, contract_name, str(key)),
            value,
        )
        for key, value in raw.items()
    }


__all__ = [
    "BoundNodeView",
    "BoundWorkflowView",
    "EmissionNode",
    "EmissionWorkflow",
    "bound_workflow_view",
    "implementation_override",
    "legacy_emission_payload",
    "module_specifier",
]
