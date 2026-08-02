"""Public input and node-call contract handling for the Python runtime."""

from __future__ import annotations

from typing import Any, Mapping

from vibeflow.core.contracts import (
    CARDINALITY_ALL,
    CARDINALITY_EXACTLY_ONE,
    CARDINALITY_OPTIONAL_ONE,
    DataEnvelope,
)
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
from vibeflow.targets.python.runtime.planning import NodeFrame
from vibeflow.targets.python.runtime.types import _RuntimeState


class RuntimeContractMixin:
    def _validate_public_inputs(self, initial: Mapping[str, Any]) -> None:
        """Apply the closed ABI only when every input declares required."""

        if not self.graph.inputs or any(
            input_spec.required is None
            for input_spec in self.graph.inputs
        ):
            return
        known_keys = {input_spec.key for input_spec in self.graph.inputs}
        for key in initial:
            if key not in known_keys:
                raise PipelineRuntimeError(
                    f"unknown workflow input '{key}'"
                )
        for input_spec in self.graph.inputs:
            if input_spec.required and input_spec.key not in initial:
                raise PipelineRuntimeError(
                    f"required workflow input '{input_spec.key}' is missing"
                )

    def _new_state(self, initial: Mapping[str, Any]) -> _RuntimeState:
        state = _RuntimeState(inboxes={name: [] for name in self._frames})
        input_envelopes = []
        for provider in self.graph.inputs:
            if provider.key not in initial:
                continue
            input_envelopes.append(
                DataEnvelope(
                    key=provider.key,
                    type=provider.type,
                    value=initial[provider.key],
                    source_node="pipeline.input",
                )
            )
        for node_name in self._initial_input_nodes():
            frame = self._frames[node_name]
            accepted = {requirement.type for requirement in frame.requires}
            state.inboxes[node_name].extend(
                envelope
                for envelope in input_envelopes
                if envelope.type in accepted
            )
        return state

    def _initial_input_nodes(self) -> tuple[str, ...]:
        nodes: list[str] = []
        for name in self._plan.order:
            frame = self._frames[name]
            if not frame.requires:
                continue
            if not frame.incoming:
                nodes.append(name)
                continue
            if any(self._is_empty_start(edge.source) for edge in frame.incoming):
                nodes.append(name)
        return tuple(nodes)

    def _is_empty_start(self, node_name: str) -> bool:
        frame = self._frames.get(node_name)
        return bool(
            frame
            and frame.is_terminal
            and not frame.incoming
            and not frame.requires
            and not frame.provides
        )

    def _resolve_inputs(
        self,
        frame: NodeFrame,
        state: _RuntimeState,
    ) -> dict[str, object]:
        inputs: dict[str, object] = {}
        for requirement in frame.requires:
            matches = [
                envelope
                for envelope in state.inboxes[frame.name]
                if envelope.type == requirement.type
            ]
            self._record_type_resolution(frame, requirement, matches)
            if requirement.cardinality == CARDINALITY_EXACTLY_ONE:
                if len(matches) != 1:
                    raise PipelineRuntimeError(
                        f"node '{frame.name}' requires type "
                        f"'{requirement.type}' exactly once, got {len(matches)}"
                    )
                inputs[requirement.type] = matches[0].to_input()
            elif requirement.cardinality == CARDINALITY_OPTIONAL_ONE:
                if len(matches) > 1:
                    raise PipelineRuntimeError(
                        f"node '{frame.name}' requires type "
                        f"'{requirement.type}' at most once, got {len(matches)}"
                    )
                inputs[requirement.type] = (
                    matches[0].to_input() if matches else None
                )
            elif requirement.cardinality == CARDINALITY_ALL:
                inputs[requirement.type] = [
                    envelope.to_input()
                    for envelope in matches
                ]
            else:
                raise PipelineRuntimeError(
                    f"node '{frame.name}' has invalid cardinality "
                    f"'{requirement.cardinality}'"
                )
        return inputs


__all__ = ["RuntimeContractMixin"]
