import {defineNode} from "@vibeflow/plugin";
interface Envelope<T> { readonly value: T; }

function run(inputs: Readonly<Record<"payload.internal", Envelope<unknown>>>): { readonly processed_payload: unknown } {
  // BUSINESS CODE: replace this pass-through with the real transformation.
  return { processed_payload: inputs["payload.internal"].value };
}

export const process_payloadNode=defineNode({...{"rulesets": ["vibeflow.process"], "type_key": "minimal.process_payload", "display_name": "Process payload", "description": "Contains the project-specific business transformation.", "version": "0.15.0", "flow_kind": "process", "contract": {"requires": [{"type": "payload.internal", "cardinality": "exactly_one", "display_name": "Internal payload"}], "provides": [{"key": "processed_payload", "type": "payload.processed", "display_name": "Processed payload"}], "params_schema": {}, "params_defaults": {}, "input_semantics": {"payload.internal": ["Payload ready for project-specific processing."]}, "output_semantics": {"processed_payload": ["Result of project-specific processing."]}}, "base_libs": [], "capabilities": [], "tags": ["business"]},run});
