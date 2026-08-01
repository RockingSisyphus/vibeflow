from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from vibeflow.aot.declarations import (
    declarations,
    schema_to_typescript,
)
from vibeflow.aot.model import (
    AotPlanError,
    ImplementationSpec,
    NodeSpec,
    WorkflowSpec,
    normalize_workflow_plan,
)
from vibeflow.aot.schema import (
    JavascriptJsonValueError,
    validate_javascript_json_value,
)
from vibeflow.aot.static_codegen import StaticWorkflowEmitter
from vibeflow.aot.templates import RUNTIME_SOURCE


@dataclass(frozen=True)
class EmittedWorkflow:
    source: str
    declarations: str
    plan_sha256: str
    implementation_modules: tuple[str, ...]
    implementation_bindings: tuple[tuple[str, str], ...]
    host_extensions: tuple[str, ...] = ()


def emit_workflow_module(
    plan: WorkflowSpec | object,
    *,
    implementation_by_type: Mapping[str, object] | None = None,
    host_extensions: tuple[Mapping[str, Any], ...] = (),
) -> EmittedWorkflow:
    """Emit a side-effect-free ESM module from portable JSON/dataclasses.

    ``implementation_by_type`` is the integration seam for a descriptor
    catalog. Portable catalog source references can be replaced with concrete
    JS/TS locations without mutating the portable plan.
    """

    workflow = normalize_workflow_plan(plan)
    raw_overrides = {
        str(key): value
        for key, value in (implementation_by_type or {}).items()
    }
    overrides = {
        str(key): _implementation_override(value)
        for key, value in raw_overrides.items()
    }
    serializable = workflow.to_dict()
    bindings: dict[tuple[str, str], str] = {}
    modules: list[str] = []
    _bind_implementations(
        workflow,
        serializable,
        raw_overrides=raw_overrides,
        overrides=overrides,
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
    host_imports, host_factories = _host_extension_imports(
        host_extensions,
    )
    import_lines.extend(host_imports)
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
    ).emit()
    if workflow.entry_mode == "sync":
        public_entry = (
            "export function runWorkflow(inputs, options) {\n"
            "  return __vfInvokeWorkflow(inputs, options);\n"
            "}"
        )
    else:
        public_entry = (
            "export async function runWorkflowAsync(inputs, options) {\n"
            "  return __vfInvokeWorkflow(inputs, options);\n"
            "}"
        )
    source_parts = [
        "\n".join(import_lines),
        RUNTIME_SOURCE,
        static_source,
        public_entry,
        (
            _host_extension_source(
                workflow,
                host_extensions,
                host_factories,
            )
            if host_extensions
            else ""
        ),
        "",
    ]
    return EmittedWorkflow(
        source="\n\n".join(part for part in source_parts if part != ""),
        declarations=declarations(
            workflow,
            has_host_extensions=bool(host_extensions),
        ),
        plan_sha256=hashlib.sha256(
            canonical_plan.encode("utf-8")
        ).hexdigest(),
        implementation_modules=tuple(modules),
        implementation_bindings=tuple(bindings),
        host_extensions=tuple(
            str(item.get("id", "")) for item in host_extensions
        ),
    )


def _bind_implementations(
    workflow: WorkflowSpec,
    serializable: dict[str, Any],
    *,
    raw_overrides: Mapping[str, object],
    overrides: Mapping[str, ImplementationSpec],
    bindings: dict[tuple[str, str], str],
    modules: list[str],
) -> None:
    def bind(
        node: NodeSpec,
        node_payload: dict[str, Any],
        path: tuple[str, ...],
    ) -> None:
        if node.implementation is not None:
            implementation = overrides.get(
                node.type_used,
                node.implementation,
            )
            module = _module_specifier(implementation.module)
            binding_key = (module, implementation.export)
            binding = bindings.get(binding_key)
            if binding is None:
                binding = f"impl:{len(bindings)}"
                bindings[binding_key] = binding
                if module not in modules:
                    modules.append(module)
            node_payload["implementation_id"] = binding
            node_payload["implementation"] = implementation.to_dict()
            _attach_output_schemas(
                node_payload,
                raw_overrides.get(node.type_used),
            )
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
        child_workflow: WorkflowSpec,
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


def _attach_output_schemas(
    node_payload: dict[str, Any],
    raw_override: object,
) -> None:
    if not isinstance(raw_override, Mapping):
        return
    output_schemas = raw_override.get("output_schema")
    if not isinstance(output_schemas, Mapping) or not output_schemas:
        return
    node_payload["output_schemas"] = {
        str(key): dict(value)
        for key, value in output_schemas.items()
        if isinstance(value, Mapping)
    }


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
            f"[{json.dumps(exported, ensure_ascii=False)}]"
        )
        for (module, exported), binding in bindings.items()
    }
    return import_lines, expressions


