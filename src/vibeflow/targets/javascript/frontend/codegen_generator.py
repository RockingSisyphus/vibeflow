from __future__ import annotations

from typing import Any, Mapping

from vibeflow.targets.javascript.frontend.emission_protocol import EmissionWorkflow
from vibeflow.targets.javascript.frontend.model import AotPlanError
from vibeflow.targets.javascript.frontend.codegen_common import (
    WorkflowCode,
    constant,
)
from vibeflow.targets.javascript.frontend.codegen_nodes import NodeCodegenMixin
from vibeflow.targets.javascript.frontend.codegen_scheduler import SchedulerCodegenMixin


class StaticWorkflowEmitter(
    NodeCodegenMixin,
    SchedulerCodegenMixin,
):
    """Compile a normalized workflow graph into workflow-specific JavaScript.

    The emitted scheduler has one ``switch`` case per node and hard-coded route
    activation / join expressions. Runtime helpers operate only on contracts
    and call-local state; they never receive a graph to interpret.
    """

    def __init__(
        self,
        *,
        workflow: EmissionWorkflow,
        payload: Mapping[str, Any],
        binding_expressions: Mapping[str, str],
    ) -> None:
        self.workflow = workflow
        self.payload = payload
        self.binding_expressions = binding_expressions
        self._next_index = 0
        self._codes: list[WorkflowCode] = []

    def emit(self) -> str:
        root = self._register(self.workflow, self.payload)
        constants: list[str] = []
        functions: list[str] = []
        for code in self._codes:
            constants.extend(self._emit_constants(code))
        descriptors, requirements, schemas = self._capability_catalogs()
        constants.extend(
            [
                constant("__vfCapabilityDescriptors", descriptors),
                constant("__vfCapabilityRequirements", requirements),
                constant("__vfSchemaCatalog", schemas),
            ]
        )
        for code in reversed(self._codes):
            functions.extend(self._emit_functions(code))
        workflow_factory = (
            "createStaticWorkflowSync"
            if self.workflow.entry_mode == "sync"
            else "createStaticWorkflowAsync"
        )
        functions.append(
            f"const __vfInvokeWorkflow = {workflow_factory}(\n"
            f"  {root.metadata_name},\n"
            "  __vfCapabilityDescriptors,\n"
            "  __vfCapabilityRequirements,\n"
            "  __vfSchemaCatalog,\n"
            f"  {root.function_name},\n"
            ");"
        )
        return "\n\n".join((*constants, *functions))

    def _register(
        self,
        workflow: EmissionWorkflow,
        payload: Mapping[str, Any],
    ) -> WorkflowCode:
        index = self._next_index
        self._next_index += 1
        node_names = {
            node.id: f"__vf_w{index}_n{node_index}"
            for node_index, node in enumerate(workflow.nodes)
        }
        activate_names = {
            node.id: f"__vf_activate_w{index}_n{node_index}"
            for node_index, node in enumerate(workflow.nodes)
        }
        execute_names = {
            node.id: f"__vf_execute_w{index}_n{node_index}"
            for node_index, node in enumerate(workflow.nodes)
        }
        children: dict[str, WorkflowCode] = {}
        payload_nodes = payload.get("nodes")
        if not isinstance(payload_nodes, list):
            raise ValueError("serialized portable workflow must contain nodes")
        for node, node_payload in zip(
            workflow.nodes,
            payload_nodes,
            strict=True,
        ):
            if node.subplan is None:
                continue
            if not isinstance(node_payload, Mapping):
                raise ValueError("serialized portable node must be an object")
            child_payload = node_payload.get("subplan")
            if not isinstance(child_payload, Mapping):
                raise ValueError(f"composite node '{node.id}' lost its subplan")
            children[node.id] = self._register(
                node.subplan,
                child_payload,
            )
        code = WorkflowCode(
            workflow=workflow,
            payload=payload,
            index=index,
            metadata_name=f"__vf_workflow_{index}_metadata",
            function_name=f"__vf_workflow_{index}_execute",
            node_names=node_names,
            activate_names=activate_names,
            execute_names=execute_names,
            children=children,
        )
        self._codes.append(code)
        return code

    def _emit_constants(self, code: WorkflowCode) -> list[str]:
        workflow = code.workflow
        metadata = {
            "abi_version": workflow.abi_version,
            "workflow_id": workflow.workflow_id,
            "inputs": [item.to_dict() for item in workflow.inputs],
            "outputs": [item.to_dict() for item in workflow.outputs],
            "max_steps": workflow.max_steps,
            "entry_mode": workflow.entry_mode,
            "schemas": {
                key: dict(value)
                for key, value in sorted(workflow.schemas.items())
            },
        }
        result = [constant(code.metadata_name, metadata)]
        payload_nodes = code.payload.get("nodes")
        assert isinstance(payload_nodes, list)
        for node, node_payload in zip(
            workflow.nodes,
            payload_nodes,
            strict=True,
        ):
            assert isinstance(node_payload, Mapping)
            node_metadata: dict[str, Any] = {
                "id": node.id,
                "type_used": node.type_used,
                "requires": [item.to_dict() for item in node.requires],
                "provides": [item.to_dict() for item in node.provides],
                "params": dict(node.params),
                "capabilities": [item.to_dict() for item in node.capabilities],
                "completion": node.completion,
                "schedule": node.schedule,
                "executor": node.executor,
            }
            output_schemas = node_payload.get("output_schemas")
            if isinstance(output_schemas, Mapping) and output_schemas:
                node_metadata["output_schemas"] = {
                    str(key): dict(value)
                    for key, value in output_schemas.items()
                    if isinstance(value, Mapping)
                }
            result.append(
                constant(code.node_names[node.id], node_metadata)
            )
        return result

    def _emit_functions(self, code: WorkflowCode) -> list[str]:
        result: list[str] = []
        payload_nodes = code.payload.get("nodes")
        assert isinstance(payload_nodes, list)
        for node, node_payload in zip(
            code.workflow.nodes,
            payload_nodes,
            strict=True,
        ):
            assert isinstance(node_payload, Mapping)
            result.append(self._emit_activate(code, node))
            result.append(self._emit_execute(code, node, node_payload))
        result.append(self._emit_scheduler(code))
        return result

    def _capability_catalogs(
        self,
    ) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, Any]]:
        descriptors: dict[str, Any] = {}
        requirements: dict[str, set[str]] = {}
        schemas: dict[str, Any] = {}

        def visit(workflow: EmissionWorkflow) -> None:
            for key, schema in workflow.schemas.items():
                schemas.setdefault(key, dict(schema))
            for descriptor in workflow.capabilities:
                payload = descriptor.to_dict()
                previous = descriptors.get(descriptor.id)
                if previous is not None and previous != payload:
                    raise AotPlanError(
                        f"capability '{descriptor.id}' has conflicting descriptors",
                        code="VF_CAPABILITY_CONFLICT",
                    )
                descriptors[descriptor.id] = payload
            descriptor_by_id = {
                item.id: item for item in workflow.capabilities
            }
            for node in workflow.nodes:
                for requirement in node.capabilities:
                    descriptor = descriptor_by_id.get(requirement.id)
                    operations = (
                        requirement.operations
                        or tuple(descriptor.operations if descriptor else ())
                    )
                    requirements.setdefault(
                        requirement.id,
                        set(),
                    ).update(operations)
                if node.subplan is not None:
                    visit(node.subplan)

        visit(self.workflow)
        return (
            {key: descriptors[key] for key in sorted(descriptors)},
            {
                key: sorted(requirements[key])
                for key in sorted(requirements)
            },
            {key: schemas[key] for key in sorted(schemas)},
        )


__all__ = ["StaticWorkflowEmitter"]
