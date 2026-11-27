from __future__ import annotations

from typing import Any, Mapping

from vibeflow.targets.javascript.frontend.codegen_common import Expression, StaticData, js, private_params
from vibeflow.targets.javascript.frontend.emission_protocol import EmissionWorkflow


class StaticWorkflowEmitter:
    """Compile execution facts and static imports into module-local tables."""

    def __init__(
        self,
        *,
        workflow: EmissionWorkflow,
        payload: Mapping[str, Any],
        binding_expressions: Mapping[str, str],
        named_workflows=None,
        default_entry="",
    ) -> None:
        self.workflow = workflow
        self.payload = payload
        self.binding_expressions = binding_expressions
        self.named_workflows = named_workflows or {}
        self.default_entry = default_entry
        self.data = StaticData()
        self.blocks = []
        self.block_indices = {}
        self.calls = []

    def emit(self) -> str:
        root = self._register(self.workflow, self.payload, root=True)
        schemas = {key: self.data.share(value) for key, value in self.workflow.schemas.items()}
        asynchronous = self.workflow.entry_mode == "async"
        suffix = "Async" if asynchronous else "Sync"
        factory = f"createStaticWorkflow{suffix}"
        execute = f"executeStaticBlock{suffix}"
        entries = self.named_workflows or {"": self.workflow}
        declarations = []
        metadata_by_entry = [
            {**self._metadata(workflow), "workflow_id": workflow.workflow_id}
            for workflow in entries.values()
        ]
        self.data.count_uses((self.blocks, self.calls, schemas, metadata_by_entry))
        block_sources = self.data.write(self.blocks)
        call_sources = self.data.write(self.calls)
        schema_source = self.data.write(schemas)
        for index, metadata in enumerate(metadata_by_entry):
            metadata = self.data.write(metadata)
            declarations.append(
                f"const __vfEntryInvoke_{index} = {factory}({metadata}, __vfSchemaCatalog,"
                " __vfRuntimePluginDescriptors, __vfRuntimePluginFactories,"
                f" (inputs, root, path) => {execute}(__vfProgram, {root}, inputs, root, path, {index}));"
            )
        if self.named_workflows:
            pairs = ",".join(f"[{js(name)},__vfEntryInvoke_{index}]" for index, name in enumerate(entries))
            default = self.default_entry or (next(iter(entries)) if len(entries) == 1 else None)
            declarations.extend([
                f"const __vfEntryInvocations = new Map([{pairs}]);",
                f"""function __vfInvokeWorkflow(inputs, options = {{}}) {{
  const invoke = __vfEntryInvocations.get(options.entry ?? {js(default)});
  if (!invoke) throw new Error('select a workflow entry: ' + [...__vfEntryInvocations.keys()].join(', '));
  return invoke(inputs, options);
}}""",
            ])
        else:
            declarations.append("""function __vfInvokeWorkflow(inputs, options = {}) {
  if (options.entry != null) throw new Error('unknown workflow entry: ' + options.entry);
  return __vfEntryInvoke_0(inputs, options);
}""")
        return "\n".join([
            self.data.declaration() if self.data.indices else "",
            f"const __vfSchemaCatalog = deepFreeze({schema_source});",
            f"const __vfProgram = {{blocks: {block_sources}, calls: {call_sources}}};",
            *declarations,
        ])

    def _ports(self, items):
        result = []
        for item in items:
            fields = item.to_dict()
            if "schema" in fields:
                fields["schema"] = self.data.share(fields["schema"])
            result.append(fields)
        return result

    def _metadata(self, workflow):
        return {
            "abi_version": workflow.abi_version,
            "node_order": [node.id for node in workflow.nodes],
            "inputs": self._ports(workflow.inputs),
            "outputs": self._ports(workflow.outputs),
            "max_steps": workflow.max_steps,
            "entry_mode": workflow.entry_mode,
        }

    def _register(self, workflow, payload, *, root=False):
        nodes = {node.id: node for node in workflow.nodes}
        indices = {name: index for index, name in enumerate(nodes)}
        incoming = {name: [] for name in nodes}
        outgoing = {name: [] for name in nodes}
        edges = {}
        for route in workflow.routes:
            if route.schedule:
                pair = (route.source, route.target)
                edges.setdefault(pair, len(edges))
                incoming[route.target].append(route)
            outgoing[route.source].append(route)
        descriptors, params, children = [], [], {}
        for index, (node, raw) in enumerate(zip(nodes.values(), payload["nodes"], strict=True)):
            descriptors.append(self._node(node, raw, outgoing[node.id], nodes, indices, edges, workflow.entry_mode))
            params.append(dict(node.params))
            if node.subplan is not None:
                children[str(index)] = self._register(node.subplan, raw["subplan"])

        variants = [
            self._entry(selected, nodes, indices, incoming, edges, named=root and bool(self.named_workflows))
            for selected in (self.named_workflows.values() if root and self.named_workflows else (workflow,))
        ]
        block = (None if root else self._metadata(workflow), descriptors, variants)
        # Descriptions contain static bindings. Workflow IDs, parameter objects and
        # child call references live in the separate call table.
        key = repr(block)
        if key not in self.block_indices:
            self.block_indices[key] = len(self.blocks)
            self.blocks.append(block)
        call = len(self.calls)
        self.calls.append((self.block_indices[key], workflow.workflow_id, private_params(params), children))
        return call

    def _node(self, node, raw, routes, nodes, indices, edges, mode):
        outgoing = [
            (
                indices[route.target],
                edges[(route.source, route.target)] if route.schedule else None,
                self.data.share([port.type for port in nodes[route.target].requires]) if route.transfer else None,
                self.data.share(route.condition.to_dict()) if route.condition is not None else None,
            )
            for route in routes
        ]
        target_count = len({target for target, edge, _, _ in outgoing if edge is not None})
        description = {
            "id": node.id,
            "definition_id": node.definition_id,
            "requires": self.data.share([item.to_dict() for item in node.requires]),
            "provides": self.data.share([item.to_dict() for item in node.provides]),
        }
        if node.implementation is not None:
            description["source"] = self.data.share(node.implementation.to_dict())
        suffix = "Async" if mode == "async" else "Sync"
        if node.is_loop:
            operation = (Expression(f"executeStaticLoop{suffix}"), self.data.share(node.loop.to_dict()))
        elif node.is_nodeset:
            operation = (Expression(f"executeStaticNodeset{suffix}"), self._nodeset_outputs(node))
        else:
            binding = self.binding_expressions.get(str(raw.get("implementation_id")), "undefined")
            operation = (Expression(f"executeStaticNode{suffix}"), Expression(binding))
        return (description, operation, outgoing, node.is_terminal and not target_count,
                node.max_concurrency if target_count > 1 else None)

    def _nodeset_outputs(self, node):
        mappings = []
        for provider in node.provides:
            matches = [output for output in node.subplan.outputs if output.type == provider.type]
            if len(matches) != 1:
                return f"composite node {node.id!r} expected one body output contract of type {provider.type!r}, got {len(matches)}"
            mappings.append({"provider": provider.key, "alias": matches[0].alias})
        return self.data.share(mappings)

    def _entry(self, selected, nodes, indices, incoming, edges, *, named):
        active = {node.id for node in selected.nodes}
        routes = {name: [route for route in sources if route.source in active] for name, sources in incoming.items()}
        empty_starts = {
            node.id for node in selected.nodes
            if node.is_terminal and not node.requires and not node.provides
            and (node.id in selected.entries if named else not routes[node.id])
        }
        checks = {}
        for node in selected.nodes:
            sources = routes[node.id]
            seed = None
            if node.requires and (not sources or any(route.source in empty_starts for route in sources)):
                seed = self.data.share([item.type for item in node.requires])
            policy, required = _join_edges(node, sources, nodes)
            checks[str(indices[node.id])] = (
                seed, policy, [edges[(route.source, route.target)] for route in required],
                self.data.share([item.type for item in node.requires if item.cardinality == "exactly_one"]),
            )
        return ([indices[name] for name in selected.entries], checks if named else list(checks.values()))


def _join_edges(node, incoming, nodes):
    if not incoming:
        return None, ()
    if node.join_policy in {"all", "any_active"}:
        return node.join_policy, incoming
    if node.join_policy == "safe_any":
        conditional = [route for route in incoming if route.condition is not None]
        if len(conditional) == len(incoming):
            return "any_active", conditional
        required = {item.type for item in node.requires}
        control = [
            route for route in conditional
            if not any(item.type in required for item in nodes[route.source].provides)
        ]
        if control:
            return "any_active", control
    return None, ()
