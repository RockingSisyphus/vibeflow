import {defineNode} from "@vibeflow/plugin";
interface Envelope<T> { readonly value: T; }

function run(inputs: Readonly<Record<"payload.request", Envelope<unknown>>>): { readonly internal_payload: unknown } {
  return { internal_payload: inputs["payload.request"].value };
}

export const input_boundaryNode=defineNode({node_type:"vibeflow.node",...{"rulesets": ["vibeflow.io"], "id": "minimal.input_boundary", "display_name": "Input boundary", "description": "Adapts the public request into the workflow's internal payload.", "version": "0.15.0", "flow_kind": "io", "contract": {"requires": [{"type": "payload.request", "cardinality": "exactly_one", "display_name": "Public request"}], "provides": [{"key": "internal_payload", "type": "payload.internal", "display_name": "Internal payload"}], "params_schema": {}, "params_defaults": {}, "input_semantics": {"payload.request": ["Generic payload supplied by the caller."]}, "output_semantics": {"internal_payload": ["Internal payload passed to business processing."]}}, "base_libs": [], "capabilities": [], "tags": ["boundary"]},run});
