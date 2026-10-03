from __future__ import annotations

from vibeflow.targets.python.sdk import node

def _value(inputs, data_type: str):
    return inputs[data_type]["value"]


@node(**{'rulesets': ['vibeflow.process'],
 'type_key': 'minimal.start',
 'display_name': 'Workflow start',
 'description': 'Marks the structural start of the minimal workflow.',
 'version': '0.15.0',
 'flow_kind': 'terminal',
 'contract': {'requires': [],
              'provides': [],
              'params_schema': {},
              'params_defaults': {},
              'input_semantics': {},
              'output_semantics': {}},
 'base_libs': [],
 'capabilities': [],
 'tags': ['boundary']})
class StartNode:

    def run_pure(self, inputs, params):
        return {}


@node(**{'rulesets': ['vibeflow.io'],
 'type_key': 'minimal.input_boundary',
 'display_name': 'Input boundary',
 'description': "Adapts the public request into the workflow's internal payload.",
 'version': '0.15.0',
 'flow_kind': 'io',
 'contract': {'requires': [{'type': 'payload.request',
                            'cardinality': 'exactly_one',
                            'display_name': 'Public request'}],
              'provides': [{'key': 'internal_payload',
                            'type': 'payload.internal',
                            'display_name': 'Internal payload'}],
              'params_schema': {},
              'params_defaults': {},
              'input_semantics': {'payload.request': ['Generic payload supplied by the caller.']},
              'output_semantics': {'internal_payload': ['Internal payload passed to business '
                                                        'processing.']}},
 'base_libs': [],
 'capabilities': [],
 'tags': ['boundary']})
class InputBoundaryNode:

    def run_pure(self, inputs, params):
        return {"internal_payload": _value(inputs, "payload.request")}


@node(**{'rulesets': ['vibeflow.process'],
 'type_key': 'minimal.process_payload',
 'display_name': 'Process payload',
 'description': 'Contains the project-specific business transformation.',
 'version': '0.15.0',
 'flow_kind': 'process',
 'contract': {'requires': [{'type': 'payload.internal',
                            'cardinality': 'exactly_one',
                            'display_name': 'Internal payload'}],
              'provides': [{'key': 'processed_payload',
                            'type': 'payload.processed',
                            'display_name': 'Processed payload'}],
              'params_schema': {},
              'params_defaults': {},
              'input_semantics': {'payload.internal': ['Payload ready for project-specific '
                                                       'processing.']},
              'output_semantics': {'processed_payload': ['Result of project-specific '
                                                         'processing.']}},
 'base_libs': [],
 'capabilities': [],
 'tags': ['business']})
class ProcessPayloadNode:

    def run_pure(self, inputs, params):
        # BUSINESS CODE: replace this pass-through with the real transformation.
        return {"processed_payload": _value(inputs, "payload.internal")}


@node(**{'rulesets': ['vibeflow.io'],
 'type_key': 'minimal.output_boundary',
 'display_name': 'Output boundary',
 'description': 'Adapts the processed payload to the public response.',
 'version': '0.15.0',
 'flow_kind': 'io',
 'contract': {'requires': [{'type': 'payload.processed',
                            'cardinality': 'exactly_one',
                            'display_name': 'Processed payload'}],
              'provides': [{'key': 'response',
                            'type': 'payload.response',
                            'display_name': 'Public response'}],
              'params_schema': {},
              'params_defaults': {},
              'input_semantics': {'payload.processed': ['Processed payload ready to leave the '
                                                        'workflow.']},
              'output_semantics': {'response': ['Generic response returned to the caller.']}},
 'base_libs': [],
 'capabilities': [],
 'tags': ['boundary']})
class OutputBoundaryNode:

    def run_pure(self, inputs, params):
        return {"response": _value(inputs, "payload.processed")}


@node(**{'rulesets': ['vibeflow.process'],
 'type_key': 'minimal.end',
 'display_name': 'Workflow end',
 'description': 'Marks the structural end after the response is available.',
 'version': '0.15.0',
 'flow_kind': 'terminal',
 'contract': {'requires': [],
              'provides': [],
              'params_schema': {},
              'params_defaults': {},
              'input_semantics': {},
              'output_semantics': {}},
 'base_libs': [],
 'capabilities': [],
 'tags': ['boundary']})
class EndNode:

    def run_pure(self, inputs, params):
        return {}
