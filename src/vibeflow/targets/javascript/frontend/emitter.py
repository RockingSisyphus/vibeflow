from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from vibeflow.block_compiler.model import WorkflowPlan
from vibeflow.targets.javascript.frontend.bindings import JavascriptBindingPlan
from vibeflow.targets.javascript.frontend.declarations import (
    declarations,
    schema_to_typescript,
)
from vibeflow.targets.javascript.frontend.emission_protocol import (
    EmissionNode,
    EmissionWorkflow,
)
from vibeflow.targets.javascript.frontend.emission_view import (
    bound_workflow_view,
    bound_entry_view,
    emission_payload,
    module_specifier,
)
from vibeflow.targets.javascript.frontend.errors import AotPlanError

from vibeflow.targets.javascript.frontend.schema import (
    JavascriptJsonValueError,
    validate_javascript_json_value,
)
from vibeflow.targets.javascript.frontend.codegen_generator import StaticWorkflowEmitter
from vibeflow.targets.javascript.frontend.templates import RUNTIME_SOURCE


@dataclass(frozen=True)
class EmittedWorkflow:
    source: str
    declarations: str
    plan_sha256: str
    implementation_modules: tuple[str, ...]
    implementation_bindings: tuple[tuple[str, str], ...]

    runtime_plugins: tuple[str, ...] = ()