def _host_extension_imports(
    host_extensions: tuple[Mapping[str, Any], ...],
) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    factories: list[str] = []
    for index, extension in enumerate(host_extensions):
        module = _module_specifier(str(extension.get("module", "")))
        exported = str(
            extension.get("export", "createHostExtension")
            or "createHostExtension"
        )
        namespace = f"__vf_host_module_{index}"
        lines.append(
            f"import * as {namespace} from "
            f"{json.dumps(module, ensure_ascii=False)};"
        )
        factories.append(
            f"{namespace}[{json.dumps(exported, ensure_ascii=False)}]"
        )
    return lines, factories


def _host_extension_source(
    workflow: WorkflowSpec,
    host_extensions: tuple[Mapping[str, Any], ...],
    factories: list[str],
) -> str:
    descriptors = [
        {
            "id": str(extension.get("id", "")),
            "provides": [
                str(item)
                for item in extension.get("provides", ())
            ],
            "config": dict(extension.get("config", {})),
            "factory_index": index,
        }
        for index, extension in enumerate(host_extensions)
    ]
    entry_name = (
        "runWorkflow"
        if workflow.entry_mode == "sync"
        else "runWorkflowAsync"
    )
    invoke_async = "" if workflow.entry_mode == "sync" else "async "
    invocation = (
        """
    try {
      return __vfInvokeWorkflow(inputs, { ...rawOptions, capabilities, signal: linked.signal });
    } finally {
      linked.cleanup();
    }"""
        if workflow.entry_mode == "sync"
        else """
    const invocation = Promise.resolve().then(() =>
      __vfInvokeWorkflow(inputs, { ...rawOptions, capabilities, signal: linked.signal })
    );
    active.add(invocation);
    try {
      return await invocation;
    } finally {
      active.delete(invocation);
      linked.cleanup();
    }"""
    )
    return f"""
const __vfHostDescriptors = {json.dumps(descriptors, ensure_ascii=False, sort_keys=True)};
const __vfHostFactories = [{", ".join(factories)}];

function __vfHostFailure(code, message, cause) {{
  return new VibeFlowWorkflowError(code, message, {{
    workflowId: {json.dumps(workflow.workflow_id, ensure_ascii=False)},
    cause,
  }});
}}

function __vfLinkedSignal(signals) {{
  const controller = new AbortController();
  const listeners = [];
  for (const signal of signals.filter(Boolean)) {{
    if (signal.aborted) {{
      controller.abort(signal.reason);
      break;
    }}
    const listener = () => controller.abort(signal.reason);
    signal.addEventListener("abort", listener, {{ once: true }});
    listeners.push([signal, listener]);
  }}
  return {{
    signal: controller.signal,
    cleanup() {{
      for (const [signal, listener] of listeners) {{
        signal.removeEventListener("abort", listener);
      }}
    }},
  }};
}}

function __vfFrozenHostConfig(value) {{
  if (Array.isArray(value)) {{
    return Object.freeze(value.map((item) => __vfFrozenHostConfig(item)));
  }}
  if (value && typeof value === "object") {{
    const copy = {{}};
    for (const [key, item] of Object.entries(value)) {{
      copy[key] = __vfFrozenHostConfig(item);
    }}
    return Object.freeze(copy);
  }}
  return value;
}}

export function createWorkflowHost(options = {{}}) {{
  if (!options || typeof options !== "object" || Array.isArray(options)) {{
    throw __vfHostFailure(
      "VF_HOST_OPTIONS",
      "workflow host options must be an object",
    );
  }}
  const controller = new AbortController();
  const active = new Set();
  const externalCapabilities = options.capabilities || {{}};
  const providedCapabilities = Object.create(null);
  let started = false;
  let startedCount = 0;
  let startPromise = null;
  let stopPromise = null;

  function mergedCapabilities(extra = {{}}) {{
    const merged = Object.create(null);
    for (const source of [externalCapabilities, providedCapabilities, extra]) {{
      for (const [id, capability] of Object.entries(source || {{}})) {{
        if (Object.prototype.hasOwnProperty.call(merged, id)) {{
          throw __vfHostFailure(
            "VF_HOST_CAPABILITY_CONFLICT",
            `capability '${{id}}' is supplied by more than one host source`,
          );
        }}
        merged[id] = capability;
      }}
    }}
    return merged;
  }}

  {invoke_async}function invoke(inputs, rawOptions = {{}}) {{
    if (!started || stopPromise) {{
      throw __vfHostFailure(
        "VF_HOST_NOT_STARTED",
        "workflow host must be started before invoking its workflow",
      );
    }}
    const capabilities = mergedCapabilities(rawOptions.capabilities);
    const linked = __vfLinkedSignal([controller.signal, rawOptions.signal]);
    {invocation.strip()}
  }}

  const instances = __vfHostDescriptors.map((descriptor) => {{
    const factory = __vfHostFactories[descriptor.factory_index];
    if (typeof factory !== "function") {{
      throw __vfHostFailure(
        "VF_HOST_EXTENSION_FACTORY",
        `host_extension '${{descriptor.id}}' does not export a factory function`,
      );
    }}
    let instance;
    try {{
      instance = factory(Object.freeze({{
        extensionId: descriptor.id,
        config: __vfFrozenHostConfig(descriptor.config),
        signal: controller.signal,
        {entry_name}: invoke,
      }}));
    }} catch (cause) {{
      throw __vfHostFailure(
        "VF_HOST_EXTENSION_CREATE",
        `host_extension '${{descriptor.id}}' factory failed`,
        cause,
      );
    }}
    if (!instance || typeof instance !== "object"
        || typeof instance.start !== "function"
        || typeof instance.stop !== "function") {{
      throw __vfHostFailure(
        "VF_HOST_EXTENSION_SHAPE",
        `host_extension '${{descriptor.id}}' must return start() and stop()`,
      );
    }}
    const capabilities = instance.capabilities || {{}};
    for (const capabilityId of descriptor.provides) {{
      if (!Object.prototype.hasOwnProperty.call(capabilities, capabilityId)) {{
        throw __vfHostFailure(
          "VF_HOST_EXTENSION_CAPABILITY",
          `host_extension '${{descriptor.id}}' did not provide '${{capabilityId}}'`,
        );
      }}
      if (Object.prototype.hasOwnProperty.call(providedCapabilities, capabilityId)) {{
        throw __vfHostFailure(
          "VF_HOST_CAPABILITY_CONFLICT",
          `multiple host_extensions provide capability '${{capabilityId}}'`,
        );
      }}
      providedCapabilities[capabilityId] = capabilities[capabilityId];
    }}
    return {{ descriptor, instance }};
  }});

  async function start() {{
    if (stopPromise) {{
      throw __vfHostFailure(
        "VF_HOST_STOPPED",
        "a stopped workflow host cannot be restarted",
      );
    }}
    if (started) return;
    if (startPromise) return startPromise;
    startPromise = (async () => {{
      try {{
        for (const item of instances) {{
          await item.instance.start();
          startedCount += 1;
        }}
        started = true;
      }} catch (cause) {{
        controller.abort(cause);
        for (let index = startedCount - 1; index >= 0; index -= 1) {{
          try {{
            await instances[index].instance.stop();
          }} catch {{
            // Preserve the primary start failure.
          }}
        }}
        startedCount = 0;
        throw __vfHostFailure(
          "VF_HOST_EXTENSION_START",
          "workflow host failed while starting an extension",
          cause,
        );
      }}
    }})();
    return startPromise;
  }}

  async function stop() {{
    if (stopPromise) return stopPromise;
    stopPromise = (async () => {{
      controller.abort("workflow host stopped");
      let firstFailure = null;
      for (let index = startedCount - 1; index >= 0; index -= 1) {{
        try {{
          await instances[index].instance.stop();
        }} catch (cause) {{
          firstFailure ||= cause;
        }}
      }}
      startedCount = 0;
      started = false;
      await Promise.allSettled([...active]);
      if (firstFailure) {{
        throw __vfHostFailure(
          "VF_HOST_EXTENSION_STOP",
          "workflow host failed while stopping an extension",
          firstFailure,
        );
      }}
    }})();
    return stopPromise;
  }}

  return Object.freeze({{
    signal: controller.signal,
    get started() {{ return started; }},
    start,
    stop,
    {entry_name}: invoke,
  }});
}}
""".strip()


