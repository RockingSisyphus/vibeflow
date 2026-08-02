from __future__ import annotations

from typing import Mapping

from vibeflow.core.contracts import CARDINALITY_ALL, CARDINALITY_EXACTLY_ONE, CARDINALITY_OPTIONAL_ONE, DataEnvelope
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
from vibeflow.targets.python.runtime.helpers import condition_matches
from vibeflow.targets.python.runtime.types import _RuntimeState
from vibeflow.targets.python.runtime.values import _store_output

class RuntimeOutputMixin:
    def _deliver_transfer_only_edges(self, node_name: str, outputs: Mapping[str, object], state: _RuntimeState, scheduled_pairs: set[tuple[str, str]]) -> None:
        # Deferred result-key tasks have not produced transferable values yet.
        # Their routes and data are delivered once the task is joined.
        if node_name in self._async_results:
            return
        values = self._condition_values(node_name, outputs, state)
        for edge in self._frames[node_name].transfer_outgoing:
            if edge.pair in scheduled_pairs:
                continue
            if edge.when and not condition_matches(edge.when, values):
                continue
            self._record_edge(edge)
            self._deliver_outputs(edge, outputs, state)

    def _deliver_outputs(self, edge: EdgeSpec, outputs: Mapping[str, object], state: _RuntimeState) -> None:
        source = self._frames[edge.source]
        if edge.pair not in {
            candidate.pair for candidate in source.transfer_outgoing
        }:
            return
        target = self._frames[edge.target]
        providers_by_key = {provider.key: provider for provider in source.provides}
        required_types = {requirement.type for requirement in target.requires}
        for key, value in outputs.items():
            provider = providers_by_key.get(str(key))
            if provider is None:
                continue
            envelope = DataEnvelope(key=provider.key, type=provider.type, value=value, source_node=source.name)
            if provider.type in required_types:
                state.inboxes[target.name] = [
                    item
                    for item in state.inboxes[target.name]
                    if (item.key, item.type, item.source_node) != (envelope.key, envelope.type, envelope.source_node)
                ]
                state.inboxes[target.name].append(envelope)

    def _record_node_output_candidates(
        self,
        node_name: str,
        outputs: Mapping[str, object],
        state: _RuntimeState,
    ) -> None:
        frame = self._frames[node_name]
        providers_by_key = {provider.key: provider for provider in frame.provides}
        for key, value in outputs.items():
            provider = providers_by_key.get(str(key))
            if provider is None:
                continue
            self._record_pipeline_output_candidate(
                DataEnvelope(
                    key=provider.key,
                    type=provider.type,
                    value=value,
                    source_node=frame.name,
                ),
                state,
            )

    def _record_pipeline_output_candidate(self, envelope: DataEnvelope, state: _RuntimeState) -> None:
        if any(output.type == envelope.type for output in self.graph.outputs):
            candidates = state.output_candidates[envelope.type]
            identity = (envelope.key, envelope.type, envelope.source_node)
            for index, item in enumerate(candidates):
                if (item.key, item.type, item.source_node) == identity:
                    candidates[index] = envelope
                    break
            else:
                candidates.append(envelope)

    def _finalize_pipeline_outputs(self, state: _RuntimeState) -> None:
        for output in self.graph.outputs:
            matches = list(state.output_candidates.get(output.type, ()))
            if output.cardinality == CARDINALITY_EXACTLY_ONE:
                if len(matches) != 1:
                    raise PipelineRuntimeError(f"pipeline output type '{output.type}' expected exactly one value, got {len(matches)}")
                _store_output(state.result, output.public_name, matches[0])
            elif output.cardinality == CARDINALITY_OPTIONAL_ONE:
                if len(matches) > 1:
                    raise PipelineRuntimeError(f"pipeline output type '{output.type}' expected at most one value, got {len(matches)}")
                if matches:
                    _store_output(state.result, output.public_name, matches[0])
            elif output.cardinality == CARDINALITY_ALL:
                state.result.set(output.public_name, [match.to_input() for match in matches])

    def _record_edge(self, edge: EdgeSpec) -> None:
        self.trace.record_edge(edge.source, edge.target)

    def _activate_edge(self, edge: EdgeSpec, state: _RuntimeState) -> None:
        state.active_edges.add(edge.pair)
        self._record_edge(edge)

    def _clear_conditional_outgoing(self, node_name: str, state: _RuntimeState) -> None:
        for edge in self._frames[node_name].outgoing:
            if edge.when:
                state.active_edges.discard(edge.pair)

    def _mark_node_run(self, node_name: str) -> None:
        self._node_runs[node_name] = self._node_runs.get(node_name, 0) + 1
        self.trace.record_node_run(node_name, self._node_runs[node_name])


__all__ = ["RuntimeOutputMixin"]