def emit_workflow_module(
    plan: WorkflowPlan,
    *,
    javascript_bindings: JavascriptBindingPlan,
) -> EmittedWorkflow:
    """Emit a side-effect-free ESM module from a canonical plan and bindings."""
    workflow = bound_workflow_view(plan, javascript_bindings)

    runtime_plugins = tuple(
        _plugin_binding_value(item) for item in javascript_bindings.runtime_plugins
    )
    serializable = emission_payload(workflow)
    serializable["named_entries"] = [item.to_dict() for item in plan.named_entries]
    serializable["default_entry"] = plan.default_entry
    bindings: dict[tuple[str, str], str] = {}
    modules: list[str] = []
    _bind_implementations(
        workflow,
        serializable,
        bindings=bindings,
        modules=modules,
    )
    try:
        validate_javascript_json_value(serializable)
    except JavascriptJsonValueError as exc:
        raise AotPlanError(str(exc), code=exc.code) from exc

    import_lines, binding_expressions = _implementation_imports(
        bindings,
        modules,
    )

    plugin_imports, plugin_factories = _runtime_plugin_imports(
        runtime_plugins,
    )
    import_lines.extend(plugin_imports)
    canonical_plan = json.dumps(
        serializable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    static_source = StaticWorkflowEmitter(
        workflow=workflow,
        payload=serializable,
        binding_expressions=binding_expressions,
        named_workflows={item.name: bound_entry_view(workflow, item) for item in plan.named_entries},
        default_entry=plan.default_entry,
    ).emit()
    plugin_descriptors = [
        {
            "id": str(plugin.get("id", "")),
            "target": str(plugin.get("target", "")),
            "config": dict(plugin.get("config", {})),
            "completion": str(plugin.get("completion", "immediate")),
            "factory_index": index,
        }
        for index, plugin in enumerate(runtime_plugins)
    ]
    plugin_source = (
        "const __vfRuntimePluginDescriptors = "
        + json.dumps(
            plugin_descriptors,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + ";\nconst __vfRuntimePluginFactories = ["
        + ", ".join(plugin_factories)
        + "];"
    )
    if workflow.entry_mode == "sync":
        public_entry = (
            "export function runWorkflow(inputs, options) {\n"
            "  return __vfObserveSync(__vfInvokeWorkflow, inputs, options);\n"
            "}"
        )
    else:
        public_entry = (
            "export async function runWorkflowAsync(inputs, options) {\n"
            "  return __vfObserveAsync(__vfInvokeWorkflow, inputs, options);\n"
            "}"
        )
    source_parts = [
        "\n".join(import_lines),
        RUNTIME_SOURCE,
        plugin_source,
        static_source,
        public_entry,
        "",
    ]
    return EmittedWorkflow(
        source="\n\n".join(part for part in source_parts if part != ""),
        declarations=declarations(
            workflow,

        ),
        plan_sha256=hashlib.sha256(
            canonical_plan.encode("utf-8")
        ).hexdigest(),
        implementation_modules=tuple(modules),
        implementation_bindings=tuple(bindings),

        runtime_plugins=tuple(
            str(item.get("id", "")) for item in runtime_plugins
        ),
    )


def _bind_implementations(
    workflow: EmissionWorkflow,
    serializable: dict[str, Any],
    *,
    bindings: dict[tuple[str, str], str],
    modules: list[str],
) -> None:
    def bind(
        node: EmissionNode,
        node_payload: dict[str, Any],
        path: tuple[str, ...],
    ) -> None:
        if node.implementation is not None:
            implementation = node.implementation
            module = module_specifier(implementation.module)
            binding_key = (module, implementation.export)
            binding = bindings.get(binding_key)
            if binding is None:
                binding = f"impl:{len(bindings)}"
                bindings[binding_key] = binding
                if module not in modules:
                    modules.append(module)
            node_payload["implementation_id"] = binding
            node_payload["implementation"] = implementation.to_dict()
        if node.subplan is None:
            return
        child_payload = node_payload.get("subplan")
        if not isinstance(child_payload, dict):
            raise ValueError(
                f"portable node "
                f"'{'.'.join((*path, node.id))}' lost its subplan"
            )
        bind_workflow(node.subplan, child_payload, (*path, node.id))

    def bind_workflow(
        child_workflow: EmissionWorkflow,
        payload: dict[str, Any],
        path: tuple[str, ...],
    ) -> None:
        payload_nodes = payload.get("nodes")
        if (
            not isinstance(payload_nodes, list)
            or len(payload_nodes) != len(child_workflow.nodes)
        ):
            raise ValueError(
                f"portable workflow '{child_workflow.workflow_id}' "
                "has inconsistent node serialization"
            )
        for node, node_payload in zip(
            child_workflow.nodes,
            payload_nodes,
            strict=True,
        ):
            if not isinstance(node_payload, dict):
                raise ValueError(
                    "serialized portable node must be an object"
                )
            bind(node, node_payload, path)

    bind_workflow(workflow, serializable, ())


def _implementation_imports(
    bindings: Mapping[tuple[str, str], str],
    modules: list[str],
) -> tuple[list[str], dict[str, str]]:
    import_lines: list[str] = []
    namespaces: dict[str, str] = {}
    for module in modules:
        namespace = f"__vf_module_{len(namespaces)}"
        namespaces[module] = namespace
        import_lines.append(
            f"import * as {namespace} from "
            f"{json.dumps(module, ensure_ascii=False)};"
        )
    expressions = {
        binding: (
            f"{namespaces[module]}"
            + "".join(f"[{json.dumps(part, ensure_ascii=False)}]" for part in exported.split("."))
        )
        for (module, exported), binding in bindings.items()
    }
    return import_lines, expressions





def _plugin_binding_value(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    to_value = getattr(value, "to_value", None)
    if callable(to_value):
        payload = to_value()
        if isinstance(payload, Mapping):
            return dict(payload)
    raise TypeError("runtime plugin bindings must be serializable mappings")


def _runtime_plugin_imports(
    runtime_plugins: tuple[Mapping[str, Any], ...],
) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    factories: list[str] = []
    for index, plugin in enumerate(runtime_plugins):
        module_value = plugin.get("module", "")
        exported = str(plugin.get("export", "createPlugin") or "createPlugin")
        if not module_value:
            implementation = plugin.get("implementation")
            if isinstance(implementation, Mapping):
                module_value = implementation.get(
                    "module",
                    implementation.get("ref", ""),
                )
                exported = str(
                    implementation.get("export", exported) or exported
                )
        module = module_specifier(str(module_value))
        namespace = f"__vf_runtime_plugin_module_{index}"
        lines.append(
            f"import * as {namespace} from "
            f"{json.dumps(module, ensure_ascii=False)};"
        )
        factories.append(
            namespace + "".join(f"[{json.dumps(part, ensure_ascii=False)}]" for part in exported.split("."))
        )
    return lines, factories





__all__ = [
    "EmittedWorkflow",
    "emit_workflow_module",
    "schema_to_typescript",
]
