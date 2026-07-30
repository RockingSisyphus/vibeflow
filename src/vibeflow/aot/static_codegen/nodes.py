from __future__ import annotations

import json
from typing import Any, Mapping

from vibeflow.aot.model import NodeSpec
from vibeflow.aot.static_codegen.common import (
    WorkflowCode,
    edge_identity,
    js,
)


class NodeCodegenMixin:
    binding_expressions: Mapping[str, str]

    def _emit_activate(self, code: WorkflowCode, node: NodeSpec) -> str:
        routes = [
            route for route in code.workflow.routes if route.source == node.id
        ]
        lines = [
            (
                f"function {code.activate_names[node.id]}"
                "(outputs, inputs, state, deferred = false) {"
            ),
            "  const targets = [];",
        ]
        scheduled = [route.target for route in routes if route.schedule]
        if scheduled:
            lines.append("  if (deferred) {")
            for target in scheduled:
                lines.append(f"    targets.push({js(target)});")
            lines.extend(["    return targets;", "  }"])
        else:
            lines.append("  if (deferred) return targets;")
        lines.extend(
            [
                "  const values = conditionValues(inputs, outputs);",
                (
                    f"  const envelopes = outputEnvelopes("
                    f"{code.node_names[node.id]}, outputs);"
                ),
                "  for (const envelope of envelopes) recordCandidate(state, envelope);",
            ]
        )
        node_by_id = {item.id: item for item in code.workflow.nodes}
        for route in routes:
            body: list[str] = []
            if route.schedule:
                body.extend(
                    [
                        f"state.activeEdges.add({js(edge_identity(route.source, route.target))});",
                        f"targets.push({js(route.target)});",
                        (
                            "emitTrace(state.root, \"edge_activated\", "
                            f"{{ source: {js(route.source)}, target: {js(route.target)}, "
                            "path: state.path });"
                        ),
                    ]
                )
            if route.transfer:
                target = node_by_id[route.target]
                accepted = [item.type for item in target.requires]
                body.append(
                    f"deliverStatic(envelopes, state, {js(route.target)}, {js(accepted)});"
                )
            if route.condition is None:
                lines.extend(f"  {item}" for item in body)
            else:
                lines.append(
                    f"  if (conditionMatches({js(route.condition.to_dict())}, values)) {{"
                )
                lines.extend(f"    {item}" for item in body)
                lines.append("  }")
        lines.extend(["  return targets;", "}"])
        return "\n".join(lines)

    def _emit_execute(
        self,
        code: WorkflowCode,
        node: NodeSpec,
        node_payload: Mapping[str, Any],
    ) -> str:
        name = code.execute_names[node.id]
        if node.io_operation:
            return self._emit_io_execute(code, node)
        if node.is_loop:
            return self._emit_loop_execute(code, node)
        if node.is_nodeset:
            return self._emit_nodeset_execute(code, node)
        implementation_id = node_payload.get("implementation_id")
        expression = self.binding_expressions.get(str(implementation_id))
        if expression is None:
            expression = "undefined"
        is_async = code.workflow.entry_mode == "async"
        invoke_name = (
            "invokeStaticImplementationAsync"
            if is_async
            else "invokeStaticImplementationSync"
        )
        return "\n".join(
            [
                f"{'async ' if is_async else ''}function {name}(inputs, state) {{",
                (
                    f"  return {invoke_name}({expression}, "
                    f"{code.node_names[node.id]}, inputs, state);"
                ),
                "}",
            ]
        )

    def _emit_io_execute(
        self,
        code: WorkflowCode,
        node: NodeSpec,
    ) -> str:
        is_async = code.workflow.entry_mode == "async"
        name = code.execute_names[node.id]
        lines = [
            f"{'async ' if is_async else ''}function {name}(inputs, state) {{",
            "  const capability = "
            'nodeContext('
            f"{code.node_names[node.id]}, state"
            ').capabilities["vibeflow.port"];',
        ]
        if node.io_operation == "receive":
            await_prefix = "await " if is_async else ""
            provider = node.provides[0]
            lines.extend(
                [
                    (
                        f"  const received = {await_prefix}"
                        f"capability.receive({{{json.dumps('port')}: "
                        f"{js(node.io_port)}}});"
                    ),
                    "  const outputs = dictionary();",
                    (
                        f"  setOwn(outputs, {js(provider.key)}, "
                        "received.value);"
                    ),
                ]
            )
        else:
            requirement = node.requires[0]
            lines.extend(
                [
                    (
                        f"  const input = inputs[{js(requirement.type)}];"
                    ),
                    (
                        f"  capability.send({{{json.dumps('port')}: "
                        f"{js(node.io_port)}, {json.dumps('value')}: "
                        "valueFromEnvelope(input)});"
                    ),
                    "  const outputs = dictionary();",
                ]
            )
        lines.extend(
            [
                (
                    f"  return validateNodeOutputs("
                    f"{code.node_names[node.id]}, outputs, state);"
                ),
                "}",
            ]
        )
        return "\n".join(lines)

    def _emit_nodeset_execute(
        self,
        code: WorkflowCode,
        node: NodeSpec,
    ) -> str:
        assert node.subplan is not None
        child = code.children[node.id]
        is_async = code.workflow.entry_mode == "async"
        mappings: list[dict[str, str]] = []
        mismatch: tuple[str, int] | None = None
        for provider in node.provides:
            matches = [
                output
                for output in node.subplan.outputs
                if output.type == provider.type
            ]
            if len(matches) != 1:
                mismatch = (provider.type, len(matches))
                break
            mappings.append(
                {"provider": provider.key, "alias": matches[0].alias}
            )
        lines = [
            (
                f"{'async ' if is_async else ''}"
                f"function {code.execute_names[node.id]}(inputs, state) {{"
            ),
            "  emitTrace(state.root, \"nodeset_enter\", {",
            f"    nodeId: {js(node.id)},",
            f"    nodePath: nodePath(state, {js(node.id)}),",
            "  }, true);",
        ]
        if mismatch is not None:
            type_key, count = mismatch
            message = (
                f"composite node {node.id!r} expected one body output "
                f"contract of type {type_key!r}, got {count}"
            )
            lines.extend(
                [
                    "  throw vfError(",
                    '    "VF_OUTPUT_CARDINALITY",',
                    f"    {js(message)},",
                    "    state.workflow,",
                    f"    {{ nodePath: nodePath(state, {js(node.id)}) }},",
                    "  );",
                    "}",
                ]
            )
            return "\n".join(lines)
        lines.append(
            f"  const initial = rawInputsForChild("
            f"{child.metadata_name}.inputs, inputs, state.workflow, {js(node.id)});"
        )
        if is_async:
            lines.extend(
                [
                    "  const child = await awaitWithAbort(",
                    (
                        f"    {child.function_name}("
                        f"initial, state.root, [...state.path, {js(node.id)}]),"
                    ),
                    "    state.root.signal,",
                    "    state.workflow,",
                    f"    nodePath(state, {js(node.id)}),",
                    "  );",
                ]
            )
        else:
            lines.append(
                f"  const child = {child.function_name}("
                f"initial, state.root, [...state.path, {js(node.id)}]);"
            )
        lines.extend(
            [
                (
                    f"  const outputs = outputsFromChild("
                    f"{code.node_names[node.id]}, {js(mappings)}, child, state);"
                ),
                "  emitTrace(state.root, \"nodeset_exit\", {",
                f"    nodeId: {js(node.id)},",
                f"    nodePath: nodePath(state, {js(node.id)}),",
                "  }, true);",
                "  return outputs;",
                "}",
            ]
        )
        return "\n".join(lines)

    def _emit_loop_execute(
        self,
        code: WorkflowCode,
        node: NodeSpec,
    ) -> str:
        assert node.subplan is not None
        child = code.children[node.id]
        spec = node.loop
        is_async = code.workflow.entry_mode == "async"
        lines = [
            (
                f"{'async ' if is_async else ''}"
                f"function {code.execute_names[node.id]}(inputs, state) {{"
            ),
            "  emitTrace(state.root, \"loop_enter\", {",
            f"    nodeId: {js(node.id)},",
            f"    nodePath: nodePath(state, {js(node.id)}),",
            "  }, true);",
            "  const values = dictionary();",
            "  for (const [type, input] of Object.entries(inputs)) {",
            (
                "    setOwn(values, type, Array.isArray(input) "
                "? input.map(valueFromEnvelope) : valueFromEnvelope(input));"
            ),
            "    const items = Array.isArray(input) ? input : [input];",
            "    for (const item of items) {",
            "      if (item?.key) setOwn(values, item.key, item.value);",
            "      if (item?.type) setOwn(values, item.type, item.value);",
            "    }",
            "  }",
        ]
        self._emit_loop_carry_initialization(lines, code, node)
        lines.extend(
            [
                "  let stopped = false;",
                _loop_header(spec.max_iterations),
                (
                    f"    throwIfAborted(state.root.signal, state.workflow, "
                    f"nodePath(state, {js(node.id)}));"
                ),
                "    const initial = dictionary();",
            ]
        )
        for carry in spec.carry:
            lines.append(
                f"    setOwn(initial, {js(carry.target)}, values[{js(carry.target)}]);"
            )
        lines.extend(
            [
                "    emitTrace(state.root, \"loop_iteration\", {",
                f"      nodeId: {js(node.id)},",
                f"      nodePath: nodePath(state, {js(node.id)}),",
                "      iteration,",
                "    });",
            ]
        )
        if is_async:
            lines.extend(
                [
                    "    const child = await awaitWithAbort(",
                    (
                        f"      {child.function_name}(initial, state.root, "
                        f"[...state.path, {js(node.id)}, `iter_${{iteration}}`]),"
                    ),
                    "      state.root.signal,",
                    "      state.workflow,",
                    f"      nodePath(state, {js(node.id)}),",
                    "    );",
                ]
            )
        else:
            lines.append(
                f"    const child = {child.function_name}("
                f"initial, state.root, "
                f"[...state.path, {js(node.id)}, `iter_${{iteration}}`]);"
            )
        lines.extend(
            [
                "    const childValues = resultValues(child);",
                (
                    "    for (const [key, value] of Object.entries(childValues)) "
                    "setOwn(values, key, value);"
                ),
            ]
        )
        self._emit_loop_carry_updates(lines, code, node)
        self._emit_loop_collect(lines, node)
        lines.extend(
            [
                "    const iterationCount = iteration + 1;",
                '    setOwn(values, "loop.iterations", iterationCount);',
            ]
        )
        self._emit_loop_stop(lines, node)
        lines.extend(["    if (stopped) break;", "  }"])
        if (
            spec.max_iterations is not None
            and (spec.stop_after > 0 or spec.stop_when_source)
        ):
            lines.extend(
                [
                    "  if (!stopped) {",
                    (
                        f"    throw vfError(\"VF_MAX_STEPS\", "
                        f"{js(f'loop node {node.id!r} exceeded max_iterations={spec.max_iterations}')}, "
                        "state.workflow, { "
                        f"nodePath: nodePath(state, {js(node.id)}) }});"
                    ),
                    "  }",
                ]
            )
        lines.append("  const outputs = dictionary();")
        self._emit_loop_outputs(lines, node)
        lines.extend(
            [
                "  emitTrace(state.root, \"loop_exit\", {",
                f"    nodeId: {js(node.id)},",
                f"    nodePath: nodePath(state, {js(node.id)}),",
                "  }, true);",
                (
                    f"  return validateNodeOutputs("
                    f"{code.node_names[node.id]}, outputs, state);"
                ),
                "}",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _emit_loop_carry_initialization(
        lines: list[str],
        code: WorkflowCode,
        node: NodeSpec,
    ) -> None:
        del code
        for carry in node.loop.carry:
            lines.extend(
                [
                    (
                        f"  if (!Object.prototype.hasOwnProperty.call("
                        f"values, {js(carry.source)})) {{"
                    ),
                    (
                        f"    throw vfError(\"VF_INPUT_REQUIRED\", "
                        f"{js(f'loop carry source {carry.source!r} is unavailable')}, "
                        "state.workflow, { "
                        f"nodePath: nodePath(state, {js(node.id)}) }});"
                    ),
                    "  }",
                    (
                        f"  setOwn(values, {js(carry.target)}, "
                        f"values[{js(carry.source)}]);"
                    ),
                ]
            )

    @staticmethod
    def _emit_loop_carry_updates(
        lines: list[str],
        code: WorkflowCode,
        node: NodeSpec,
    ) -> None:
        del code
        for carry in node.loop.carry:
            lines.extend(
                [
                    (
                        f"    if (!Object.prototype.hasOwnProperty.call("
                        f"values, {js(carry.update)})) {{"
                    ),
                    (
                        f"      throw vfError(\"VF_OUTPUT_KEYS\", "
                        f"{js(f'loop carry update {carry.update!r} is unavailable')}, "
                        "state.workflow, { "
                        f"nodePath: nodePath(state, {js(node.id)}) }});"
                    ),
                    "    }",
                    (
                        f"    setOwn(values, {js(carry.target)}, "
                        f"values[{js(carry.update)}]);"
                    ),
                ]
            )

    @staticmethod
    def _emit_loop_collect(lines: list[str], node: NodeSpec) -> None:
        for collect in node.loop.collect:
            if collect.mode != "all":
                lines.append(
                    f"    throw vfError(\"VF_INTERNAL\", "
                    f"{js(f'unsupported loop collect mode {collect.mode!r}')}, "
                    "state.workflow);"
                )
                continue
            lines.extend(
                [
                    (
                        f"    if (!Object.prototype.hasOwnProperty.call("
                        f"values, {js(collect.source)})) {{"
                    ),
                    (
                        f"      throw vfError(\"VF_OUTPUT_KEYS\", "
                        f"{js(f'loop collect source {collect.source!r} is unavailable')}, "
                        "state.workflow);"
                    ),
                    "    }",
                    (
                        f"    if (!Array.isArray(values[{js(collect.target)}])) "
                        f"setOwn(values, {js(collect.target)}, []);"
                    ),
                    (
                        f"    values[{js(collect.target)}].push("
                        f"values[{js(collect.source)}]);"
                    ),
                ]
            )

    @staticmethod
    def _emit_loop_stop(lines: list[str], node: NodeSpec) -> None:
        spec = node.loop
        if spec.stop_after > 0:
            lines.append(f"    stopped = iterationCount >= {spec.stop_after};")
        if spec.stop_when_source:
            lines.extend(
                [
                (
                    f"    if (!Object.prototype.hasOwnProperty.call("
                    f"values, {js(spec.stop_when_source)})) {{"
                ),
                (
                    f"      throw vfError(\"VF_OUTPUT_KEYS\", "
                    f"{js(f'loop stop source {spec.stop_when_source!r} is unavailable')}, "
                    "state.workflow);"
                ),
                "    }",
                (
                    f"    if (typeof values[{js(spec.stop_when_source)}] "
                    '!== "boolean") {'
                ),
                (
                    f"      throw vfError(\"VF_OUTPUT_SCHEMA\", "
                    f"{js(f'loop stop source {spec.stop_when_source!r} must be boolean')}, "
                    "state.workflow);"
                ),
                "    }",
                (
                    f"    stopped = stopped || values[{js(spec.stop_when_source)}] "
                    f"=== {js(spec.stop_when_equals)};"
                ),
                ]
            )

    @staticmethod
    def _emit_loop_outputs(lines: list[str], node: NodeSpec) -> None:
        for output in node.loop.outputs:
            lines.extend(
                [
                    (
                        f"  if (!Object.prototype.hasOwnProperty.call("
                        f"values, {js(output.source)})) {{"
                    ),
                    (
                        f"    throw vfError(\"VF_OUTPUT_KEYS\", "
                        f"{js(f'loop output source {output.source!r} is unavailable')}, "
                        "state.workflow);"
                    ),
                    "  }",
                    (
                        f"  setOwn(outputs, {js(output.target)}, "
                        f"values[{js(output.source)}]);"
                    ),
                ]
            )


__all__ = ["NodeCodegenMixin"]


def _loop_header(max_iterations: int | None) -> str:
    if max_iterations is None:
        return "  for (let iteration = 0; ; iteration += 1) {"
    return (
        "  for (let iteration = 0; iteration < "
        f"{max_iterations}; iteration += 1) {{"
    )
