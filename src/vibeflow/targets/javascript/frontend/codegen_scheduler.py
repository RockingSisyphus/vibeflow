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
        asynchronous = workflow.entry_mode == "async"
        hook = "await invokeRuntimeHookAsync" if asynchronous else "invokeRuntimeHookSync"
        incoming = {node.id: [] for node in workflow.nodes}
        for route in workflow.routes:
            if route.schedule:
                incoming[route.target].append(route)
        empty_starts = {node.id for node in workflow.nodes
                        if node.is_terminal and not incoming[node.id]
                        and not node.requires and not node.provides}
        lines = [f"{'async ' if asynchronous else ''}function {code.function_name}(initial, root, path) {{",
                 "  const running = new Map();", "  try {",
                 f'    {hook}(root, "beforeBlock", {{blockPath: formatBlockPath(path), path: [...path]}});',
                 f"    const state = createStaticState({code.metadata_name}, initial, root, path);"]
        for node in workflow.nodes:
            lines.append(f"    initializeInbox(state, {js(node.id)});")
            if node.requires and (not incoming[node.id] or any(r.source in empty_starts for r in incoming[node.id])):
                lines.append(f"    seedInbox(state, {js(node.id)}, {js([r.type for r in node.requires])});")
        lines.extend([f"    const ready = {js(list(workflow.entries))};",
                      "    const queued = new Set(ready);", "    let completed = false;",
                      f"    const executeReady = {'async ' if asynchronous else ''}(nodeId) => {{",
                      "      switch (nodeId) {"])
        for node in workflow.nodes:
            lines.extend(self._emit_scheduler_case(code, node, incoming[node.id]))
        lines.extend(["        default: break;", "      }", "    };"])
        if asynchronous:
            lines.extend([
                "    while (ready.length || running.size) {",
                "      throwIfAborted(root.signal, state.workflow);",
                "      const batch = ready.splice(0);",
                "      for (const nodeId of batch) {",
                "        queued.delete(nodeId);",
                "        if (running.has(nodeId)) { enqueueStaticTargets([nodeId], ready, queued); continue; }",
                "        const operation = executeReady(nodeId).then(() => ({nodeId}), error => ({nodeId, error}));",
                "        running.set(nodeId, operation);",
                "      }",
                "      if (!running.size) break;",
                "      const outcome = await Promise.race(running.values());",
                "      running.delete(outcome.nodeId);",
                "      if (outcome.error) throw outcome.error;",
                "    }",
            ])
        else:
            lines.extend(["    while (ready.length) {", "      const nodeId = ready.shift();",
                          "      queued.delete(nodeId);", "      executeReady(nodeId);", "    }"])
        lines.extend(["    const publicOutputs = finalizeOutputs(state);",
                      f'    {hook}(root, "afterBlock", {{blockPath: formatBlockPath(path), path: [...path]}});',
                      "    return {publicOutputs, candidates: state.candidates, completed};",
                      "  } catch (cause) {"])
        if asynchronous:
            lines.extend([
                "    root.controller.abort(cause);",
                "    const remaining = await Promise.all(running.values());",
                "    for (const outcome of remaining) {",
                "      if (outcome.error && outcome.error !== cause && (outcome.error.code !== 'VF_ABORTED' || outcome.error.cleanupErrors?.length))",
                "        (cause.cleanupErrors ||= []).push(outcome.error);",
                "    }",
            ])
        lines.extend([f"    const failure = ensureErrorLocation(cause, {code.metadata_name}, path);",
                      f'    {hook}(root, "blockFailed", {{blockPath: formatBlockPath(path), path: [...path], code: failure.code, message: failure.message}}, true);',
                      "    throw failure;", "  }", "}"])
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
                f"            if (state.stepCount >= {code.workflow.max_steps}) throw vfError('VF_MAX_STEPS', 'workflow exceeded max_steps', state.workflow);",
                "            state.stepCount += 1;",
                f"            consumeStaticActivation({code.node_names[node.id]}, state);",
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
            ]
        )
        self._emit_node_invocation(lines, code, node)
        lines.extend(
            [
                (
                    f"            {hook}(state.root, \"afterNode\", {{ "
                    f"nodeId: {js(node.id)}, nodePath: nodePath(state, {js(node.id)}), "
                    f"blockPath: formatBlockPath(state.path), type: {js(node.type_used)}, "
                    "outputKeys: Object.keys(outputs || {}).sort() });"
                ),
                (
                    f"            const targets = {code.activate_names[node.id]}("
                    "outputs, inputs, state);"
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
