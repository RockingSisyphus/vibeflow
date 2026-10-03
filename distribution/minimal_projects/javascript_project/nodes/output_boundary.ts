import {defineNode} from "@vibeflow/plugin";
interface Envelope<T> { readonly value: T; }

function run(inputs: Readonly<Record<"payload.processed", Envelope<unknown>>>): { readonly response: unknown } {
  return { response: inputs["payload.processed"].value };
}

export const output_boundaryNode=defineNode({...{"rulesets": ["vibeflow.io"], "type_key": "minimal.output_boundary", "display_name": "Output boundary", "description": "Adapts the processed payload to the public response.", "version": "0.15.0", "flow_kind": "io", "contract": {"requires": [{"type": "payload.processed", "cardinality": "exactly_one", "display_name": "Processed payload"}], "provides": [{"key": "response", "type": "payload.response", "display_name": "Public response"}], "params_schema": {}, "params_defaults": {}, "input_semantics": {"payload.processed": ["Processed payload ready to leave the workflow."]}, "output_semantics": {"response": ["Generic response returned to the caller."]}}, "base_libs": [], "capabilities": [], "tags": ["boundary"]},run});
