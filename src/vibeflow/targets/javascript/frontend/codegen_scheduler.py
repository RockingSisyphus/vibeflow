from __future__ import annotations

from typing import Any

from vibeflow.targets.javascript.frontend.emission_protocol import EmissionNode
from vibeflow.targets.javascript.frontend.codegen_common import (
    WorkflowCode,
    edge_identity,
    js,
)


class SchedulerCodegenMixin:
    def _emit_scheduler(self, code: WorkflowCode) -> str:
        workflow = code.workflow
        hook = (
            "await invokeRuntimeHookAsync"
            if workflow.entry_mode == "async"
            else "invokeRuntimeHookSync"
        )
        incoming: dict[str, list[Any]] = {
            node.id: [] for node in workflow.nodes
        }
        for route in workflow.routes:
            if route.schedule:
                incoming[route.target].append(route)
        empty_starts = {
            node.id
            for node in workflow.nodes
            if node.is_terminal
            and not incoming[node.id]
            and not node.requires
            and not node.provides
        }
        lines = [
            (
                f"{'async ' if workflow.entry_mode == 'async' else ''}"
                f"function {code.function_name}(initial, root, path) {{"
            ),
            "  try {",
            (
                f"    {hook}(root, \"beforeBlock\", {{ "
                "blockPath: formatBlockPath(path), path: [...path] });"
            ),
            (
                f"    const state = createStaticState("
                f"{code.metadata_name}, initial, root, path);"
            ),
        ]
        for node in workflow.nodes:
            targets = {key: code.children[(node.id,key)] for key in node.task_plans}
            if targets:
                lines.append(f"    setOwn(state.taskExecutors, {js(node.id)}, dictionary());")
                for key, child in targets.items():
                    lines.append(f"    setOwn(state.taskExecutors[{js(node.id)}], {js(key)}, (inputs, root, path) => {child.function_name}(inputs, root, path));")
        for node in workflow.nodes:
            lines.append(f"    initializeInbox(state, {js(node.id)});")
        for node in workflow.nodes:
            node_incoming = incoming[node.id]
            if node.requires and (
                not node_incoming
                or any(route.source in empty_starts for route in node_incoming)
            ):
                lines.append(
                    f"    seedInbox(state, {js(node.id)}, "
                    f"{js([item.type for item in node.requires])});"
                )
        lines.extend(
            [
                f"    const ready = {js(list(workflow.entries))};",
                "    const queued = new Set(ready);",
                "    let completed = false;",
                "    while (ready.length) {",
                f"      throwIfAborted(root.signal, {code.metadata_name});",
                f"      if (state.stepCount >= {workflow.max_steps}) {{",
                '        const nextNodeId = ready[0] || "";',
                "        throw vfError(",
                '          "VF_MAX_STEPS",',
                (
                    f"          {js(f'workflow exceeded max_steps={workflow.max_steps}')},"
                ),
                f"          {code.metadata_name},",
                "          {",
                '            nodePath: nextNodeId ? nodePath(state, nextNodeId) : "",',
                "            blockPath: formatBlockPath(path),",
                "          },",
                "        );",
                "      }",
                "      const nodeId = ready.shift();",
                "      queued.delete(nodeId);",
                "      switch (nodeId) {",
            ]
        )
        for node in workflow.nodes:
            lines.extend(self._emit_scheduler_case(code, node, incoming[node.id]))
        lines.extend(
            [
                "        default:",
                "          break;",
                "      }",
                "    }",
                '    const publicOutputs = state.workflow.kind === "task" ? state.taskOutputs : finalizeOutputs(state);',
                (
                    f"    {hook}(root, \"afterBlock\", {{ "
                    "blockPath: formatBlockPath(path), path: [...path] });"
                ),
                "    return { publicOutputs, candidates: state.candidates, completed };",
                "  } catch (cause) {",
                (
                    f"    const failure = ensureErrorLocation(cause, "
                    f"{code.metadata_name}, path);"
                ),
                (
                    f"    {hook}(root, \"blockFailed\", {{ "
                    "blockPath: formatBlockPath(path), path: [...path], "
                    "code: failure.code, message: failure.message }, true);"
                ),
                "    throw failure;",
                "  }",
                "}",
            ]
        )
        return "\n".join(lines)

    def _emit_scheduler_case(
        self,
        code: WorkflowCode,
        node: EmissionNode,
        incoming: list[Any],
    ) -> list[str]:
        hook = (
            "await invokeRuntimeHookAsync"
            if code.workflow.entry_mode == "async"
            else "invokeRuntimeHookSync"
        )
        lines = [f"        case {js(node.id)}: {{"]
        node_by_id = {item.id: item for item in code.workflow.nodes}
        availability = self._availability_tests(
            code,
            node,
            incoming,
            node_by_id,
        )
        if availability:
            lines.append(
                f"          if (!({' && '.join(availability)})) break;"
            )
        lines.extend(
            [
                "          try {",
                (
                    f"            const inputs = prepareStaticNode("
                    f"{code.node_names[node.id]}, state);"
                ),
                (
                    f"            {hook}(state.root, \"beforeNode\", {{ "
                    f"nodeId: {js(node.id)}, nodePath: nodePath(state, {js(node.id)}), "
                    f"blockPath: formatBlockPath(state.path), type: {js(node.type_used)} }});"
                ),
                "            let outputs;",
                "            let deferred = false;",
            ]
        )
        self._emit_node_invocation(lines, code, node)
        lines.extend(
            [
                "            state.taskOutputs = outputs;",
                "            state.stepCount += 1;",
                (
                    f"            const targets = {code.activate_names[node.id]}("
                    "outputs, inputs, state, deferred);"
                ),
                (
                    f"            {hook}(state.root, \"afterNode\", {{ "
                    f"nodeId: {js(node.id)}, nodePath: nodePath(state, {js(node.id)}), "
                    f"blockPath: formatBlockPath(state.path), type: {js(node.type_used)}, "
                    "outputKeys: Object.keys(outputs || {}).sort() });"
                ),
            ]
        )
        has_scheduled_outgoing = any(
            route.schedule
            for route in code.workflow.routes
            if route.source == node.id
        )
        if node.is_terminal and not has_scheduled_outgoing:
            lines.extend(
                [
                    "            completed = true;",
                    "            ready.length = 0;",
                ]
            )
        else:
            lines.append(
                "            enqueueStaticTargets(targets, ready, queued);"
            )
        lines.extend(
            [
                "          } catch (cause) {",
                (
                    f"            const failure = ensureErrorLocation("
                    f"cause, {code.metadata_name}, path, {js(node.id)});"
                ),
                (
                    f"            {hook}(state.root, \"nodeFailed\", {{ "
                    f"nodeId: {js(node.id)}, nodePath: nodePath(state, {js(node.id)}), "
                    "blockPath: formatBlockPath(state.path), "
                    "code: failure.code, message: failure.message }, true);"
                ),
                "            throw failure;",
                "          }",
                "          break;",
                "        }",
            ]
        )
        return lines

    @staticmethod
    def _availability_tests(
        code: WorkflowCode,
        node: EmissionNode,
        incoming: list[Any],
        node_by_id: dict[str, EmissionNode],
    ) -> list[str]:
        del code
        availability: list[str] = []
        edge_tests = [
            f"state.activeEdges.has({js(edge_identity(route.source, route.target))})"
            for route in incoming
        ]
        if incoming and node.join_policy == "all":
            availability.append("(" + " && ".join(edge_tests) + ")")
        elif incoming and node.join_policy == "any_active":
            availability.append("(" + " || ".join(edge_tests) + ")")
        elif incoming and node.join_policy == "safe_any":
            availability.extend(
                SchedulerCodegenMixin._safe_any_tests(
                    node,
                    incoming,
                    node_by_id,
                )
            )
        for requirement in node.requires:
            if requirement.cardinality == "exactly_one":
                availability.append(
                    f"state.inboxes[{js(node.id)}].some("
                    f"(item) => item.type === {js(requirement.type)})"
                )
        return availability

    @staticmethod
    def _safe_any_tests(
        node: EmissionNode,
        incoming: list[Any],
        node_by_id: dict[str, EmissionNode],
    ) -> list[str]:
        conditional_routes = [
            route for route in incoming if route.condition is not None
        ]
        if conditional_routes and len(conditional_routes) == len(incoming):
            return [
                "("
                + " || ".join(
                    f"state.activeEdges.has({js(edge_identity(route.source, route.target))})"
                    for route in conditional_routes
                )
                + ")"
            ]
        required_types = {
            requirement.type for requirement in node.requires
        }
        control_routes = [
            route
            for route in conditional_routes
            if not any(
                provider.type in required_types
                for provider in node_by_id[route.source].provides
            )
        ]
        if not control_routes:
            return []
        return [
            "("
            + " || ".join(
                f"state.activeEdges.has({js(edge_identity(route.source, route.target))})"
                for route in control_routes
            )
            + ")"
        ]

    @staticmethod
    def _emit_node_invocation(
        lines: list[str],
        code: WorkflowCode,
        node: EmissionNode,
    ) -> None:
        await_prefix = "await " if code.workflow.entry_mode == "async" else ""
        lines.extend([
            f"            outputs = {await_prefix}{code.execute_names[node.id]}(inputs, state);",
            f"            finishStaticNode({code.node_names[node.id]}, state);",
        ])



__all__ = ["SchedulerCodegenMixin"]