def _implementation_override(value: object) -> ImplementationSpec:
    if isinstance(value, ImplementationSpec):
        return value
    if isinstance(value, (str, Path)):
        return ImplementationSpec(module=str(value))
    if not isinstance(value, Mapping):
        raise TypeError(
            "implementation override must be a path, mapping, "
            "or ImplementationSpec"
        )
    source = value.get("source")
    source_map = source if isinstance(source, Mapping) else {}
    module = value.get(
        "module",
        value.get(
            "entry",
            value.get(
                "ref",
                source_map.get("ref", source_map.get("module", "")),
            ),
        ),
    )
    if not str(module or "").strip():
        raise ValueError("implementation override requires module/ref")
    exported = value.get("export", source_map.get("export", "run"))
    return ImplementationSpec(
        module=str(module),
        export=str(exported or "run"),
        language=str(
            value.get("language", "javascript") or "javascript"
        ),
        completion=str(
            value.get("completion", "immediate") or "immediate"
        ),
    )


def _module_specifier(value: str) -> str:
    module = str(value).strip()
    if not module:
        raise ValueError("node implementation module cannot be empty")
    if "\n" in module or "\r" in module or "\x00" in module:
        raise ValueError(
            "node implementation module contains invalid characters"
        )
    return module


__all__ = [
    "EmittedWorkflow",
    "emit_workflow_module",
    "schema_to_typescript",
]
